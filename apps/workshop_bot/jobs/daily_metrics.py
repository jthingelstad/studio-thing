"""``daily-metrics`` (Marky) — daily website + subscriber + campaign report.

Scheduled daily 19:00 CT; manual re-fire via ``/workshop promo metrics``.

Each run: (1) for every active campaign, fetch current traffic (Tinylytics
`?ref=` source count) + signups (Buttondown ref attribution), append a
``campaign_metrics`` row, and compute the delta vs the prior row; (2)
gather subscriber growth and recent site engagement; (3) if nothing
material moved, **PASS** silently — no "nothing to report" ack; (4) if
something moved, run Marky's agent loop to compose a terse report and post
it to ``#promotion``.
"""

from __future__ import annotations

import asyncio
import logging

from ..systems.buttondown import client as buttondown
from ..systems.tinylytics import client as tinylytics
from ..tools import anthropic_client, context, db
from . import _base

logger = logging.getLogger("workshop.jobs.daily_metrics")

NAME = "daily-metrics"


def _campaign_window_days(started_at: str | None) -> int:
    """Pick a sensible attribution window for a campaign's age."""
    if not started_at:
        return 14
    try:
        from datetime import datetime as _dt
        age = (_dt.now().date() - _dt.strptime(str(started_at)[:10], "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return 14
    return 7 if age <= 10 else (30 if age <= 45 else 60)


def _campaign_traffic(ref: str, days: int) -> int | None:
    try:
        out = tinylytics.sources(days=days)
        by_source = out.get("by_source") or {}
        return int(by_source.get(ref, 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily-metrics: tinylytics sources for %s failed: %s", ref, exc)
        return None


def _campaign_signups(ref: str, days: int) -> int | None:
    try:
        out = buttondown.attribution_summary(days=days)
        by_ref = out.get("by_ref") or {}
        return int(by_ref.get(ref, 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily-metrics: buttondown attribution for %s failed: %s", ref, exc)
        return None


def _poll_campaigns() -> list[dict]:
    """Poll each active campaign, append a metrics row, return per-campaign
    snapshots with deltas."""
    snapshots: list[dict] = []
    for c in db.active_campaigns():
        days = _campaign_window_days(c.get("started_at"))
        traffic = _campaign_traffic(c["ref"], days)
        signups = _campaign_signups(c["ref"], days)
        prev = db.latest_campaign_metric(c["name"]) or {}
        prev_t, prev_s = prev.get("traffic"), prev.get("signups")
        db.insert_campaign_metric(campaign_name=c["name"], signups=signups, traffic=traffic)
        d_t = (traffic - prev_t) if (traffic is not None and isinstance(prev_t, int)) else None
        d_s = (signups - prev_s) if (signups is not None and isinstance(prev_s, int)) else None
        snapshots.append({
            "name": c["name"], "ref": c["ref"], "window_days": days,
            "traffic": traffic, "signups": signups,
            "delta_traffic": d_t, "delta_signups": d_s,
            "expected_traffic": c.get("expected_traffic"), "expected_signups": c.get("expected_signups"),
            "copy": (c.get("copy") or None),
            "is_first_poll": not prev,
        })
    return snapshots


def _moved(growth: dict, campaigns: list[dict]) -> bool:
    """Did anything material move? — non-trivial subscriber net, any churn
    spike, or a campaign delta / first poll."""
    net = int(growth.get("net") or 0)
    churned = int(growth.get("churned") or 0)
    if abs(net) >= 3 or churned >= 3:
        return True
    for c in campaigns:
        if c["is_first_poll"]:
            return True
        if (c["delta_traffic"] or 0) != 0 or (c["delta_signups"] or 0) != 0:
            return True
        # Trending way off expectation is worth a flag even if static.
        et, t = c.get("expected_traffic"), c.get("traffic")
        if isinstance(et, int) and et > 0 and isinstance(t, int) and (t < 0.4 * et or t > 1.5 * et):
            return True
    return False


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    # All of these hit external APIs — keep them off the event loop.
    campaigns = await asyncio.to_thread(_poll_campaigns)
    try:
        growth = await asyncio.to_thread(buttondown.subscriber_growth, days=7)
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily-metrics: subscriber_growth failed: %s", exc)
        growth = {}
    try:
        engagement = await asyncio.to_thread(tinylytics.summary, days=2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily-metrics: tinylytics summary failed: %s", exc)
        engagement = {}

    if not _moved(growth, campaigns):
        return _base.JobResult(True, "PASS — nothing material moved.", data={"posted": False, "campaigns": campaigns})

    bot = None
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is not None:
        bot = team.bots.get("marky")
    if bot is None or getattr(bot, "user", None) is None:
        return _base.JobResult(True, "(daily-metrics: something moved but no Discord — not posted)",
                               data={"posted": False, "campaigns": campaigns})

    marky_ctx = await asyncio.to_thread(context.build_marky_context)
    payload = {
        "subscriber_growth_7d": growth,
        "engagement_48h": engagement,
        "campaigns": campaigns,
    }
    try:
        base_prompt = anthropic_client.load_prompt("marky-daily-metrics")
    except OSError as exc:
        logger.warning("daily-metrics: prompt missing: %s", exc)
        return _base.JobResult(False, f"daily-metrics prompt missing: {exc}", data={"posted": False})
    user_msg = (
        f"{context.render_block(marky_ctx)}\n\n"
        f"{context.render_block(payload, heading='Today’s numbers')}\n\n{base_prompt}"
    )
    with db.AgentRun("marky", trigger="daily-metrics") as agent_run:
        answer, _meta = await bot.core(latest=user_msg, history=[], model=None)
        agent_run.records_written = 1 if (answer and answer.strip()) else 0
    from ..personas.base import is_pass_response
    if not answer or is_pass_response(answer):
        return _base.JobResult(True, "Marky: PASS (nothing worth a report).", data={"posted": False, "campaigns": campaigns})
    posted = await ctx.post("DISCORD_CHANNEL_PROMOTION", answer, persona="marky")
    return _base.JobResult(
        True,
        "Marky posted a daily-metrics report to #promotion." if posted else "(couldn't post Marky's report)",
        data={"posted": bool(posted), "campaigns": campaigns},
    )
