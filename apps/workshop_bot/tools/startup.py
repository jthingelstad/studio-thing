"""Startup self-check + announcement.

After all four persona bots fire on_ready, audit each bot's required channels
and basic permissions, then post one summary message to #chatter via the
designated announcer (Eddy by default).
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ..personas.base import PersonaBot

logger = logging.getLogger("workshop.startup")

REPO = Path(__file__).resolve().parents[3]

# persona name -> list of (env var holding channel id, friendly label)
CHANNELS_BY_PERSONA: dict[str, list[tuple[str, str]]] = {
    "eddy":  [("DISCORD_CHANNEL_EDITORIAL",  "primary"),
              ("DISCORD_CHANNEL_WORKSHOP",   "workshop"),
              ("DISCORD_CHANNEL_CHATTER",  "chatter")],
    "marky": [("DISCORD_CHANNEL_PROMOTION",  "primary"),
              ("DISCORD_CHANNEL_WORKSHOP",   "workshop"),
              ("DISCORD_CHANNEL_CHATTER",  "chatter")],
    "patty": [("DISCORD_CHANNEL_SUPPORTERS", "primary"),
              ("DISCORD_CHANNEL_WORKSHOP",   "workshop"),
              ("DISCORD_CHANNEL_CHATTER",  "chatter")],
    "linky": [("DISCORD_CHANNEL_RESEARCH",   "primary"),
              ("DISCORD_CHANNEL_WORKSHOP",   "workshop"),
              ("DISCORD_CHANNEL_CHATTER",  "chatter")],
    # Thingy is a public-facing bridge — it only needs visibility into
    # its own #ask-thingy channel. It deliberately doesn't see #workshop
    # or #chatter (no peer reactions, no operational stream).
    "thingy": [("DISCORD_CHANNEL_ASK_THINGY", "primary")],
}

REQUIRED_PERMS = ("view_channel", "send_messages", "read_message_history")

ANNOUNCER = "eddy"


def git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(out.strip())
    except Exception:  # noqa: BLE001
        return False


def _check_one(bot: "PersonaBot", env_key: str) -> tuple[str, str | None, list[str]]:
    """Return (channel_label_or_id, channel_name_or_None, list_of_issues)."""
    cid_raw = os.environ.get(env_key, "").strip()
    if not cid_raw:
        return env_key, None, [f"{env_key} is not set in .env"]
    try:
        cid = int(cid_raw)
    except ValueError:
        return env_key, None, [f"{env_key}={cid_raw!r} is not a valid channel id"]

    channel = bot.get_channel(cid)
    if channel is None:
        # try a fetch in case the cache hasn't populated for this channel
        return env_key, None, [f"channel id {cid} not visible to {bot.name} (not a member?)"]

    issues: list[str] = []
    guild = getattr(channel, "guild", None)
    me = guild.me if guild is not None else None
    if me is None:
        issues.append("could not resolve bot member in guild")
    else:
        perms = channel.permissions_for(me)
        for perm_name in REQUIRED_PERMS:
            if not getattr(perms, perm_name, False):
                issues.append(f"missing perm: {perm_name}")
    return env_key, getattr(channel, "name", None), issues


def audit(bots: Iterable["PersonaBot"]) -> dict[str, list[tuple[str, str | None, list[str]]]]:
    """Per-bot list of (env_key, channel_name, issues)."""
    out: dict[str, list[tuple[str, str | None, list[str]]]] = {}
    for bot in bots:
        env_keys = [k for k, _ in CHANNELS_BY_PERSONA.get(bot.persona, [])]
        out[bot.persona] = [_check_one(bot, k) for k in env_keys]
    return out


def format_summary(audit_results: dict, *, hash_str: str, dirty: bool) -> str:
    lines = [f"**workshop-bot online** — `{hash_str}`{' (dirty)' if dirty else ''}"]
    any_issue = False
    for persona, rows in audit_results.items():
        bits: list[str] = []
        for env_key, name, issues in rows:
            label = f"#{name}" if name else env_key
            if issues:
                any_issue = True
                bits.append(f"{label} ⚠️ ({'; '.join(issues)})")
            else:
                bits.append(label)
        marker = "✓" if not any(r[2] for r in rows) else "⚠️"
        lines.append(f"{marker} **{persona.capitalize()}** — " + " · ".join(bits))
    if any_issue:
        lines.append("")
        lines.append("⚠️ One or more channels are unreachable or missing permissions. Check `.env` and the Discord role.")
    return "\n".join(lines)


async def announce(announcer: "PersonaBot", message: str) -> None:
    cid_raw = os.environ.get("DISCORD_CHANNEL_CHATTER", "").strip()
    if not cid_raw:
        logger.warning("DISCORD_CHANNEL_CHATTER not set; not posting startup announce")
        return
    try:
        channel = announcer.get_channel(int(cid_raw))
    except ValueError:
        logger.warning("DISCORD_CHANNEL_CHATTER is not a valid id")
        return
    if channel is None:
        logger.warning("chatter channel not visible to announcer %s", announcer.name)
        return
    try:
        await channel.send(message)
        logger.info("startup announcement posted to #%s by %s", getattr(channel, "name", "?"), announcer.name)
    except Exception:  # noqa: BLE001
        logger.exception("failed to post startup announcement")
