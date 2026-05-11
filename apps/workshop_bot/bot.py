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
import random
import signal
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

from .personas.base import Deps
from .personas.eddy import EddyBot
from .personas.linky import LinkyBot
from .personas.marky import MarkyBot
from .personas.patty import PattyBot
from .personas.team import TeamRegistry
from .personas.thingy import ThingyBot
from .scheduler.runner import Runner as SchedulerRunner
from .systems.buttondown.server import ButtondownServer
from .systems.pinboard.server import PinboardServer
from .systems.stripe.server import StripeServer
from .systems.tinylytics.server import TinylyticsServer
from .tools import agent_tools, corpus, db, startup

logger = logging.getLogger("workshop.bot")

# Stagger between persona logins on cold start so 5 simultaneous /users/@me
# calls from the same IP don't trip Discord's CloudFlare global rate limit.
LOGIN_STAGGER_SECONDS = 2.0

# Exponential backoff schedule when a login is rate-limited (Discord error
# 40062). Long by design: 40062 cooldowns can run minutes-to-hours, and
# pounding the endpoint deepens the hole.
RATE_LIMIT_BACKOFFS = (300, 600, 1200, 1800)  # 5m, 10m, 20m, 30m
RATE_LIMIT_BACKOFF_CAP = 1800  # 30m
RATE_LIMIT_JITTER = 0.10  # ±10% so the 5 personas don't wake in lockstep

# Cap discord.py's internal retry-after sleep, applied only around login().
# Without this, a 429 on the login storm triggers 5 retries × Discord's
# retry_after, all from the same IP — the herd we're trying to avoid. We do
# our own slow backoff above instead. Restored to None (discord.py's default,
# wait as long as needed) once login succeeds, so routine post-login calls
# like typing/send/reactions can ride out small cooldowns silently.
HTTP_RATELIMIT_TIMEOUT = 1.0

# Per-persona ceiling on waiting for on_ready before declaring the persona
# missing. With LOGIN_STAGGER_SECONDS=2 between five personas plus normal
# login + gateway + READY latency, fully healthy startups land in <60s.
# 90s leaves slack without paying the full 5m+ rate-limit ladder.
READY_WAIT_SECONDS = 90.0

PERSONAS: list[tuple[str, str, type]] = [
    ("eddy", "DISCORD_TOKEN_EDDY", EddyBot),
    ("linky", "DISCORD_TOKEN_LINKY", LinkyBot),
    ("marky", "DISCORD_TOKEN_MARKY", MarkyBot),
    ("patty", "DISCORD_TOKEN_PATTY", PattyBot),
    # Thingy is the public-facing bridge to the Librarian Lambda. Skipped
    # automatically by collect_tokens() if DISCORD_TOKEN_THINGY isn't set,
    # so the bot still starts cleanly while Jamie creates the Discord app.
    ("thingy", "DISCORD_TOKEN_THINGY", ThingyBot),
]


