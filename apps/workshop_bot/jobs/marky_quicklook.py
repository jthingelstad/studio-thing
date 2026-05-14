"""``/marky {engagement,referrers}`` — read-only quick looks.

No LLM calls; composites of what Tinylytics and Buttondown already
surface. Useful when Jamie wants a fast read without waiting for the
nightly daily-metrics cron.
"""

from __future__ import annotations

import asyncio
import logging

from ..systems.buttondown import client as buttondown
from ..systems.tinylytics import client as tinylytics
from . import _base

logger = logging.getLogger("workshop.jobs.marky_quicklook")


# ---------- /marky engagement ----------

async def engagement(ctx: "_base.JobContext", *, days: int = 7) -> "_base.JobResult":
    """Composite subscriber-growth + site-engagement quick read."""
    days = max(1, min(int(days or 7), 90))
    try:
        growth = await asyncio.to_thread(buttondown.subscriber_growth, days=days)
    except Exception as exc:  # noqa: BLE001
        logger.warning("marky_quicklook engagement: subscriber_growth failed: %s", exc)
        growth = {}
    try:
        summary = await asyncio.to_thread(tinylytics.summary, days=days)
    except Exception as exc:  # noqa: BLE001
        logger.warning("marky_quicklook engagement: tinylytics summary failed: %s", exc)
        summary = {}

    bits = [f"📈 **Engagement — last {days}d**"]

    added = growth.get("added")
    churned = growth.get("churned")
    net = growth.get("net")
    by_source = growth.get("by_source") or {}
    if any(v is not None for v in (added, churned, net)):
        bits.append(
            f"**Subscribers:** +{added or 0} added · −{churned or 0} churned · "
            f"net **{net if net is not None else 0:+d}**"
        )
        if by_source:
            top = sorted(by_source.items(), key=lambda kv: -int(kv[1] or 0))[:4]
            bits.append("_by source:_ " + ", ".join(f"`{k}`={v}" for k, v in top))
    else:
        bits.append("_(Buttondown growth unavailable)_")

    total_hits = summary.get("total_hits")
    top_pages = summary.get("top_pages") or []
    top_referrers = summary.get("top_referrers") or []
    if total_hits is not None:
        bits.append("")
        bits.append(f"**Site:** {total_hits:,} hits")
        if top_pages:
            bits.append("_top pages:_")
            for p in top_pages[:5]:
                path = p.get("path") or "?"
                hits = p.get("hits") or p.get("count") or 0
                bits.append(f"- {hits:>4} · `{path}`")
        if top_referrers:
            bits.append("_top referrers:_")
            for r in top_referrers[:5]:
                ref = r.get("referrer") or r.get("source") or "?"
                hits = r.get("hits") or r.get("count") or 0
                bits.append(f"- {hits:>4} · `{ref}`")
    else:
        bits.append("\n_(Tinylytics summary unavailable)_")

    return _base.JobResult(True, "\n".join(bits), data={"growth": growth, "summary": summary})


# ---------- /marky referrers ----------

async def referrers(ctx: "_base.JobContext", *, days: int = 30) -> "_base.JobResult":
    """Tinylytics referrer drill-down over a trailing window."""
    days = max(1, min(int(days or 30), 365))
    try:
        rows = await asyncio.to_thread(tinylytics.referrers, days=days, limit=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("marky_quicklook referrers: failed: %s", exc)
        return _base.JobResult(False, f"❌ Tinylytics referrers fetch failed: `{type(exc).__name__}: {exc}`")

    if not rows:
        return _base.JobResult(True, f"_(No referrers recorded in the last {days}d.)_")

    bits = [f"🔗 **Referrers — last {days}d** (top {min(20, len(rows))})"]
    for r in rows[:20]:
        ref = r.get("referrer") or r.get("source") or "?"
        hits = r.get("hits") or r.get("count") or 0
        bits.append(f"- **{hits:>5}** · `{ref}`")

    return _base.JobResult(True, "\n".join(bits), data={"referrers": rows[:20], "days": days})
