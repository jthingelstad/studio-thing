"""``daily-metrics`` (Marky) — daily website + subscriber + campaign report.

Scheduled daily 19:00 CT; manual re-fire via ``/marky metrics``.

Each run: (1) for every active campaign, fetch current signups
(Buttondown ref attribution) + traffic (Tinylytics ``?ref=`` source
count), append a ``campaign_metrics`` row, update the campaign's
denormalised ``actual_signups``, and compute the delta vs the prior
row; (2) gather subscriber growth and recent site engagement; (3) if
nothing material moved, **PASS** silently — no "nothing to report"
ack; (4) if something moved, run Marky's agent loop to compose a
terse report and post it to ``#promotion``.

Traffic is read from Tinylytics for the same-day "is this campaign
driving clicks?" lens but is no longer persisted (migration 0013 — the
KPI is signups; traffic noise wasn't pulling its weight).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..personas.base import is_pass_response
from ..systems.buttondown import client as buttondown
from ..systems.tinylytics import client as tinylytics
from ..tools import db
from ..tools.content import context
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.daily_metrics")

NAME = "daily-metrics"

# Attribution-window tiers for `_campaign_window_days`. Fresh campaigns
# want a tight 7d window so a launch spike isn't averaged away; aging
# campaigns want a wider window so a slow trickle is still visible.
_AGE_RECENT_MAX = 10   # ≤ this many days → recent window
_AGE_MID_MAX = 45      # ≤ this many days → mid window; else long
_WINDOW_DEFAULT_DAYS = 14
_WINDOW_RECENT_DAYS = 7
_WINDOW_MID_DAYS = 30
_WINDOW_LONG_DAYS = 60

# Materiality thresholds used by `_moved`. Tweak these to make the daily
# report louder or quieter.
_MIN_MATERIAL_NET = 3       # |subscriber net 7d| at or above → material
_MIN_MATERIAL_CHURNED = 3   # 7d churn at or above → material


def _campaign_window_days(started_at: str | None) -> int:
    """Pick a sensible attribution window for a campaign's age."""
    if not started_at:
        return _WINDOW_DEFAULT_DAYS
    try:
        age = (datetime.now().date() - datetime.strptime(str(started_at)[:10], "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return _WINDOW_DEFAULT_DAYS
    if age <= _AGE_RECENT_MAX:
        return _WINDOW_RECENT_DAYS
    if age <= _AGE_MID_MAX:
        return _WINDOW_MID_DAYS
    return _WINDOW_LONG_DAYS


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
    """Poll each active campaign, append a metrics row, update the
    denormalised ``actual_signups``, return per-campaign snapshots
    with deltas. Traffic stays in the snapshot for the report's
    same-day lens but isn't persisted (migration 0013)."""
    snapshots: list[dict] = []
    for c in db.active_campaigns():
        days = _campaign_window_days(c.get("started_at"))
        traffic = _campaign_traffic(c["ref"], days)
        signups = _campaign_signups(c["ref"], days)
        prev = db.latest_campaign_metric(c["name"]) or {}
        prev_s = prev.get("signups")
        db.insert_campaign_metric(campaign_name=c["name"], signups=signups)
        if signups is not None:
            # Denormalise onto the campaign row so the headline number
            # is one read away — no join, no metric history walk.
            db.set_actual_signups(c["name"], int(signups))
        d_s = (signups - prev_s) if (signups is not None and isinstance(prev_s, int)) else None
        snapshots.append({
            "name": c["name"], "ref": c["ref"], "window_days": days,
            "traffic": traffic, "signups": signups,
            "delta_signups": d_s,
            "cost": c.get("cost"),
            "platform": c.get("platform"),
            "copy": (c.get("copy") or None),
            "is_first_poll": not prev,
        })
    return snapshots


def _growth_moved(growth: dict) -> bool:
    """Did subscriber growth move materially this week? — a non-trivial
    net change in either direction, or a churn spike."""
    net = int(growth.get("net") or 0)
    churned = int(growth.get("churned") or 0)
    return abs(net) >= _MIN_MATERIAL_NET or churned >= _MIN_MATERIAL_CHURNED


def _campaigns_moved(campaigns: list[dict]) -> bool:
    """Did any campaign show a material signal? — a first poll or any
    delta vs the prior row."""
    for c in campaigns:
        if c["is_first_poll"]:
            return True
        if (c["delta_signups"] or 0) != 0:
            return True
    return False


def _moved(growth: dict, campaigns: list[dict]) -> bool:
    """Did anything material move? Composition of the two lenses above."""
    return _growth_moved(growth) or _campaigns_moved(campaigns)


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    try:
        with _base.job_lock([f"job:{NAME}"], NAME):
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

            bot, channel, reason = _llm_job.resolve_bot_and_channel(
                ctx, "marky", "DISCORD_CHANNEL_PROMOTION"
            )
            if bot is None:
                return _base.JobResult(
                    True, f"(daily-metrics: something moved but {reason} — not posted)",
                    data={"posted": False, "campaigns": campaigns},
                )

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
            numbers_block = context.render_block(payload, heading="Today's numbers")
            user_msg = (
                f"{context.render_block(marky_ctx)}\n\n"
                f"{numbers_block}\n\n{base_prompt}"
            )
            with db.AgentRun("marky", trigger="daily-metrics") as agent_run:
                answer, _meta = await bot.core(latest=user_msg, history=[], model=None)
                agent_run.record_meta(_meta)
                agent_run.records_written = 1 if (answer and answer.strip()) else 0
            if not answer or is_pass_response(answer):
                return _base.JobResult(True, "Marky: PASS (nothing worth a report).", data={"posted": False, "campaigns": campaigns})
            posted = await ctx.post("DISCORD_CHANNEL_PROMOTION", answer, persona="marky")
            return _base.JobResult(
                True,
                "Marky posted a daily-metrics report to #promotion." if posted else "(couldn't post Marky's report)",
                data={"posted": bool(posted), "campaigns": campaigns},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `daily-metrics` already running ({exc.holder_desc}).")
