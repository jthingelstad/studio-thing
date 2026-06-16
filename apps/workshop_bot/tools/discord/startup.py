"""Startup self-check + per-persona announcements.

Each persona's ``on_ready`` audits its own channels and posts a single
readiness line to ``#chatter`` under its own avatar. Eddy additionally
posts a deployment header (git hash + dirty flag) at the top of the
sequence, and — once the post-startup task in ``bot.py`` has waited
for everyone — posts a follow-up "⚠️ X not ready" line if any persona
missed the ready window.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

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
    "scout": [("DISCORD_CHANNEL_PRODUCTION", "primary"),
              ("DISCORD_CHANNEL_WORKSHOP",   "workshop"),
              ("DISCORD_CHANNEL_CHATTER",  "chatter")],
    # Thingy (the public reader-facing bridge) moved to its own process —
    # see apps/thingy_bridge/.
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


def audit_one(bot: "PersonaBot") -> list[tuple[str, str | None, list[str]]]:
    """Audit a single bot's channels — list of (env_key, channel_name, issues)."""
    env_keys = [k for k, _ in CHANNELS_BY_PERSONA.get(bot.persona, [])]
    return [_check_one(bot, k) for k in env_keys]


def audit(bots: Iterable["PersonaBot"]) -> dict[str, list[tuple[str, str | None, list[str]]]]:
    """Per-bot list of (env_key, channel_name, issues). Legacy helper —
    each persona's ``on_ready`` calls :func:`audit_one` for its own bot."""
    return {bot.persona: audit_one(bot) for bot in bots}


def format_persona_line(
    bot: "PersonaBot",
    audit_rows: list[tuple[str, str | None, list[str]]],
    *,
    header: Optional[str] = None,
    commands_summary: Optional[str] = None,  # accepted, ignored — see below
) -> str:
    """Build the one-line readiness card a single persona posts to #chatter.

    Clean case: ``✓ {Name} online`` — that's it. The channels-and-perms
    audit only surfaces when something is broken; a healthy persona
    doesn't list its channels (it's just operator noise in #chatter).

    Optional ``header`` prepends a deployment line (Eddy uses this for
    the git hash so a restart is operator-visible).

    ``commands_summary`` is accepted for backward compatibility but
    no longer rendered — repeating the slash verb list on every boot
    is operator noise; the channel itself documents available commands."""
    issues_only: list[str] = []
    for env_key, name, issues in audit_rows:
        if not issues:
            continue
        label = f"#{name}" if name else env_key
        issues_only.append(f"{label} ({'; '.join(issues)})")
    marker = "✓" if not issues_only else "⚠️"
    if issues_only:
        line = f"{marker} **{bot.name}** online — " + " · ".join(issues_only)
    else:
        line = f"{marker} **{bot.name}** online"
    out: list[str] = []
    if header:
        out.append(header)
    out.append(line)
    return "\n".join(out)


def format_summary(audit_results: dict, *, hash_str: str, dirty: bool) -> str:
    """Legacy multi-line summary (one card for the whole team). Kept for
    tools that still want a single-card view; per-persona on_ready uses
    :func:`format_persona_line` instead."""
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
    """Post ``message`` to #chatter via ``announcer``'s bot client."""
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
        await channel.send(message, suppress_embeds=True)
        logger.info("startup announcement posted to #%s by %s", getattr(channel, "name", "?"), announcer.name)
    except Exception:  # noqa: BLE001
        logger.exception("failed to post startup announcement")
