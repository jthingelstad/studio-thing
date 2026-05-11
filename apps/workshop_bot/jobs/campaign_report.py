"""``campaign-report`` — active campaigns + current performance vs expected.

Joins ``campaigns`` against the latest ``campaign_metrics`` row per
campaign and returns a summary. Read-only, deterministic, no LLM.
"""

from __future__ import annotations

from ..tools import db
from . import _base

NAME = "campaign-report"


def _vs(actual, expected) -> str:
    if expected is None or actual is None:
        return f"{actual if actual is not None else '?'}"
    if expected == 0:
        return f"{actual} (no target)"
    pct = round(100 * actual / expected)
    arrow = "📈" if pct >= 100 else ("➡️" if pct >= 60 else "🐢")
    return f"{actual} / {expected} ({pct}% {arrow})"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    campaigns = db.active_campaigns()
    if not campaigns:
        return _base.JobResult(True, "No active campaigns. Register one with `/workshop job add-campaign <name> <ref>`.",
                               data={"campaigns": []})
    lines = ["📊 **Active campaigns**", ""]
    for c in campaigns:
        latest = db.latest_campaign_metric(c["name"]) or {}
        signups = latest.get("signups")
        traffic = latest.get("traffic")
        polled = latest.get("ran_at") or "never polled"
        lines.append(
            f"- **{c['name']}** (ref `{c['ref']}`, since {c['started_at']}) — "
            f"signups: {_vs(signups, c.get('expected_signups'))} · "
            f"traffic: {_vs(traffic, c.get('expected_traffic'))} · last poll: {polled}"
        )
    return _base.JobResult(True, "\n".join(lines), data={"campaigns": [c["name"] for c in campaigns]})
