"""Workshop bot entrypoint.

Run with `python -m apps.workshop_bot.bot` from the repo root.

Spins up five discord.py Client instances (one per author-facing
persona — Scout, Eddy, Linky, Marky, Patty), each with its own bot
token. The corpus is built once at startup and shared across all five.
Migrations run idempotently every start.

The reader-facing Thingy bot lives in a separate process
(`apps/thingy_bridge/`) — see that app's README for the bridge launch
story.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import signal
import sys
import time
from pathlib import Path

import discord
from dotenv import load_dotenv

from .personas.base import Deps
from .personas.eddy import EddyBot
from .personas.linky import LinkyBot
from .personas.marky import MarkyBot
from .personas.patty import PattyBot
from .personas.scout import ScoutBot
from .personas.team import TeamRegistry
from .scheduler.runner import Runner as SchedulerRunner
from .systems.buttondown.server import ButtondownServer
from .systems.pinboard.server import PinboardServer
from .systems.stripe.server import StripeServer
from .systems.tinylytics.server import TinylyticsServer
from .webapp import start_webapp
from .tools import db
from .tools.content import corpus
from .tools.llm import agent_tools, anthropic_client
from .tools.discord import startup

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

# Per-persona gateway-watchdog thresholds. We watch heartbeat-ACK
# staleness via ``bot.latency`` rather than dispatched-event activity:
# Discord sends a HEARTBEAT every ~41s, discord.py updates ``latency``
# on each ACK, so when ACKs stop the value stops changing — that's
# our signal that the connection is silently dead regardless of guild
# activity. Activity-based watchdogs false-fire on quiet private
# guilds (no presence intent → no PRESENCE_UPDATE, no chatter →
# no MESSAGE_CREATE / TYPING_START). 120s ≈ 3× the heartbeat interval,
# with margin for jitter. launchd's KeepAlive watches the PID only,
# so the watchdog's ``os._exit(1)`` is what causes a real respawn.
WATCHDOG_ACK_STALE_SECS = 120.0
WATCHDOG_CHECK_SECS = 30.0
# Grace period after on_ready before enforcing — first ACK can take a
# moment, and reconnects briefly show latency=inf.
WATCHDOG_GRACE_SECS = 90.0

PERSONAS: list[tuple[str, str, type]] = [
    ("eddy", "DISCORD_TOKEN_EDDY", EddyBot),
    ("linky", "DISCORD_TOKEN_LINKY", LinkyBot),
    ("marky", "DISCORD_TOKEN_MARKY", MarkyBot),
    ("patty", "DISCORD_TOKEN_PATTY", PattyBot),
    ("scout", "DISCORD_TOKEN_SCOUT", ScoutBot),
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


async def _gateway_watchdog(
    name: str,
    bot,
    stop_event: asyncio.Event,
    *,
    ack_stale_secs: float = WATCHDOG_ACK_STALE_SECS,
    grace_secs: float = WATCHDOG_GRACE_SECS,
    check_secs: float = WATCHDOG_CHECK_SECS,
) -> None:
    """One heartbeat-ACK watchdog per persona — same shape as
    thingy_bridge's. We track ``bot.latency`` (refreshed on every
    HEARTBEAT_ACK) and exit when it stops changing for ``ack_stale_secs``.
    Heartbeats fire every ~41s regardless of guild activity, so this
    signal is invariant to chatter volume — unlike a dispatched-events
    watchdog, which false-fires on quiet private guilds.

    On miss we ``os._exit(1)`` rather than ``sys.exit`` because the
    asyncio loop may itself be wedged — we want the process gone
    immediately so launchd's KeepAlive respawns it (4 fresh sessions,
    since one dead persona typically means the whole process needs
    cycling).
    """
    last_latency: float | None = None
    last_change_at = time.monotonic()
    non_finite_since: float | None = None

    try:
        await asyncio.wait_for(bot.ready_event.wait(), timeout=READY_WAIT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "[%s] watchdog: not ready within %.0fs; arming anyway",
            name, READY_WAIT_SECONDS,
        )
    armed_at = time.monotonic()
    last_change_at = armed_at
    logger.info(
        "[%s] watchdog: armed (no-ack threshold %.0fs, grace %.0fs)",
        name, ack_stale_secs, grace_secs,
    )

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=check_secs)
            return
        except asyncio.TimeoutError:
            pass

        if bot.is_closed():
            logger.error(
                "[%s] watchdog: bot.is_closed() is True; exiting so launchd restarts us",
                name,
            )
            os._exit(1)

        current = bot.latency  # float seconds, or inf when no WS / no ACK yet
        now = time.monotonic()
        since_armed = now - armed_at
        if not math.isfinite(current):
            # No heartbeat yet, or mid-reconnect. Track *this* episode of
            # non-finite so a brief reconnect blip after the grace window
            # doesn't false-fire — only kill if non-finite has lasted past
            # the threshold AND we're out of the initial grace window.
            if non_finite_since is None:
                non_finite_since = now
            non_finite_for = now - non_finite_since
            if since_armed > grace_secs and non_finite_for > ack_stale_secs:
                logger.error(
                    "[%s] watchdog: bot.latency has been non-finite for "
                    "%.0fs (threshold %.0fs); exiting so launchd restarts us",
                    name, non_finite_for, ack_stale_secs,
                )
                os._exit(1)
            continue

        non_finite_since = None

        if last_latency is None or current != last_latency:
            last_latency = current
            last_change_at = now
            continue

        stale = now - last_change_at
        if since_armed > grace_secs and stale > ack_stale_secs:
            logger.error(
                "[%s] watchdog: bot.latency hasn't changed in %.0fs "
                "(threshold %.0fs); HEARTBEAT_ACKs have stopped — "
                "exiting so launchd restarts us",
                name, stale, ack_stale_secs,
            )
            os._exit(1)


async def run() -> int:
    resolved = collect_tokens()
    if not resolved:
        logger.error("no Discord tokens found; nothing to start")
        return 2

    try:
        anthropic_client.validate_keys(name for name, _, _ in resolved)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    report = db.run_migrations()
    applied_count = len(report.applied) + len(report.skipped)
    latest = report.latest_id or "(none)"
    logger.info(
        "workshop.db ready (%d applied, latest: %s, schema_hash: %s)",
        applied_count, latest, report.short_hash or "(unhashed)",
    )
    corpus_handle = corpus.load()
    team = TeamRegistry()
    registry = agent_tools.ToolRegistry()
    agent_tools.register_local_helpers(registry)
    registry.register_system(ButtondownServer())
    registry.register_system(PinboardServer())
    registry.register_system(StripeServer())
    registry.register_system(TinylyticsServer())
    deps = Deps(corpus=corpus_handle, team=team, registry=registry)

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

    # One watchdog per persona. If any of them goes silent-zombie, the
    # whole process exits so launchd respawns with fresh sessions for
    # all five — restarting one Client mid-flight is messier than a
    # full cycle.
    for n, b, _ in bots:
        tasks.append(asyncio.create_task(
            _gateway_watchdog(n, b, stop_event),
            name=f"watchdog:{n}",
        ))

    scheduler_enabled = (
        os.environ.get("WORKSHOP_SCHEDULER_ENABLED", "1").strip() not in ("0", "false", "")
    )
    runner = SchedulerRunner(team, deps=deps) if scheduler_enabled else None

    async def _post_startup() -> None:
        # Each persona's on_ready posts its own startup card to #chatter
        # (under its own avatar). This task just waits for ready, logs
        # a consolidated audit, and — if any persona missed the window
        # — has Eddy post a single "⚠️ not ready" follow-up so #chatter
        # captures the gap.
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
            logger.error("no personas reached ready in %ds; skipping scheduler", READY_WAIT_SECONDS)
            return
        # Log the consolidated audit for postmortem readability.
        results = startup.audit(ready_bots)
        consolidated = startup.format_summary(
            results, hash_str=startup.git_hash(), dirty=startup.git_dirty(),
        )
        if missing:
            consolidated += f"\n\n⚠️ not ready after {READY_WAIT_SECONDS}s: {', '.join(missing)}"
        logger.info("startup audit:\n%s", consolidated)
        # If any persona missed the window, have Eddy (lead) post a
        # single follow-up note so the gap shows up in #chatter.
        if missing:
            announcer = next(
                (b for n, b, _ in bots if n == startup.ANNOUNCER and b in ready_bots),
                ready_bots[0],
            )
            try:
                await startup.announce(
                    announcer,
                    f"⚠️ not ready after {READY_WAIT_SECONDS}s: {', '.join(missing)}",
                )
            except Exception:  # noqa: BLE001
                logger.exception("startup: couldn't post missing-personas note")
        # Start scheduled jobs once we have at least one ready persona —
        # individual jobs gracefully skip if their target persona is
        # missing, so we don't need to wait for everyone.
        if runner is not None:
            try:
                runner.start()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler: failed to start")

    tasks.append(asyncio.create_task(_post_startup(), name="startup-announce"))

    # Private (tailnet-only) web app — Jamie's operator surface (Scout slate, growing). Non-fatal.
    try:
        await start_webapp(deps=deps)
    except Exception:  # noqa: BLE001
        logger.exception("webapp: failed to start (non-fatal)")

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
