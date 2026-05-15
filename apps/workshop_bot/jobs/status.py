"""``/eddy status`` — a read-only operational snapshot of the bot.

Not a content-loop job; it's the "what's the bot doing / is anything
stuck" view. All DB-only (no S3, no external APIs), so it's snappy. For
the in-flight issue's *content* completeness, use ``/eddy issue
status``; for campaign performance vs. expectation, use
``/marky campaign report``.

Shows: the active issue window, the active goal + live campaigns, any
held job locks (a deadlock would show here), and the last several
``agent_runs`` rows.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.status")

NAME = "status"

_RUN_ICON = {"success": "✅", "error": "❌", "pending": "⏳"}


def _rel(date_iso: str | None) -> str:
    try:
        d = (datetime.strptime(str(date_iso)[:10], "%Y-%m-%d").date() - datetime.now().date()).days
    except (TypeError, ValueError):
        return "?"
    if d == 0:
        return "today"
    return f"in {d}d" if d > 0 else f"{-d}d ago"


def _dur(ms) -> str:
    try:
        s = int(ms) / 1000.0
    except (TypeError, ValueError):
        return "?"
    return f"{s:.1f}s" if s < 60 else f"{s / 60:.1f}m"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    lines: list[str] = ["🛠️ **workshop_bot status**"]

    w = db.get_active_issue_window()
    if w is None:
        lines.append("• issue window: *(none — `/eddy issue start` to set one)*")
    else:
        n = int(w["issue_number"])
        lines.append(
            f"• issue window: **WT{n}** · pub {w['pub_date']} ({_rel(w['pub_date'])}) · "
            f"cutoff {w['end_date']} · {w.get('day_count', 7)}-day "
            f"— `/eddy issue status` for content state"
        )

    g = db.get_active_goal()
    if g is None:
        lines.append("• goal: *(none — `/patty goal set <kind> <value>`)*")
    else:
        lines.append(
            f"• goal: **{g['target_kind']} → {g['target_value']}** "
            f"(since {g.get('started_at', '?')})" + (f" — {g['notes']}" if g.get("notes") else "")
        )

    camps = db.active_campaigns()
    if camps:
        lines.append("• campaigns (live):")
        for c in camps:
            lines.append(f"  └ `{c['name']}` · ref `{c['ref']}` · since {c.get('started_at', '?')}")
    else:
        lines.append("• campaigns: *(none live)*")

    locks = db.list_job_locks()
    if locks:
        lines.append("• ⚠️ held job locks:")
        for lk in locks:
            lines.append(
                f"  └ `{lk['asset']}` — `{lk['job']}` since {lk.get('started_at', '?')} UTC "
                f"(pid {lk.get('pid')})"
            )
    else:
        lines.append("• job locks: none held")

    runs = db.recent_agent_runs(limit=8)
    if runs:
        lines.append("• recent runs:")
        for r in runs:
            icon = _RUN_ICON.get(str(r.get("status") or ""), "·")
            when = str(r.get("started_at") or "")[5:16]  # MM-DD HH:MM
            tail = f" — {r['error']}" if r.get("error") else ""
            lines.append(
                f"  └ {icon} {r.get('agent_name', '?')} · {r.get('trigger', '?')} · "
                f"{_dur(r.get('duration_ms'))} · {when}{tail}"
            )
    else:
        lines.append("• recent runs: *(none recorded yet)*")

    return _base.JobResult(
        True,
        "\n".join(lines),
        data={"issue_window": w, "goal": g, "campaigns": camps, "locks": locks, "runs": runs},
    )