def configure_logging() -> None:
    level_name = os.environ.get("WORKSHOP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file = os.environ.get(
        "WORKSHOP_LOG_FILE",
        str(Path(__file__).resolve().parent / "logs" / "workshop.log"),
    )
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Always log to file; mirror to stderr only when running interactively
    # (under launchd stderr is a file, so we'd just duplicate into workshop.err).
    handlers: list[logging.Handler] = [logging.FileHandler(log_file)]
    if sys.stderr.isatty():
        handlers.append(logging.StreamHandler(sys.stderr))

    root = logging.getLogger()
    root.setLevel(level)
    for h in handlers:
        h.setFormatter(fmt)
        root.addHandler(h)

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
    registry = agent_tools.ToolRegistry()
    agent_tools.register_local_helpers(registry)
    registry.register_system(ButtondownServer())
    registry.register_system(PinboardServer())
    registry.register_system(StripeServer())
    registry.register_system(TinylyticsServer())
    deps = Deps(corpus=corpus_handle, team=team, registry=registry)

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

    async def _sleep_or_stop(seconds: float) -> bool:
        """Sleep up to ``seconds``, returning True if stop was requested."""
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _start(name: str, client, token: str) -> None:
        attempt = 0
        while not stop_event.is_set():
            # Cap the HTTP retry only around login() so the herd-of-5 cold
            # start fails fast on 40062 instead of compounding into 25 hammered
            # requests. Restore the default after login so routine calls
            # (typing, sends, reactions) can ride out their small cooldowns
            # silently the way discord.py intends.
            client.http.max_ratelimit_timeout = HTTP_RATELIMIT_TIMEOUT
            try:
                await client.login(token)
            except asyncio.CancelledError:
                raise
            except discord.HTTPException as e:
                if getattr(e, "code", None) == 40062 or e.status == 429:
                    base = RATE_LIMIT_BACKOFFS[
                        min(attempt, len(RATE_LIMIT_BACKOFFS) - 1)
                    ] if attempt < len(RATE_LIMIT_BACKOFFS) else RATE_LIMIT_BACKOFF_CAP
                    jitter = base * RATE_LIMIT_JITTER * (2 * random.random() - 1)
                    delay = max(60.0, base + jitter)
                    logger.warning(
                        "[%s] Discord rate-limited login (code=%s); sleeping %.0fs before retry",
                        name, getattr(e, "code", "?"), delay,
                    )
                    if await _sleep_or_stop(delay):
                        return
                    attempt += 1
                    continue
                logger.exception("[%s] login failed (non-rate-limit)", name)
                _request_stop()
                return
            except Exception:
                logger.exception("[%s] login failed", name)
                _request_stop()
                return

            # Logged in. Restore the default so post-login HTTP calls don't
            # surface every short cooldown as RateLimited. Reset backoff and
            # run the gateway. If it drops, we loop back to login() —
            # discord.py's reconnect=True handles transient gateway blips, so
            # we only re-enter on harder failures. Resetting ``attempt`` here
            # (not at top-of-loop) is intentional: a successful login proves
            # we're not in a 40062 hole, so the next gateway-failure cycle
            # should start a fresh rate-limit ladder rather than inherit the
            # last cycle's backoff.
            client.http.max_ratelimit_timeout = None
            attempt = 0
            try:
                await client.connect(reconnect=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[%s] gateway dropped; will re-login", name)
                if await _sleep_or_stop(30):
                    return
                continue
            return  # clean disconnect

    tasks: list[asyncio.Task] = []
    for n, b, t in bots:
        tasks.append(asyncio.create_task(_start(n, b, t), name=f"persona:{n}"))
        # Space out the initial login burst so we don't trip 40062 from the herd.
        if await _sleep_or_stop(LOGIN_STAGGER_SECONDS):
            break

    scheduler_enabled = (
        os.environ.get("WORKSHOP_SCHEDULER_ENABLED", "1").strip() not in ("0", "false", "")
    )
    runner = SchedulerRunner(team, deps=deps) if scheduler_enabled else None

    async def _post_startup() -> None:
        # Wait for each persona's on_ready, but with a per-persona timeout
        # so a stubbornly rate-limited bot (40062 cooldowns can run minutes
        # to hours) doesn't block the scheduler from starting for the
        # personas that did come up. Missing personas will be reported in
        # the audit summary; the scheduler skips jobs whose persona is
        # absent (see scheduler/runner.py JobContext.channel).
        ready_bots: list = []
        missing: list[str] = []
        for name, client, _ in bots:
            try:
                await asyncio.wait_for(
                    client.ready_event.wait(), timeout=READY_WAIT_SECONDS,
                )
                ready_bots.append(client)
            except asyncio.TimeoutError:
                logger.warning(
                    "%s: not ready after %ds; proceeding without it",
                    name, READY_WAIT_SECONDS,
                )
                missing.append(name)
        if not ready_bots:
            logger.error("no personas reached ready in %ds; skipping audit + scheduler", READY_WAIT_SECONDS)
            return
        results = startup.audit(ready_bots)
        summary = startup.format_summary(
            results, hash_str=startup.git_hash(), dirty=startup.git_dirty(),
        )
        if missing:
            summary += f"\n\n⚠️ not ready after {READY_WAIT_SECONDS}s: {', '.join(missing)}"
        logger.info("startup audit:\n%s", summary)
        announcer = next(
            (b for n, b, _ in bots if n == startup.ANNOUNCER and b in ready_bots),
            ready_bots[0],
        )
        await startup.announce(announcer, summary)
        # Start scheduled jobs once we have at least one ready persona —
        # individual jobs gracefully skip if their target persona is
        # missing, so we don't need to wait for everyone.
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
