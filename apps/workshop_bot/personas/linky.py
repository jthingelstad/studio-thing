"""Linky — Pinboard curation.

Adds one Linky-specific override on top of the shared :class:`PersonaBot`
loop: a Discord-reply listener that turns Jamie's reply to a research
card into a Pinboard description-write. The reply text is saved verbatim
to that bookmark's description; the URL's tags and ``toread`` flag are
untouched (so Jamie can finish curation in Pinboard — add ``_brief`` if
it's a Brief, clear ``toread`` when it's ready to ship). For
popular-feed cards the URL isn't yet bookmarked; the reply is the
"adopt this — start commentary" gesture, and a new bookmark is created
``toread=yes shared=yes`` with the reply as its description.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import discord

from ..systems.pinboard import client as pinboard_client
from ..tools import db
from .base import PersonaBot

logger = logging.getLogger("workshop.linky")


def _owner_id() -> Optional[str]:
    raw = (os.environ.get("DISCORD_OWNER_USER_ID") or "").strip()
    return raw or None


class LinkyBot(PersonaBot):
    persona = "linky"
    name = "Linky"
    home_channel_env = "DISCORD_CHANNEL_RESEARCH"
    empty_greeting = "Hey — want a curation pass, or asking about a specific link?"
    preferred_model = "sonnet"

    async def on_message(self, message: discord.Message) -> None:  # type: ignore[override]
        # Pre-check: is Jamie replying to one of Linky's #research cards?
        # If so, short-circuit the LLM flow and write his reply text to
        # the Pinboard bookmark's description.
        try:
            if await self._maybe_handle_research_reply(message):
                return
        except Exception:  # noqa: BLE001
            logger.exception("linky: research-reply handler raised")
            # Fall through to normal flow rather than swallow the message.
        await super().on_message(message)

    async def _maybe_handle_research_reply(self, message: discord.Message) -> bool:
        """Return True if this message is a Jamie-reply to a Linky research
        card and the description-write was handled (success or failure both
        return True — the message is "consumed" either way so the LLM
        doesn't also reply to it)."""
        if message.guild is None or self.user is None:
            return False
        if message.author == self.user or message.author.bot:
            return False

        owner = _owner_id()
        if owner is None or str(message.author.id) != owner:
            return False

        ref = message.reference
        ref_id = getattr(ref, "message_id", None) if ref is not None else None
        if not ref_id:
            return False

        row = db.lookup_research_message(str(ref_id))
        if row is None:
            return False

        url = row.get("url") or ""
        fallback_title = row.get("title") or None
        reply_text = (message.content or "").strip()
        if not reply_text:
            # Empty reply — react with ❓ so Jamie knows it landed but did nothing.
            try:
                await message.add_reaction("❓")
            except discord.DiscordException:
                pass
            return True

        try:
            res = await asyncio.to_thread(
                pinboard_client.set_description, url, reply_text,
                fallback_title=fallback_title,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("linky: set_description failed for %s", url)
            try:
                await message.add_reaction("❌")
                await message.reply(
                    f"Sorry — couldn't save to Pinboard: `{type(exc).__name__}: {exc}`"[:1900],
                    mention_author=False, suppress_embeds=True,
                )
            except discord.DiscordException:
                pass
            return True

        # Pick the reaction based on what happened.
        created = bool(res.get("created"))
        ok = res.get("result_code") == "done"
        try:
            await message.add_reaction("📌" if created and ok else ("✅" if ok else "⚠️"))
        except discord.DiscordException:
            pass
        logger.info(
            "linky: research reply -> set_description url=%s created=%s ok=%s",
            url, created, ok,
        )
        return True
