"""Headless production status — phase, content presence, readiness gates.

Pure DB + S3 reads, no Discord. This is the single source of production status,
consumed by the web project page, the machine-readable feed
(`jobs/scout_production_feed.py`), the lifecycle transitions
(`jobs/production_ops.py`), and — until they're retired — the phase cards.

It absorbs the state that used to live inside the card modules
(`build_card.gather_state` / `publish_card.gather_state`) and the two S3
presence primitives from `jobs/_cards.py` (`issue_files` / `read_metadata_raw`).
The card-render bits (embeds, views) stay in the card modules.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..tools import content_store, db, issue_items, s3
from ..tools.content import draft as draft_mod
from . import issue_status, publish

logger = logging.getLogger("workshop.jobs.production_state")

# Publish-phase readiness gate keys. These strings double as the
# publish-card button custom_ids (the view disables a button when its gate is
# False); kept here so the feed + web read gates without importing the card.
BTN_RECOMPOSE = "publish:recompose"
BTN_EMAIL = "publish:email"
BTN_WEBSITE = "publish:website"
BTN_PODCAST = "publish:podcast"
BTN_ALL = "publish:all"


# ---------- S3 presence primitives (moved from jobs/_cards.py) ----------

def read_metadata_raw(n: int) -> dict:
    """Read the authored metadata.json content verbatim (no placeholder
    injection) so callers can tell *authored* fields from *absent* ones. The
    publish-stamped buttondown_id/absolute_url are NOT here — they live on the
    issue window (read separately). Empty dict on any miss."""
    raw = content_store.read_issue(n, "metadata.json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("production_state: read_metadata_raw(%d) JSON parse failed: %s", n, exc)
        return {}
    return data if isinstance(data, dict) else {}


def issue_files(n: int) -> set:
    """Presence set for the issue: authored content names (from the DB store)
    UNION the S3 binaries/artifacts whose presence still matters (cover.jpg,
    the rendered mp3, generated artifacts). Stale S3 copies of authored atoms
    are excluded — content presence comes from the DB."""
    names = set(content_store.list_issue(n))
    try:
        listing = s3.list_issue(n)
        for o in listing.get("objects", []):
            fn = o.get("filename")
            if fn and not content_store.is_atom_name(fn):
                names.add(fn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("production_state: issue_files(%d) S3 list failed: %s", n, exc)
    return names


def _resolve_n(n: Optional[int], window: Optional[dict]) -> tuple[Optional[int], Optional[dict]]:
    """Resolve the issue number + window. Prefer the window's issue_number
    column; fall back to the explicit n (start-issue passes a compute_window
    dict that has dates but no issue_number)."""
    window = window or db.get_active_issue_window()
    if window is None:
        return None, None
    derived = window.get("issue_number")
    if derived is not None:
        return int(derived), window
    if n is not None:
        return int(n), window
    return None, None


# ---------- the status state (moved from build_card / publish_card) ----------

def build_state(n: Optional[int] = None, *, window: Optional[dict] = None) -> dict:
    """Build-phase content state. Synchronous (blocking S3); async callers
    wrap in asyncio.to_thread."""
    n, window = _resolve_n(n, window)
    if n is None:
        return {"issue_number": None}
    files = issue_files(n)
    st = draft_mod.section_status(n, list_objects=files)

    currently = db.currently_get_entries(n)
    try:
        open_comments = len(issue_items.list_open_comments(n))
    except Exception as exc:  # noqa: BLE001
        logger.warning("production_state: list_open_comments(%d) failed: %s", n, exc)
        open_comments = 0

    sec = st["sections"]
    sections_ready = all(sec[k]["present"] for k in ("notable", "brief", "journal"))
    build_ready = bool(sections_ready and st["intro_present"] and st["cover_present"])

    return {
        "issue_number": n,
        "phase": window.get("phase", "build"),
        "pub_date": window.get("pub_date", ""),
        "days_to_pub": issue_status._days_to(window.get("pub_date", "")),
        "word_count": st["word_count"],
        "sections": sec,
        "intro_present": st["intro_present"],
        "outro_present": "outro.md" in files,
        "cover_present": st["cover_present"],
        "currently_entries": [c.get("type_label") for c in currently],
        "reorder_applied": "thesis.md" in files,
        "open_comments": open_comments,
        "review_url": s3.issue_file_url(n, "draft.html"),
        "build_ready": build_ready,
    }


def publish_state(n: Optional[int] = None, *, window: Optional[dict] = None) -> dict:
    """Publish-phase send state — the shared envelope + per-channel gates."""
    n, window = _resolve_n(n, window)
    if n is None:
        return {"issue_number": None}
    files = issue_files(n)
    st = draft_mod.section_status(n, list_objects=files)
    meta = read_metadata_raw(n)

    subject = (meta.get("subject") or "").strip()
    description = (meta.get("description") or "").strip()
    # Publish-stamped fields live on the issue window, not the content row.
    buttondown_id = (window.get("buttondown_id") or "").strip()
    absolute_url = (window.get("absolute_url") or "").strip()
    cta_files = sorted(
        f for f in files if (f.startswith("cta-") or f.startswith("thanks-")) and f.endswith(".md")
    )
    haiku_present = bool(st["assets"].get("haiku.md"))
    echoes_present = "echoes.md" in files
    thesis_body = content_store.read_issue(n, "thesis.md")
    thesis_text = thesis_body.strip() if thesis_body else ""

    any_section = any(st["sections"][k]["present"] for k in ("notable", "brief", "journal"))
    email_ready = bool(subject and description and haiku_present
                       and st["intro_present"] and st["cover_present"])
    email_missing = []
    if not subject:
        email_missing.append("subject")
    if not description:
        email_missing.append("description")
    for req, present in (("haiku", haiku_present),
                         ("intro", st["intro_present"]), ("cover", st["cover_present"])):
        if not present:
            email_missing.append(req)

    phase = window.get("phase", "publish")
    thesis_failed = phase == "publish" and not thesis_text
    echoes_failed = phase == "publish" and not echoes_present
    recompose_needed = thesis_failed or echoes_failed

    return {
        "issue_number": n,
        "phase": phase,
        "pub_date": window.get("pub_date", ""),
        "days_to_pub": issue_status._days_to(window.get("pub_date", "")),
        "thesis": thesis_text,
        "thesis_failed": thesis_failed,
        "subject": subject,
        "description": description,
        "haiku_present": haiku_present,
        "echoes_present": echoes_present,
        "echoes_failed": echoes_failed,
        "recompose_needed": recompose_needed,
        "cta_files": cta_files,
        "buttondown_id": buttondown_id,
        "buttondown_url": (publish._draft_url(buttondown_id) if buttondown_id else ""),
        "absolute_url": absolute_url,
        "email_missing": email_missing,
        "audio_shipped": f"weekly-thing-{n}.mp3" in files,
        "email_shipped": bool(buttondown_id),
        "review_url": s3.issue_file_url(n, "draft.html"),
        "gates": {
            BTN_RECOMPOSE: recompose_needed,
            BTN_EMAIL: email_ready,
            BTN_WEBSITE: bool(buttondown_id),
            BTN_PODCAST: any_section,
            BTN_ALL: email_ready,
        },
    }
