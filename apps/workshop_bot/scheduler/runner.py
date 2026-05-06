"""Run scheduled jobs against the live persona bots.

The runner sits inside the bot process (same asyncio loop) and uses
APScheduler's ``AsyncIOScheduler``. Each job in ``jobs.py`` declares a
cron string and a Python function. At fire time the runner calls the
function with a ``JobContext`` and lets it do the work.

Most handlers do their job in pure Python — fetch, format, post. The
ones that need LLM judgment call ``ctx.bot(persona).core(...)`` directly.
The runner doesn't make that decision; the handler does.

A failed job logs the error and posts a short notice to its channel so
Jamie sees it without tailing logs. It does not crash the bot.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import TYPE_CHECKING, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..tools import db, discord_io
from . import jobs as jobs_module

if TYPE_CHECKING:
    from ..personas.base import PersonaBot
    from ..personas.team import TeamRegistry

logger = logging.getLogger("workshop.scheduler")


class JobContext:
    """Per-fire context handed to each job function."""

    def __init__(self, *, team: "TeamRegistry", job: jobs_module.JobSpec) -> None:
        self.team = team
        self.job = job

    def channel(self, env_var: str, *, persona: Optional[str] = None):
        """Resolve a Discord channel id from an env var.

        When ``persona`` is given, the channel object is bound to that
        bot's client so ``channel.send`` posts as that persona. Without
        ``persona``, falls back to any bot that can see the channel —
        only safe for channels every persona has send permission on
        (e.g. #chatter).
        """
        cid_raw = (os.environ.get(env_var) or "").strip()
        if not cid_raw:
            logger.warning("scheduler: %s not set; %s skipped", env_var, self.job.id)
            return None
        try:
            cid = int(cid_raw)
        except ValueError:
            logger.warning("scheduler: %s=%r not a channel id", env_var, cid_raw)
            return None
        if persona is not None:
            bot = self.team.bots.get(persona)
            if bot is None or bot.user is None:
                logger.warning("scheduler: persona %r not available for %s", persona, self.job.id)
                return None
            ch = bot.get_channel(cid)
            if ch is None:
                logger.warning("scheduler: channel %s not visible to %s", cid, persona)
            return ch
        # Any persona's client can resolve the channel (they share the guild).
        for bot in self.team.bots.values():
            if bot.user is None:
                continue
            ch = bot.get_channel(cid)
            if ch is not None:
                return ch
        logger.warning("scheduler: channel %s not visible to any persona", cid)
        return None

    def bot(self, persona: str) -> Optional["PersonaBot"]:
        return self.team.bots.get(persona)

    async def post(self, channel, text: str, *, suppress_embeds: bool = False) -> None:
        """Post (chunked) to a Discord channel."""
        if not text or not text.strip():
            return
        for chunk in discord_io.split_for_discord(text):
            await channel.send(chunk, suppress_embeds=suppress_embeds)


class Runner:
    def __init__(self, team: "TeamRegistry") -> None:
        self.team = team
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self) -> None:
        self.scheduler = AsyncIOScheduler()
        n_added = 0
        for job in jobs_module.JOBS:
            if not job.enabled:
                logger.info("scheduler: skipping disabled job %s", job.id)
                continue
            try:
                trigger = CronTrigger.from_crontab(job.cron, timezone=job.timezone)
            except ValueError as exc:
                logger.error("scheduler: bad cron %r on %s: %s", job.cron, job.id, exc)
                continue
            self.scheduler.add_job(
                self._run,
                trigger=trigger,
                id=job.id,
                args=[job],
                name=job.id,
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
            )
            n_added += 1
        self.scheduler.start()
        logger.info("scheduler: started with %d job(s)", n_added)

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            logger.info("scheduler: stopped")

    async def fire_once(self, job_id: str) -> None:
        """Manually fire a job by id (CLI / debugging)."""
        job = jobs_module.by_id(job_id)
        if job is None:
            raise ValueError(f"unknown job id: {job_id}")
        await self._run(job)

    async def _run(self, job: jobs_module.JobSpec) -> None:
        logger.info("scheduler: firing %s", job.id)
        ctx = JobContext(team=self.team, job=job)
        with db.AgentRun("scheduler", trigger=f"scheduled:{job.id}") as run:
            try:
                await job.func(ctx)
                run.records_written = 1
                logger.info("scheduler: %s ok", job.id)
            except Exception as exc:  # noqa: BLE001
                run.error = f"{type(exc).__name__}: {exc}"
                logger.exception("scheduler: %s failed", job.id)
                # Best-effort post a notice somewhere visible.
                ch = ctx.channel("DISCORD_CHANNEL_CHATTER")
                if ch is not None:
                    try:
                        await ctx.post(
                            ch,
                            f"⚠️ scheduled job `{job.id}` hit an error: "
                            f"`{type(exc).__name__}: {exc}`",
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("scheduler: also failed to post error notice")


# ---- CLI: inspect configured jobs ----
#
# Manual job firing (the previous `--once <job_id>` flag) needed a live
# Discord-connected team registry, which a standalone CLI can't provide.
# Drop it; ``Runner.fire_once`` is still callable in-process if a future
# slash command needs it.

def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List configured jobs and where they post.",
    )
    return parser


def main() -> int:
    parser = _build_argparser()
    args = parser.parse_args()
    if args.list:
        for job in jobs_module.JOBS:
            mark = "✓" if job.enabled else "✗"
            print(
                f"{mark} {job.id:32} {job.cron:20} -> "
                f"{job.func.__module__}.{job.func.__name__}"
            )
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
