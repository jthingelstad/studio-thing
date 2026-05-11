"""Concrete scheduled-job handlers.

The only scheduled surface today is the per-persona heartbeat — a
default-PASS wake-up that posts only when the persona has something
concrete to surface. The earlier "rituals" (Friday curation, Monday
subscriber report, Thursday member.json) were removed pending a
deliberate redesign of how the team helps Jamie assemble each issue.

Conventions still in force:

  - Handlers don't raise. The runner catches exceptions and posts a
    failure notice; handlers focus on the happy path.
  - Anything posted to Discord goes through ``ctx.post(text, ...)`` so
    the runner can chunk it consistently.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Literal

HeartbeatResult = Literal["pass", "posted", "disabled", "skipped", "error"]

from ..personas.base import is_pass_response
from ..tools import anthropic_client, db


if TYPE_CHECKING:
    from .runner import JobContext

logger = logging.getLogger("workshop.scheduler.handlers")


# ============================================================
# Heartbeat — shared LLM-driven scheduled check-in
# ============================================================

def _heartbeats_enabled() -> bool:
    """Honor ``WORKSHOP_HEARTBEATS_ENABLED`` (default 1)."""
    raw = (os.environ.get("WORKSHOP_HEARTBEATS_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


async def heartbeat(ctx: "JobContext", persona: str) -> HeartbeatResult:
    """A persona's scheduled wake-up turn.

    Loads ``prompts/<persona>/heartbeat.md`` as the user message, runs
    the persona's full agent loop, and posts the answer to its home
    channel — unless the answer is ``PASS`` (the default), in which case
    the heartbeat exits silently. Heartbeats are wrapped in their own
    ``db.AgentRun`` so the persona's scheduled token spend is visible
    alongside its mention-driven turns.

    Wired into ``scheduler/jobs.py`` as
    ``functools.partial(handlers.heartbeat, persona='<name>')`` per
    each persona's heartbeat JobSpec. Also reachable from the
    ``/workshop heartbeat`` slash command, which uses the return value
    to ack the invoker honestly (PASS vs posted vs error).
    """
    if not _heartbeats_enabled():
        logger.info("heartbeat: disabled via WORKSHOP_HEARTBEATS_ENABLED=0; skipping %s", persona)
        return "disabled"

    bot = ctx.bot(persona)
    if bot is None:
        logger.warning("heartbeat: persona %r not registered; skipping", persona)
        return "skipped"

    try:
        prompt_text = anthropic_client.load_prompt(f"{persona}-heartbeat")
    except OSError as exc:
        logger.warning("heartbeat: prompt for %r unreadable: %s", persona, exc)
        return "skipped"

    model = (os.environ.get("WORKSHOP_HEARTBEAT_MODEL") or "haiku").strip() or None

    answer = ""
    with db.AgentRun(persona, trigger="heartbeat") as run:
        try:
            answer, _meta = await bot.core(
                latest=prompt_text, history=[], model=model
            )
        except Exception as exc:  # noqa: BLE001
            run.error = f"{type(exc).__name__}: {exc}"
            logger.exception("heartbeat %s: agent loop failed", persona)
            return "error"
        run.records_written = 0 if (not answer or is_pass_response(answer)) else 1

    if not answer or is_pass_response(answer):
        logger.info("heartbeat %s: PASS", persona)
        return "pass"

    home_env = bot.home_channel_env
    if not home_env:
        logger.warning("heartbeat %s: no home_channel_env; dropping reply", persona)
        return "skipped"
    channel = ctx.channel(home_env, persona=persona)
    if channel is None:
        return "skipped"
    await ctx.post(channel, answer, suppress_embeds=True)
    return "posted"


# ============================================================
# Content-loop jobs — fired from cron via a thin bridge
# ============================================================

# Maps a job name to its async ``run(ctx, **kwargs)`` entrypoint. Kept
# lazy so importing scheduler.handlers doesn't pull the whole jobs graph
# at module load.
def _content_job_runner(name: str):
    from ..jobs import update_draft

    return {
        "update-draft": update_draft.run,
    }.get(name)


async def content_job(ctx: "JobContext", *, job: str, **kwargs) -> str:
    """Run a content-loop job (``apps/workshop_bot/jobs/<job>.py``) on the
    scheduler. Bridges the scheduler's ``JobContext`` (which carries
    ``team`` and, post-Step-4, ``deps``) to the jobs package's own
    ``JobContext``. The job itself posts whatever it needs to a channel;
    this handler just logs the outcome."""
    from ..jobs import _base as jobs_base

    runner = _content_job_runner(job)
    if runner is None:
        logger.warning("content_job: no runner registered for %r", job)
        return "skipped"
    deps = getattr(ctx, "deps", None)
    job_ctx = jobs_base.JobContext(deps=deps, trigger="scheduled")
    result = await runner(job_ctx, **kwargs)
    logger.info("content_job %s -> ok=%s: %s", job, getattr(result, "ok", "?"), getattr(result, "message", ""))
    return "ok" if getattr(result, "ok", False) else "noop"
