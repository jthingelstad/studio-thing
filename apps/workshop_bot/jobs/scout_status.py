"""``/scout status`` — Scout's read-only ops snapshot.

Mirrors ``jobs/status.py`` (the ``/eddy status`` view) but framed from
the production-management perspective: what's on the slate, what's the
phase, what's blocked. All DB-only; no S3, no external APIs.

Today the slate is newsletter-only — exactly one in-flight
``issue_windows`` row at most. The multi-surface ``productions`` schema
will widen this while keeping the same job signature.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.scout_status")

NAME = "scout-status"

_RUN_ICON = {"success": "✅", "error": "❌", "pending": "⏳"}


def _rel(date_iso: str | None) -> str:
    try:
        d = (
            datetime.strptime(str(date_iso)[:10], "%Y-%m-%d").date()
            - datetime.now().date()
        ).days
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
    lines: list[str] = ["🛠️ **scout status** — slate + bot health"]

    w = db.get_active_issue_window()
    if w is None:
        lines.append("• slate: *(empty — no in-flight newsletter; nothing else tracked yet)*")
    else:
        n = int(w["issue_number"])
        phase = str(w.get("phase") or "build").lower()
        lines.append(
            f"• slate: **WT{n}** [{phase}] · pub {w['pub_date']} ({_rel(w['pub_date'])}) · "
            f"cutoff {w['end_date']} · {w.get('day_count', 7)}-day"
        )

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
        data={"issue_window": w, "locks": locks, "runs": runs},
    )
