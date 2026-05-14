"""Linky — Pinboard curation.

Adds two Linky-specific overrides on top of the shared :class:`PersonaBot`
loop, both feeding off the ``linky_research_messages`` table:

1. **Reply listener.** Jamie replies to one of Linky's per-link research
   cards in ``#research``; the reply text is saved verbatim as that
   bookmark's Pinboard description. Tags and the ``toread`` flag are
   untouched (so Jamie finishes curation in Pinboard — add ``_brief`` if
   it's a Brief, clear ``toread`` when ready to ship). For popular-feed
   cards the URL isn't yet bookmarked; the reply auto-creates a
   ``toread=yes shared=yes`` bookmark with the reply as its description.
2. **Reaction listener.** Jamie reacts ✅ or 👍 to a popular-feed
   research card; Linky saves the URL to Pinboard as ``toread=yes
   shared=yes`` with a blank description (Jamie can finish in Pinboard
   later or just leave it as a queued read). The card gets a 📌
   reaction back so Jamie can see it landed. Toread-source cards
   already point at a bookmarked URL; ✅/👍 on those is a no-op.
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


# Reactions Jamie can drop on a discovery-feed card (popular / lobsters)
# to save it to Pinboard without typing a reply. Each one means "yes,
# save this — blank description, I'll finish it in Pinboard if at all."
_SAVE_REACTIONS = {"✅", "👍"}

# Sources whose URLs aren't yet in Jamie's Pinboard, so a save-gesture
# (reaction or reply) creates a new bookmark. `toread`-sourced URLs are
# already bookmarked — for those, the reply updates the description and
# the save-reaction is a no-op.
_DISCOVERY_SOURCES = {"popular", "lobsters"}


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

    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent,
    ) -> None:  # type: ignore[override]
        """When Jamie reacts ✅ / 👍 to one of Linky's popular-feed research
        cards, save the URL to Pinboard as ``toread=yes shared=yes`` with
        a blank description. Toread-source cards already point at a
        bookmarked URL — those reactions are no-ops.
        """
        owner = _owner_id()
        if owner is None or str(payload.user_id) != owner:
            return
        if str(payload.emoji) not in _SAVE_REACTIONS:
            return
        row = db.lookup_research_message(str(payload.message_id))
        if row is None:
            return
        if row.get("source") not in _DISCOVERY_SOURCES:
            # Toread cards point at an already-bookmarked URL.
            return
        url = (row.get("url") or "").strip()
        if not url:
            return
        title = row.get("title") or url

        # Acknowledge / save in one path to keep the order of side effects
        # readable: lookup → maybe-save → react.
        try:
            existing = await asyncio.to_thread(pinboard_client.posts_get, url)
        except Exception:  # noqa: BLE001
            existing = None
            logger.exception("linky: posts_get failed during save-reaction for %s", url)

        ack_emoji = "📌"
        if existing and (existing.get("posts") or []):
            # Already bookmarked — nothing to write; just acknowledge.
            await self._react_card(payload, ack_emoji)
            logger.info("linky: save-reaction on %s (already bookmarked)", url)
            return

        try:
            res = await asyncio.to_thread(
                pinboard_client.posts_add,
                url=url, title=title, description="",
                tags="", toread=True, shared=True, replace=False,
            )
            ok = res.get("result_code") == "done"
            await self._react_card(payload, ack_emoji if ok else "⚠️")
            logger.info(
                "linky: save-reaction on %s -> posts_add result=%s",
                url, res.get("result_code"),
            )
        except Exception:  # noqa: BLE001
            logger.exception("linky: posts_add failed during save-reaction for %s", url)
            await self._react_card(payload, "❌")

    async def _react_card(
        self, payload: discord.RawReactionActionEvent, emoji: str,
    ) -> None:
        """Add a reaction to the card the user just reacted to. Best-effort;
        a missing channel / fetch error is logged but doesn't propagate."""
        try:
            channel = self.get_channel(payload.channel_id)
            if channel is None:
                channel = await self.fetch_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            await msg.add_reaction(emoji)
        except discord.DiscordException:
            logger.exception("linky: couldn't react %s on message %s",
                             emoji, payload.message_id)
        except Exception:  # noqa: BLE001
            logger.exception("linky: unexpected error reacting %s on message %s",
                             emoji, payload.message_id)
