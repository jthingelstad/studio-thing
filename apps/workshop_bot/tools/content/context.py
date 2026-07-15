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
from datetime import date, datetime
from typing import Any, Optional

from .. import db
from . import draft

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


def _draft_iteration_count(issue_number: int) -> int:
    """How many editorial review passes Eddy has run for this issue —
    the "how many times have we reviewed this?" signal for tier
    selection. Counts Eddy's review ``agent_runs`` inside the issue's
    window (agent_runs has no issue column; the window bounds scope it).
    +1 because the count is read at the start of the *current* pass, so
    1 means "this is our first pass"."""
    try:
        window = db.get_active_issue_window(int(issue_number))
        since = (window or {}).get("start_date") or "1970-01-01"
        with db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM agent_runs "
                "WHERE agent_name = 'eddy' "
                "  AND trigger IN ('eddy-review', 'update-draft:html-review') "
                "  AND started_at >= ?",
                (since,),
            ).fetchone()
            return (int(row["n"]) if row else 0) + 1
    except Exception:  # noqa: BLE001
        return 1


def _open_comments_counts(issue_number: int) -> dict[str, Any]:
    """Open editorial_comments for this issue, total + per scope.

    Lets Eddy see at a glance that he's already flagged N3 three times
    or that hygiene comments are piling up unaddressed."""
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT scope, section, COUNT(*) AS n "
                "FROM editorial_comments "
                "WHERE issue_number = ? "
                "  AND replaced_by_id IS NULL "
                "  AND closed_at IS NULL "
                "GROUP BY scope, section",
                (int(issue_number),),
            ).fetchall()
    except Exception:  # noqa: BLE001
        return {"total": 0, "by_scope": {}, "by_section": {}}
    total = 0
    by_scope: dict[str, int] = {}
    by_section: dict[str, int] = {}
    for r in rows:
        n = int(r["n"])
        total += n
        scope = str(r["scope"])
        by_scope[scope] = by_scope.get(scope, 0) + n
        section = r["section"]
        if section:
            by_section[str(section)] = by_section.get(str(section), 0) + n
    return {"total": total, "by_scope": by_scope, "by_section": by_section}


def _review_tier(days_to_pub: Optional[int], iteration_count: int) -> str:
    """Map cycle position → tier. The draft-review prompt branches on
    this so feedback adapts to where in the process we are:

    - ``early`` — first 1-2 passes, plenty of runway. Substantive,
      anchored, suggestions only.
    - ``mid`` — passes 3+ with multiple days still to go. Flag only
      what hasn't been noted before; reference prior handles instead
      of re-flagging.
    - ``ship_eve`` — <24h to publish. Blockers only — anchor
      mismatches, dead links, voice slips, alt-text gaps. Skip
      stylistic preferences.

    A missing ``days_to_pub`` defaults to ``mid`` (safest assumption
    when the cycle position is unknown).
    """
    if days_to_pub is None:
        return "mid"
    if days_to_pub <= 1:
        return "ship_eve"
    if iteration_count <= 2:
        return "early"
    return "mid"


def build_eddy_context(
    *,
    ref_date: Optional[date] = None,
    section_status: Optional[dict[str, Any]] = None,
    prev_digest: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Eddy's ``## Today`` block for the editorial review (``eddy-review``).

    ``section_status`` can be supplied by the caller (it already has it) to
    avoid recomputation. ``prev_digest`` is retired vocabulary (the
    ``draft_digests`` projection table is gone) — accepted and ignored so
    older callers keep working.
    """
    today = ref_date or _today()
    window = db.get_active_issue_window()
    if window is None:
        return {"today": today.isoformat(), "weekday": today.strftime("%a"), "active_issue": None}
    n = int(window["issue_number"])
    st = section_status if section_status is not None else draft.section_status(n)
    days_to_pub = _days_until(window["pub_date"], today)
    iteration_count = _draft_iteration_count(n)
    open_comments = _open_comments_counts(n)
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%a"),
        "active_issue": n,
        "pub_date": window["pub_date"],
        "end_date": window["end_date"],
        "start_date": window["start_date"],
        "days_to_pub": days_to_pub,
        "draft_iteration_count": iteration_count,
        "review_tier": _review_tier(days_to_pub, iteration_count),
        "open_comments": open_comments,
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
        "currently_content": st.get("currently_content", ""),
        "haiku_present": st["haiku_present"],
        "cover_present": st["cover_present"],
        "cta_files": st["cta_files"],
        "required_missing": st["required_missing"],
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
