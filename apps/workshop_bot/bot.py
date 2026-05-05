"""Workshop bot entrypoint.

Run with `python -m apps.workshop_bot.bot` from the repo root.

Spins up four discord.py Client instances (one per persona), each with its
own bot token. The corpus is built once at startup and shared across all
four. Migrations run idempotently every start.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

from .personas.base import Deps
from .personas.eddy import EddyBot
from .personas.linky import LinkyBot
from .personas.marky import MarkyBot
from .personas.patty import PattyBot
from .personas.team import TeamRegistry
from .scheduler.runner import Runner as SchedulerRunner
from .tools import corpus, db, startup

logger = logging.getLogger("workshop.bot")

PERSONAS: list[tuple[str, str, type]] = [
    ("eddy", "DISCORD_TOKEN_EDDY", EddyBot),
    ("linky", "DISCORD_TOKEN_LINKY", LinkyBot),
    ("marky", "DISCORD_TOKEN_MARKY", MarkyBot),
    ("patty", "DISCORD_TOKEN_PATTY", PattyBot),
]


def configure_logging() -> None:
    level_name = os.environ.get("WORKSHOP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # Quiet discord.py's gateway noise unless DEBUG is on.
    if level > logging.DEBUG:
        logging.getLogger("discord").setLevel(logging.WARNING)


def collect_tokens() -> list[tuple[str, str, type]]:
    missing: list[str] = []
    resolved: list[tuple[str, str, type]] = []
    for name, env_key, cls in PERSONAS:
        token = os.environ.get(env_key)
        if not token:
            missing.append(env_key)
            continue
        resolved.append((name, token, cls))
    if missing:
        logger.error("missing Discord tokens: %s", ", ".join(missing))
    return resolved


async def run() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY is not set")
        return 2

    db.run_migrations()
    corpus_handle = corpus.load()
    team = TeamRegistry()
    deps = Deps(corpus=corpus_handle, team=team)

    resolved = collect_tokens()
    if not resolved:
        logger.error("no Discord tokens found; nothing to start")
        return 2

    bots = [(name, cls(deps), token) for (name, token, cls) in resolved]
    for name, b, _ in bots:
        team.register(b)
    logger.info("starting %d persona bot(s): %s", len(bots), ", ".join(n for n, _, _ in bots))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        if not stop_event.is_set():
            logger.info("stop requested; closing clients...")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # Windows
            pass

    async def _start(client, token: str) -> None:
        try:
            await client.start(token)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("client start failed")
            _request_stop()

    tasks = [asyncio.create_task(_start(b, t), name=f"persona:{n}") for n, b, t in bots]

    scheduler_enabled = (
        os.environ.get("WORKSHOP_SCHEDULER_ENABLED", "1").strip() not in ("0", "false", "")
    )
    runner = SchedulerRunner(team) if scheduler_enabled else None

    async def _post_startup() -> None:
        # Wait until every persona has fired on_ready.
        for _, client, _ in bots:
            await client.ready_event.wait()
        results = startup.audit([b for _, b, _ in bots])
        summary = startup.format_summary(
            results, hash_str=startup.git_hash(), dirty=startup.git_dirty(),
        )
        logger.info("startup audit:\n%s", summary)
        announcer = next((b for n, b, _ in bots if n == startup.ANNOUNCER), bots[0][1])
        await startup.announce(announcer, summary)
        # Start scheduled jobs only after every persona is ready, so we don't
        # fire a Marky daily job into a Marky client that hasn't connected.
        if runner is not None:
            try:
                runner.start()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler: failed to start")

    tasks.append(asyncio.create_task(_post_startup(), name="startup-announce"))

    try:
        await stop_event.wait()
    finally:
        if runner is not None:
            try:
                runner.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler: error during shutdown")
        for _, client, _ in bots:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                logger.exception("error while closing client")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return 0


def main() -> int:
    load_dotenv()
    configure_logging()
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
