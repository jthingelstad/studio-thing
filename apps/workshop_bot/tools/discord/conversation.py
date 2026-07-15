"""Build Anthropic message history from a Discord channel.

Fetches the last N messages before a given message, keeping only the user
and the bot itself, plus messages from other persona bots (so #chatter and
#workshop carry the cross-agent visibility the multi-agent design assumes).
Coalesces consecutive same-role messages and trims leading assistant turns
so the result is a valid Anthropic conversation prefix.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import discord

logger = logging.getLogger("workshop.conversation")

DEFAULT_LIMIT = 8
MENTION_RE = re.compile(r"<@!?\d+>")


def strip_mentions(text: str) -> str:
    return MENTION_RE.sub("", text or "").strip()


def short_bot_name(display_name: str) -> str:
    """`Weekly Thing - Eddy` → `Eddy`. Falls back to the raw name."""
    parts = (display_name or "").rsplit(" - ", 1)
    return parts[-1].strip() or display_name


def coalesce_messages(raw: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Coalesce consecutive same-role turns and trim any leading assistant
    turns so the result is a valid Anthropic conversation prefix.

    Shared between ``build_history`` (single-persona path) and
    ``team._build_round_history`` (team-round path); the rule should
    not differ between them.
    """
    coalesced: list[list[str]] = []
    for role, content in raw:
        if coalesced and coalesced[-1][0] == role:
            coalesced[-1][1] = coalesced[-1][1] + "\n\n" + content
        else:
            coalesced.append([role, content])
    while coalesced and coalesced[0][0] == "assistant":
        coalesced.pop(0)
    return [{"role": role, "content": content} for role, content in coalesced]


async def build_history(
    channel: "discord.abc.Messageable",
    *,
    before: Optional["discord.Message"],
    bot_user_id: int,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, str]]:
    """Return Anthropic-shaped messages list for the conversation prefix.

    Self messages → role=assistant. Everything else (real users and OTHER
    persona bots) → role=user. Other bots are prefixed with `[Name]` so the
    persona can tell who's who. This is what makes #chatter and #workshop
    actually work — agents see each other's recent messages.

    Drops messages that are empty after mention-stripping, coalesces
    consecutive same-role turns, and trims leading assistant turns so the
    result is a valid Anthropic prompt prefix.
    """
    raw: list[tuple[str, str]] = []
    try:
        async for msg in channel.history(limit=limit, before=before):
            content = strip_mentions(msg.content)
            if not content:
                continue
            if msg.author.id == bot_user_id:
                raw.append(("assistant", content))
            elif msg.author.bot:
                speaker = short_bot_name(msg.author.display_name or msg.author.name)
                raw.append(("user", f"[{speaker}] {content}"))
            else:
                raw.append(("user", content))
    except Exception:  # noqa: BLE001
        logger.warning(
            "history fetch failed; continuing without prior context",
            exc_info=True,
        )
        return []
    raw.reverse()  # oldest first
    return coalesce_messages(raw)
