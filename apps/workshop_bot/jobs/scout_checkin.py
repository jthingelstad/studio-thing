"""scout-checkin — Scout's agentic state-of-the-slate note.

The replacement for the retired mechanical daily phase-card refresh. Scout
reviews the production slate and posts ONE brief note to #production *only* when
something is worth flagging (a pub date closing in, a stuck production, a needed
decision) — otherwise it replies ``PASS`` and nothing is posted. PASS-by-default,
mirroring ``daily-metrics``. The web production page is the always-current
scoreboard; this is just the nudge when the slate warrants a word.
"""

from __future__ import annotations

import logging

from ..personas.base import is_pass_response
from ..tools import db
from ..tools.content import context
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.scout_checkin")

NAME = "scout-checkin"

_PROMPT = """You are Scout, the producer, looking at the studio's production slate.

{ctx_block}

If something here is worth raising with Jamie in #production right now — a pub
date getting close, a production stuck or blocked, a decision needed — post ONE
brief, specific note (no preamble). If everything's on track and there's nothing
useful to say, reply with exactly `PASS` and nothing will be posted."""


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    # Empty slate → nothing to flag.
    actives = db.list_active_issue_windows()
    others = []
    for ptype in ("article", "podcast", "project"):
        others += db.list_productions(production_type=ptype, status="active")
    if not actives and not others:
        return _base.JobResult(True, "(scout-checkin: empty slate — nothing to flag)")

    bot, channel, reason = _llm_job.resolve_bot_and_channel(
        ctx, "scout", "DISCORD_CHANNEL_PRODUCTION")
    if bot is None:
        return _base.JobResult(True, f"(scout-checkin: scout unavailable — {reason})")

    try:
        ctx_block = context.render_block(context.build_scout_context())
    except Exception:  # noqa: BLE001 — context is best-effort
        ctx_block = "_(slate context unavailable)_"
    user_msg = _PROMPT.format(ctx_block=ctx_block)

    reply = ""
    try:
        with db.AgentRun("scout", trigger="scout-checkin") as agent_run:
            reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
            agent_run.record_meta(_meta)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
    except Exception:  # noqa: BLE001
        logger.exception("scout-checkin: agent run failed")
        return _base.JobResult(False, "scout-checkin: agent run failed")

    if reply and reply.strip() and not is_pass_response(reply):
        await ctx.post(channel, reply.strip(), persona="scout")
        return _base.JobResult(True, "scout-checkin: posted a slate note", data={"posted": True})
    return _base.JobResult(True, "scout-checkin: PASS (nothing to flag)", data={"posted": False})
