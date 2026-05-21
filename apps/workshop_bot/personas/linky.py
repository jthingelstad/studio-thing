"""Linky — Pinboard curation.

Adds three Linky-specific overrides on top of the shared
:class:`PersonaBot` loop, all feeding off the ``linky_research_messages``
table:

1. **Reply listener.** Jamie replies to one of Linky's per-link research
   cards in ``#research``; the reply text is saved verbatim as that
   bookmark's Pinboard description. Tags and the ``toread`` flag are
   untouched (so Jamie finishes curation in Pinboard — add ``_brief`` if
   it's a Brief, clear ``toread`` when ready to ship). For discovery-
   source cards the URL isn't yet bookmarked; the reply auto-creates a
   ``toread=yes shared=yes`` bookmark with the reply as its description.
2. **Save-reaction listener.** Jamie reacts ✅ or 👍 to a research card.
   On **discovery-feed** cards Linky saves the URL to Pinboard as
   ``toread=yes shared=yes`` with a blank description (puts it INTO
   the toread queue); the card gets a 📌 reaction back. On
   **toread-source** cards Linky clears the ``toread`` flag (takes it
   OUT of the queue) while preserving title / description / tags /
   shared; the card gets a 👍 reaction back. The two paths mirror each
   other — same gesture, opposite ends of the toread pipeline.
3. **Briefly-reaction listener.** Jamie reacts ⏩ to *any* card; Linky
   ensures the URL is bookmarked AND tagged ``_brief``. Discovery cards
   create the bookmark fresh (``toread=yes shared=yes``, empty
   description); toread cards merge ``_brief`` into the existing tag
   list while preserving title / description / toread / shared. The
   card gets 🔖 back so it's visually distinct from a regular save.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import discord

from ..systems.pinboard import client as pinboard_client
from ..tools import db
from ..tools.feeds.feed_registry import DISCOVERY_FEEDS
from .base import Deps, PersonaBot
from .commands import register_linky_commands

logger = logging.getLogger("workshop.linky")


def _owner_id() -> Optional[str]:
    raw = (os.environ.get("DISCORD_OWNER_USER_ID") or "").strip()
    return raw or None


# Reactions Jamie can drop on a discovery-feed card to save it to
# Pinboard without typing a reply. Each one means "yes, save this —
# blank description, I'll finish it in Pinboard if at all."
_SAVE_REACTIONS = {"✅", "👍"}

# A third gesture: save the URL AND tag it as `_brief`. Works on any
# card (discovery or toread) — for discovery it creates the bookmark
# with the `_brief` tag; for toread it merges `_brief` into the
# existing tag list. The 🔖 ack distinguishes "Briefly save" from
# the regular 📌 "saved" reaction.
_BRIEF_REACTION = "⏩"
_BRIEF_ACK = "🔖"


# Sources whose URLs aren't yet in Jamie's Pinboard, so a save-gesture
# (reaction or reply) creates a new bookmark. Derived from the registry
# so adding a feed is a single edit in ``tools/feed_registry.py`` —
# no parallel set to maintain here. ``toread``-sourced URLs are already
# bookmarked; for those the reply updates the description and the
# save-reaction is a no-op.
_DISCOVERY_SOURCES: frozenset[str] = frozenset(spec.name for spec in DISCOVERY_FEEDS)


def _mark_card_researched(
    row: dict, *, summary: str, fit_note: str,
) -> None:
    """Cross-lane dedup. After Jamie saves a discovery-card URL via
    reaction or reply (which creates a ``toread=yes`` Pinboard bookmark),
    also mark the URL in ``pinboard_research_done`` so the next
    ``pinboard-scan`` toread lane doesn't re-research a URL Linky has
    already written a card for. No-op for toread-source cards — those
    were marked researched at card-post time in
    ``pinboard_scan._process_one``.

    Best-effort: a DB error here is logged but doesn't propagate. The
    save itself already succeeded from Jamie's perspective; a leaked
    re-research is a milder regression than a noisy save failure."""
    if row.get("source") == "toread":
        return
    url = (row.get("url") or "").strip()
    if not url:
        return
    try:
        db.mark_url_researched(
            url=url, title=row.get("title"),
            summary=summary, confidence="✦", fit_note=fit_note,
        )
    except Exception:  # noqa: BLE001
        logger.exception("linky: mark_url_researched failed for %s", url)


class LinkyBot(PersonaBot):
    persona = "linky"
    name = "Linky"
    home_channel_env = "DISCORD_CHANNEL_RESEARCH"
    empty_greeting = "Hey — want a curation pass, or asking about a specific link?"
    preferred_model = "sonnet"
    slash_commands_summary = "/linky commands: scan · research · pile · stats · followup"

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_linky_commands(self)

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
        if ok:
            _mark_card_researched(
                row, summary=reply_text[:500],
                fit_note="saved via reply",
            )
        logger.info(
            "linky: research reply -> set_description url=%s created=%s ok=%s",
            url, created, ok,
        )
        return True

    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent,
    ) -> None:  # type: ignore[override]
        """Dispatch reactions on Linky's research cards by emoji:
        ``✅`` / ``👍`` → save (discovery-only); ``⏩`` → save-and-tag-
        Briefly (works on any source). All other emojis and non-owner
        reactions are ignored."""
        owner = _owner_id()
        if owner is None or str(payload.user_id) != owner:
            return
        emoji = str(payload.emoji)
        row = db.lookup_research_message(str(payload.message_id))
        if row is None:
            return
        if emoji in _SAVE_REACTIONS:
            await self._handle_save_reaction(payload, row)
            return
        if emoji == _BRIEF_REACTION:
            await self._handle_brief_reaction(payload, row)
            return
        # Any other emoji on a card — ignored. (Linky's own ack
        # reactions land here too but get filtered by the owner check
        # above, since ``self.user.id`` isn't ``DISCORD_OWNER_USER_ID``.)

    async def _handle_save_reaction(
        self, payload: discord.RawReactionActionEvent, row: dict,
    ) -> None:
        """✅ / 👍 path: mirror gesture across the toread pipeline.

        - **Discovery cards** → save the URL as ``toread=yes shared=yes``
          with a blank description (puts it INTO the toread queue). Ack 📌.
        - **Toread cards** → clear the ``toread`` flag while preserving
          title / description / tags / shared (takes it OUT). Ack 👍.

        Both paths delegate to a single Pinboard-client helper
        (``bookmark_blank`` vs ``clear_toread``) that owns the
        fetch-merge-write."""
        url = (row.get("url") or "").strip()
        if not url:
            return
        source = row.get("source") or ""

        if source in _DISCOVERY_SOURCES:
            await self._save_discovery_card(payload, row, url)
            return
        if source == "toread":
            await self._save_toread_card(payload, row, url)
            return
        # Unknown source — silently ignore.

    async def _save_discovery_card(
        self, payload: discord.RawReactionActionEvent, row: dict, url: str,
    ) -> None:
        fallback_title = row.get("title") or None
        try:
            res = await asyncio.to_thread(
                pinboard_client.bookmark_blank, url, fallback_title=fallback_title,
            )
        except Exception:  # noqa: BLE001
            logger.exception("linky: bookmark_blank failed for %s", url)
            await self._react_card(payload, "❌")
            return
        ok = res.get("result_code") in ("done", "item already exists")
        await self._react_card(payload, "📌" if ok else "⚠️")
        if ok:
            _mark_card_researched(
                row, summary="saved via reaction (blank description)",
                fit_note="saved via reaction",
            )
        logger.info(
            "linky: save-reaction (discovery) on %s -> created=%s result=%s",
            url, res.get("created"), res.get("result_code"),
        )

    async def _save_toread_card(
        self, payload: discord.RawReactionActionEvent, row: dict, url: str,
    ) -> None:
        try:
            res = await asyncio.to_thread(pinboard_client.clear_toread, url)
        except Exception:  # noqa: BLE001
            logger.exception("linky: clear_toread failed for %s", url)
            await self._react_card(payload, "❌")
            return
        if res.get("error"):
            # Bookmark vanished between the card post and the reaction —
            # nothing to clear. Quietly ack with ⚠️ so Jamie knows the
            # gesture was seen but didn't change anything.
            await self._react_card(payload, "⚠️")
            logger.info("linky: save-reaction (toread) on %s -> no bookmark", url)
            return
        ok = res.get("result_code") == "done"
        await self._react_card(payload, "👍" if ok else "⚠️")
        logger.info(
            "linky: save-reaction (toread) on %s -> cleared=%s result=%s",
            url, ok, res.get("result_code"),
        )

    async def _handle_brief_reaction(
        self, payload: discord.RawReactionActionEvent, row: dict,
    ) -> None:
        """⏩ path: bookmark (if needed) and tag the URL ``_brief``.
        Works on every source — discovery cards create the bookmark
        fresh, toread cards merge ``_brief`` into the existing tag
        list while preserving title / description / toread / shared."""
        url = (row.get("url") or "").strip()
        if not url:
            return
        fallback_title = row.get("title") or None

        try:
            res = await asyncio.to_thread(
                pinboard_client.tag_as_brief, url, fallback_title=fallback_title,
            )
        except Exception:  # noqa: BLE001
            logger.exception("linky: tag_as_brief failed for %s", url)
            await self._react_card(payload, "❌")
            return
        ok = res.get("result_code") == "done"
        await self._react_card(payload, _BRIEF_ACK if ok else "⚠️")
        if ok:
            _mark_card_researched(
                row, summary="saved via ⏩ (tagged _brief)",
                fit_note="saved via ⏩ Briefly reaction",
            )
        logger.info(
            "linky: brief-reaction on %s -> created=%s tags=%r result=%s",
            url, res.get("created"), res.get("tags"), res.get("result_code"),
        )

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
