"""``update-draft`` — project upstream state into ``draft.md``.

A *pure projection*: re-run it and you get the same output (modulo
upstream changes). Each section block is replaced wholesale by its fill —
no additive merge. Real authoring lives upstream (Pinboard for links,
micro.blog for the journal, Drafts → Shortcut for ``intro.md`` /
``currently.md``); the haiku is a composed asset (``compose-haiku``).

After the fills the job writes ``draft.md`` back, records a ``draft_digests``
row (so Eddy's review can compute the delta), and — on Tue–Fri — runs
Eddy's post-update review and posts it to ``#editorial``. Sat/Sun/Mon it
stays silent. If ``final.md`` exists the issue is locked and the job
refuses (re-firing would silently produce a stale ``draft.md``).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime

from ..systems.pinboard import client as pinboard
from ..tools import anthropic_client, context, db, draft as draft_mod, microblog, s3
from . import _base

logger = logging.getLogger("workshop.jobs.update_draft")

NAME = "update-draft"

SECTION_BLOCKS = ("intro", "notable", "brief", "journal", "currently", "haiku")
_ASSET_FILE = {"intro": "intro.md", "currently": "currently.md", "haiku": "haiku.md"}

# Eddy posts a review only Tue–Fri (weekday 1..4, Mon=0). Sat/Sun/Mon the
# job runs but Eddy stays silent — issues just shipped Saturday and the
# early-week draft is too thin to comment on usefully.
_EDDY_REVIEW_WEEKDAYS = (1, 2, 3, 4)


# ---------- fills ----------

def _read_asset(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"].strip()
    return ""


def _render_notable(items: list[dict]) -> str:
    out: list[str] = []
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or url or "(untitled)").strip()
        desc = (it.get("description") or "").strip()
        block = f"### [{title}]({url})"
        if desc:
            block += f"\n\n{desc}"
        out.append(block)
    return "\n\n".join(out)


def _render_brief(items: list[dict]) -> str:
    out: list[str] = []
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or url or "(untitled)").strip()
        desc = (it.get("description") or "").strip()
        line = f"**[{title}]({url})**"
        if desc:
            line += f" — {desc}"
        out.append(line)
    return "\n\n".join(out)


def _journal_label(published_iso) -> str:
    try:
        dt = datetime.fromisoformat(str(published_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(published_iso or "").strip()
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year} at {hour12}:{dt.minute:02d} {ampm}"


def _render_journal(posts: list[dict]) -> str:
    out: list[str] = []
    for p in posts:
        url = (p.get("url") or "").strip()
        label = _journal_label(p.get("published"))
        head = f"[{label}]({url})" if url else label
        body = (p.get("content_md") or "").strip()
        out.append(f"{head}\n\n{body}" if body else head)
    return "\n\n".join(out)


def _gather_fills(window: dict) -> dict[str, str]:
    """Pull every section's content once. Source pulls (Pinboard,
    micro.blog) that fail degrade to a placeholder line rather than
    breaking the run."""
    n = int(window["issue_number"])
    fills: dict[str, str] = {block: _read_asset(n, _ASSET_FILE[block]) for block in _ASSET_FILE}

    try:
        cand = pinboard.issue_window_candidates(window["start_date"], window["end_date"])
        fills["notable"] = _render_notable(cand.get("notable", []))
        fills["brief"] = _render_brief(cand.get("brief", []))
    except Exception as exc:  # noqa: BLE001
        logger.warning("update-draft: Pinboard pull failed for #%d: %s", n, exc)
        fills["notable"] = f"_Notable — couldn't pull from Pinboard ({type(exc).__name__})._"
        fills["brief"] = f"_Briefly — couldn't pull from Pinboard ({type(exc).__name__})._"

    try:
        posts = microblog.posts_in_window(window["start_date"], window["end_date"])
        fills["journal"] = _render_journal(posts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("update-draft: micro.blog pull failed for #%d: %s", n, exc)
        fills["journal"] = f"_Journal — couldn't pull from micro.blog ({type(exc).__name__})._"

    return fills


def _load_draft(issue_number: int) -> str:
    res = s3.read_issue_file(issue_number, "draft.md")
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    return _base.starter_template()


def _final_exists(issue_number: int) -> bool:
    res = s3.read_issue_file(issue_number, "final.md")
    return bool(res.get("found"))


# ---------- Eddy's post-update review ----------

def _review_model(weekday: int) -> str:
    override = (os.environ.get("WORKSHOP_EDDY_REVIEW_MODEL") or "").strip()
    if override:
        return override
    # Thu/Fri reviews are substantive; early-week is mostly the checklist.
    return "sonnet" if weekday in (3, 4) else "haiku"


def _is_pass(text: str) -> bool:
    # Local copy of the PASS convention so this module doesn't pull in the
    # full personas.base import graph.
    if not text:
        return True
    import re as _re
    strip = _re.compile(r"[\s*_`~\"'()<>\[\].!?,;:\\\-—–]+")
    if strip.sub("", text).upper() == "PASS":
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return bool(lines) and strip.sub("", lines[-1]).upper() == "PASS"


async def _maybe_eddy_review(
    ctx: "_base.JobContext", window: dict, st: dict, prev_digest, today
) -> str:
    if today.weekday() not in _EDDY_REVIEW_WEEKDAYS:
        logger.info("update-draft: %s — Eddy stays silent", today.strftime("%a"))
        return "Eddy is silent Sat/Sun/Mon."
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        logger.info("update-draft: no team registry; Eddy review skipped")
        return "(no Discord — Eddy review skipped)"
    eddy = team.bots.get("eddy")
    if eddy is None or getattr(eddy, "user", None) is None:
        logger.info("update-draft: Eddy unavailable; review skipped")
        return "(Eddy unavailable — review skipped)"

    eddy_ctx = context.build_eddy_context(ref_date=today, section_status=st, prev_digest=prev_digest)
    try:
        review_prompt = anthropic_client.load_prompt("eddy-update-review")
    except OSError as exc:
        logger.warning("update-draft: review prompt missing: %s", exc)
        return "(Eddy review prompt missing)"
    user_msg = f"{context.render_block(eddy_ctx)}\n\n{review_prompt}"
    model = _review_model(today.weekday())
    with db.AgentRun("eddy", trigger="update-draft-review") as run:
        answer, _meta = await eddy.core(latest=user_msg, history=[], model=model)
        run.records_written = 0 if (not answer or _is_pass(answer)) else 1
    if not answer or _is_pass(answer):
        return "Eddy: PASS (nothing to flag)."
    posted = await ctx.post("DISCORD_CHANNEL_EDITORIAL", answer, persona="eddy")
    return "Eddy posted a review to #editorial." if posted else "(couldn't post Eddy's review)"


# ---------- the job ----------

async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False,
            "❌ no active issue window — run `/workshop job start-issue <n> <pub-date> <days>` first.",
        )
    n = int(window["issue_number"])

    if _final_exists(n):
        return _base.JobResult(
            False,
            f"❌ issue #{n} is locked — `final.md` exists. Delete it to unlock `update-draft`.",
        )

    asset = f"{n}/draft.md"
    try:
        with _base.job_lock([asset], NAME):
            text = _load_draft(n)
            fills = _gather_fills(window)
            for block in SECTION_BLOCKS:
                text = _base.replace_block(text, block, fills.get(block, ""))
            try:
                s3.write_issue_file(n, "draft.md", text)
            except Exception as exc:  # noqa: BLE001
                logger.exception("update-draft: write failed for #%d", n)
                return _base.JobResult(
                    False, f"❌ couldn't write `draft.md` for #{n}: `{type(exc).__name__}: {exc}`"
                )

            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            try:
                listing = s3.list_issue(n)
                files = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
            except Exception:  # noqa: BLE001
                files = set()
            st = draft_mod.section_status(n, draft_text=text, list_objects=files)
            prev_digest = db.latest_draft_digest(n)
            today = datetime.now().date()

            review_note = ""
            try:
                review_note = await _maybe_eddy_review(ctx, window, st, prev_digest, today)
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: Eddy review failed for #%d", n)
                review_note = "(Eddy review errored — see logs)"

            try:
                db.insert_draft_digest(
                    issue=n,
                    word_count=st["word_count"],
                    notable_count=st["sections"]["notable"]["item_count"],
                    brief_count=st["sections"]["brief"]["item_count"],
                    journal_count=st["sections"]["journal"]["item_count"],
                    intro_present=st["intro_present"],
                    currently_present=st["currently_present"],
                    haiku_present=st["haiku_present"],
                    cover_present=st["cover_present"],
                    source_hash=source_hash,
                )
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: digest write failed for #%d", n)
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `update-draft` is already running ({exc.holder_desc}) — try again shortly."
        )

    missing = ", ".join(st["required_missing"]) or "nothing"
    return _base.JobResult(
        True,
        f"refreshed `draft.md` for #{n} (~{st['word_count']} words; "
        f"{st['sections']['notable']['item_count']} Notable / "
        f"{st['sections']['brief']['item_count']} Briefly / "
        f"{st['sections']['journal']['item_count']} Journal). "
        f"Still missing for ship: {missing}. {review_note}".strip(),
        data={"issue_number": n, "section_status": st, "review": review_note},
    )
