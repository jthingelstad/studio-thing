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
from datetime import date, datetime, timedelta
from typing import Any, Optional

from . import db, draft

logger = logging.getLogger("workshop.context")

# Issue #1 of The Weekly Thing shipped 2017-05-13; the May 13 anniversary
# is pacing context for Patty (year-rhythm, issues remaining), not a goal
# anchor.
_ANNIVERSARY_MONTH, _ANNIVERSARY_DAY = 5, 13


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


def build_linky_context(*, ref_date: Optional[date] = None) -> dict[str, Any]:
    """Linky's ``## Today`` block for a pinboard-scan: today's date,
    days-to-publish, days into the window, toread queue depth, and how many
    items have been captured to Briefly so far this week. One ``/posts/all``
    call derives the last two; on failure they come back as ``None`` and
    Linky can fall back to the tools."""
    today = ref_date or _today()
    window = db.get_active_issue_window()
    if window is None:
        return {"today": today.isoformat(), "weekday": today.strftime("%a"), "active_issue": None}
    n = int(window["issue_number"])
    try:
        sd = datetime.strptime(window["start_date"], "%Y-%m-%d").date()
        ed = datetime.strptime(window["end_date"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        sd = ed = None

    toread_count: Optional[int] = None
    brief_captured: Optional[int] = None
    try:
        from ..systems.pinboard import client as _pb  # lazy — keeps tools import-light
        all_posts = _pb.posts_all(results=1000)
        toread_count = sum(1 for p in all_posts if (p.get("toread") == "yes"))
        if sd and ed:
            bc = 0
            for p in all_posts:
                if "_brief" not in set((p.get("tags") or "").split()):
                    continue
                try:
                    d = datetime.fromisoformat(str(p.get("time") or "").replace("Z", "+00:00")).date()
                except ValueError:
                    continue
                if sd < d <= ed:
                    bc += 1
            brief_captured = bc
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_linky_context: pinboard fetch failed: %s", exc)

    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%a"),
        "active_issue": n,
        "pub_date": window["pub_date"],
        "end_date": window["end_date"],
        "start_date": window["start_date"],
        "days_to_pub": _days_until(window["pub_date"], today),
        "days_into_window": ((today - sd).days if sd else None),
        "toread_count": toread_count,
        "brief_captured_this_week": brief_captured,
    }


def _next_anniversary(today: date) -> date:
    this_year = date(today.year, _ANNIVERSARY_MONTH, _ANNIVERSARY_DAY)
    return this_year if today <= this_year else date(today.year + 1, _ANNIVERSARY_MONTH, _ANNIVERSARY_DAY)


def _is_no_publish_saturday(d: date) -> bool:
    """No-publish weeks: July, August, and Dec 15 – Jan 15."""
    if d.month in (7, 8):
        return True
    if d.month == 12 and d.day >= 15:
        return True
    if d.month == 1 and d.day <= 15:
        return True
    return False


def _saturdays_between(after: date, through: date):
    """Saturdays strictly after ``after`` up to and including ``through``."""
    ahead = (5 - after.weekday()) % 7  # 5 == Saturday
    if ahead == 0:
        ahead = 7
    d = after + timedelta(days=ahead)
    while d <= through:
        yield d
        d += timedelta(days=7)


def _expected_issues_remaining(today: date, anniversary: date) -> int:
    return sum(1 for s in _saturdays_between(today, anniversary) if not _is_no_publish_saturday(s))


def build_patty_context(*, ref_date: Optional[date] = None) -> dict[str, Any]:
    """Patty's ``## Today`` block for compose-cta: today's date, days to
    the next May 13 anniversary (pacing context only), expected publishing
    Saturdays remaining before then, the current active goal + live
    progress (member count from Buttondown for kind='members', total
    raised from Stripe for kind='dollars'), recent achieved goals + their
    durations, and the current nonprofit. The model reads this; it doesn't
    recompute it."""
    today = ref_date or _today()
    ann = _next_anniversary(today)
    goal = db.get_active_goal()
    progress: Optional[float] = None
    if goal:
        try:
            if goal["target_kind"] == "members":
                from ..systems.buttondown import client as _bd
                progress = _bd.counts().get("premium")
            elif goal["target_kind"] == "dollars":
                from ..systems.stripe import client as _st
                progress = _st.year_to_date().get("total_usd")
        except Exception as exc:  # noqa: BLE001
            logger.warning("build_patty_context: progress lookup failed: %s", exc)

    recent: list[dict[str, Any]] = []
    for g in db.recent_achieved_goals(3):
        dur = None
        try:
            s = datetime.strptime(g["started_at"], "%Y-%m-%d").date()
            a = datetime.strptime(g["achieved_at"], "%Y-%m-%d").date()
            dur = (a - s).days
        except (TypeError, ValueError):
            pass
        recent.append({
            "kind": g["target_kind"], "target": g["target_value"],
            "started": g["started_at"], "achieved": g["achieved_at"], "duration_days": dur,
        })

    current_nonprofit: Optional[dict[str, Any]] = None
    try:
        from . import support_state
        cur = (support_state.read().get("support") or {}).get("current") or {}
        if cur:
            current_nonprofit = {
                "name": cur.get("nonprofit"), "short_name": cur.get("short_name"),
                "year": cur.get("year"), "year_label": cur.get("year_label"),
                "description": cur.get("description"),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_patty_context: support_state read failed: %s", exc)

    window = db.get_active_issue_window()
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%a"),
        "active_issue": (int(window["issue_number"]) if window else None),
        "pub_date": (window["pub_date"] if window else None),
        "days_to_anniversary": (ann - today).days,
        "next_anniversary": ann.isoformat(),
        "expected_issues_before_anniversary": _expected_issues_remaining(today, ann),
        "active_goal": (
            {"kind": goal["target_kind"], "target_value": goal["target_value"],
             "started_at": goal["started_at"],
             "current_progress": progress,
             "remaining": (goal["target_value"] - progress) if (progress is not None) else None}
            if goal else None
        ),
        "recent_achieved_goals": recent,
        "current_nonprofit": current_nonprofit,
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
