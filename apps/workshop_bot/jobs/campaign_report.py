"""``campaign-report`` — active campaigns + current performance.

Reads ``campaigns.actual_signups`` (denormalised KPI) and the latest
``campaign_metrics`` poll timestamp. Read-only, deterministic, no LLM.
"""

from __future__ import annotations

from ..tools import db
from . import _base

NAME = "campaign-report"


def _cost_per_signup(cost, signups) -> str | None:
    """Format $/signup when both fields are present and signups > 0."""
    if cost is None or signups is None or not signups:
        return None
    try:
        return f"${float(cost) / int(signups):.2f}/signup"
    except (TypeError, ValueError, ZeroDivisionError):
        return None


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    campaigns = db.active_campaigns()
    if not campaigns:
        return _base.JobResult(True, "No active campaigns. Register one with `/marky campaign add <name> <ref>`.",
                               data={"campaigns": []})
    lines = ["📊 **Active campaigns**", ""]
    for c in campaigns:
        latest = db.latest_campaign_metric(c["name"]) or {}
        polled = latest.get("ran_at") or "never polled"
        actual = c.get("actual_signups")
        cost = c.get("cost")
        bits = [f"signups: {actual if actual is not None else '—'}"]
        cps = _cost_per_signup(cost, actual)
        if cost is not None:
            bits.append(f"cost: ${float(cost):.2f}" + (f" ({cps})" if cps else ""))
        if c.get("platform"):
            bits.append(f"on {c['platform']}")
        bits.append(f"last poll: {polled}")
        lines.append(
            f"- **{c['name']}** (ref `{c['ref']}`, since {c['started_at']}) — "
            + " · ".join(bits)
        )
        copy = (c.get("copy") or "").strip()
        if copy:
            preview = copy if len(copy) <= 200 else copy[:197] + "…"
            lines.append(f"  ↳ copy: {preview.replace(chr(10), ' / ')}")
        else:
            lines.append("  ↳ copy: _(none recorded — `/marky campaign copy`)_")
    return _base.JobResult(True, "\n".join(lines), data={"campaigns": [c["name"] for c in campaigns]})
