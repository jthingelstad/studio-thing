"""Dynamic context blocks for persona prompts.

Facts that change day-to-day or per-issue, computed by Python rather than
left for the model to derive: today's date, days-to-publish, draft word
count, per-section item counts, asset presence, the delta from the prior
update-draft run. Each builder returns a dict; ``render_block`` formats it
as a markdown block to prepend to a job/review prompt. The agent reads it;
it doesn't recompute it.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional

from . import db, draft

logger = logging.getLogger("workshop.context")


def _today() -> date:
    # Issue cadence is Jamie's local time; for date-only math the offset
    # doesn't matter, and the daily cron fires at 17:00 CT so the date is
    # unambiguous. We don't carry a tz library.
    return datetime.now().date()


def _days_until(target_iso: str, ref: date) -> Optional[int]:
    try:
        t = datetime.strptime(target_iso, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (t - ref).days


def _digest_delta(st: dict[str, Any], prev: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not prev:
        return None

    def _p(key: str) -> int:
        try:
            return int(prev.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    def _was(key: str) -> bool:
        return bool(prev.get(key))

    return {
        "prev_ran_at": prev.get("ran_at"),
        "word_count": st["word_count"] - _p("word_count"),
        "notable": st["sections"]["notable"]["item_count"] - _p("notable_count"),
        "brief": st["sections"]["brief"]["item_count"] - _p("brief_count"),
        "journal": st["sections"]["journal"]["item_count"] - _p("journal_count"),
        "intro_now_present": st["intro_present"] and not _was("intro_present"),
        "currently_now_present": st["currently_present"] and not _was("currently_present"),
        "haiku_now_present": st["haiku_present"] and not _was("haiku_present"),
        "cover_now_present": st["cover_present"] and not _was("cover_present"),
        "draft_unchanged": prev.get("source_hash") == st.get("source_hash"),
    }


def build_eddy_context(
    *,
    ref_date: Optional[date] = None,
    section_status: Optional[dict[str, Any]] = None,
    prev_digest: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Eddy's ``## Today`` block for the post-update review.

    ``section_status`` / ``prev_digest`` can be supplied by ``update-draft``
    (it already has them) to avoid a second S3 round-trip; otherwise they're
    fetched here.
    """
    today = ref_date or _today()
    window = db.get_active_issue_window()
    if window is None:
        return {"today": today.isoformat(), "weekday": today.strftime("%a"), "active_issue": None}
    n = int(window["issue_number"])
    st = section_status if section_status is not None else draft.section_status(n)
    prev = prev_digest if prev_digest is not None else db.latest_draft_digest(n)
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%a"),
        "active_issue": n,
        "pub_date": window["pub_date"],
        "end_date": window["end_date"],
        "start_date": window["start_date"],
        "days_to_pub": _days_until(window["pub_date"], today),
        "word_count": st["word_count"],
        "word_count_band": _word_band(st["word_count"]),
        "sections": {
            name: {
                "item_count": v["item_count"],
                "present": v["present"],
                "placeholder": v["placeholder"],
            }
            for name, v in st["sections"].items()
        },
        "intro_present": st["intro_present"],
        "currently_present": st["currently_present"],
        "haiku_present": st["haiku_present"],
        "cover_present": st["cover_present"],
        "cta_files": st["cta_files"],
        "required_missing": st["required_missing"],
        "delta_since_last_run": _digest_delta(st, prev),
    }


def _word_band(wc: int) -> str:
    if wc < 1500:
        return "short (<1500 — note it, not necessarily a problem)"
    if wc <= 2500:
        return "comfortable (1500–2500)"
    if wc <= 3000:
        return "long (2500–3000 — gentle flag, suggest a cut or two)"
    return "over (>3000 — firm pushback, name concrete cut candidates)"


def render_block(ctx: dict[str, Any], heading: str = "Today") -> str:
    """Render a context dict as a markdown block to prepend to a prompt."""
    return (
        f"## {heading}\n\n"
        "Runtime-computed context — read it, don't recompute it:\n\n"
        f"```json\n{json.dumps(ctx, indent=2, default=str)}\n```\n"
    )
