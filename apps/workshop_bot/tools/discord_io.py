"""Discord I/O helpers — chunked send for >2000 char replies, attachment download."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

logger = logging.getLogger("workshop.discord_io")

DISCORD_MAX = 2000  # Discord per-message char limit


def split_for_discord(text: str, limit: int = DISCORD_MAX) -> list[str]:
    """Split on paragraph then line boundaries, falling back to hard cuts."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        # Prefer to split at the last paragraph break inside the window.
        cut = remaining.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_chunked(message: "discord.Message", text: str) -> None:
    """Reply to a Discord message, splitting into multiple messages if needed.

    Every chunk is a reply to the same originating message so all chunks
    visually point back to the question that prompted them — a long
    response keeps its chain instead of having half float away.
    """
    if not text.strip():
        await message.reply("(empty response)", mention_author=False)
        return
    for part in split_for_discord(text):
        await message.reply(part, mention_author=False)


async def read_text_attachments(message: "discord.Message", max_bytes: int = 200_000) -> str:
    """Concatenate text content of any .md/.txt attachments. Empty string if none."""
    if not message.attachments:
        return ""
    pieces: list[str] = []
    for att in message.attachments:
        name = (att.filename or "").lower()
        if not (name.endswith(".md") or name.endswith(".txt") or name.endswith(".markdown")):
            logger.info("skipping non-text attachment: %s", att.filename)
            continue
        if att.size > max_bytes:
            logger.warning("attachment %s too large (%d bytes); skipping", att.filename, att.size)
            continue
        data = await att.read()
        try:
            pieces.append(data.decode("utf-8"))
        except UnicodeDecodeError:
            logger.warning("attachment %s not utf-8; skipping", att.filename)
    return "\n\n".join(p.strip() for p in pieces if p.strip())
