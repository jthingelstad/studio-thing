"""garden-checkin — Eddy proactively tends the idea garden.

Part of making the studio *proactive* (AI at the center, not on-call). Eddy
periodically looks at Jamie's seeds garden and, if something's ripe — a cluster
ready to become an article, a pattern across loose seeds, a connection to his
archive worth pursuing — posts ONE brief note to #editorial. Otherwise PASS.
PASS-by-default, mirroring daily-metrics / scout-checkin.
"""

from __future__ import annotations

import logging

from ..personas.base import is_pass_response
from ..tools import db
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.garden_checkin")

NAME = "garden-checkin"

_PROMPT = """You are Eddy, tending Jamie's idea garden.

State of the garden:
- {loose} loose (unclustered) seeds
- {clusters} open clusters

Look at the garden (use seeds__list, seeds__connect, archive__retrieve). If
something is genuinely ripe — a cluster ready to become an article or podcast,
a pattern worth naming across loose seeds, or a strong connection to Jamie's own
past writing he should pursue — post ONE brief, specific note to #editorial (no
preamble). Remember: you develop the idea; Jamie writes it. If nothing is ripe
enough to be worth interrupting him, reply with exactly `PASS`."""


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    loose = [s for s in db.seed_list(status="open") if s.get("cluster_id") is None]
    clusters = db.seed_cluster_list(status="open")
    if not loose and not clusters:
        return _base.JobResult(True, "(garden-checkin: empty garden — nothing to tend)")

    bot, channel, reason = _llm_job.resolve_bot_and_channel(
        ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(True, f"(garden-checkin: eddy unavailable — {reason})")

    user_msg = _PROMPT.format(loose=len(loose), clusters=len(clusters))
    reply = ""
    try:
        with db.AgentRun("eddy", trigger="garden-checkin") as agent_run:
            reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
            agent_run.record_meta(_meta)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
    except Exception:  # noqa: BLE001
        logger.exception("garden-checkin: agent run failed")
        return _base.JobResult(False, "garden-checkin: agent run failed")

    if reply and reply.strip() and not is_pass_response(reply):
        await ctx.post(channel, reply.strip(), persona="eddy")
        return _base.JobResult(True, "garden-checkin: surfaced a ripe idea", data={"posted": True})
    return _base.JobResult(True, "garden-checkin: PASS (nothing ripe)", data={"posted": False})
