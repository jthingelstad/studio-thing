"""Linky — link curation. Two-channel surface:

- ``#research`` carries items with commitment from Jamie (Pinboard
  ``toread`` bookmarks, including the Feedbin starred mirror). State:
  CONSIDERING.
- ``#discovery`` carries items Linky surfaces from discovery feeds
  (today: Pinboard popular). State: PROPOSED — no Pinboard bookmark
  yet.

Each Linky card represents a link in some lifecycle state. Jamie's
gestures move the link through states; the same gesture means the same
thing in both channels, the implementation just differs based on where
the link starts.

Five gestures, all routed through the ``linky_research_messages`` row:

1. **Reply with commentary** → set/update the bookmark's description.
   On a discovery card the bookmark is created with the text as the
   description; on a research card the existing description is replaced.
   Ack: 📌 (created) or ✅ (updated).
2. **➕** — Save for consideration → CONSIDERING.
   Discovery: create bookmark ``toread=yes shared=yes`` with blank
   description; ack 📌. Research: already CONSIDERING; ack ⚠️.
3. **⏩** — Earmark as Briefly → +BRIEF.
   Discovery: create bookmark + tag ``_brief``. Research: merge
   ``_brief`` into existing tags. Both ack 🔖.
4. **✅** — Reviewed, fine link, nothing to do → REVIEWED.
   Discovery: record ``judged_interesting=0`` with note ``reviewed-fine``
   in ``pinboard_popular_seen`` so the URL doesn't re-surface.
   Research: clear the ``toread`` flag, keep the bookmark as archive.
   Both ack 👀.
5. **🛑** — Remove from consideration → REJECTED.
   Discovery: record ``judged_interesting=0`` with note ``rejected``
   (stronger editorial signal than ✅).
   Research: delete the Pinboard bookmark entirely.
   Both ack 🚫.

Reaction errors ack ❌; no-op edge cases (re-saving an already-saved
link, deleting a bookmark that's already gone) ack ⚠️.

The five gestures describe LINK lifecycle, not Pinboard mechanics —
the bot syncs to Pinboard today, but a future non-Pinboard backend
just swaps the implementations of ``bookmark_blank`` / ``tag_as_brief``
/ ``set_description`` / ``clear_toread`` / ``delete_bookmark``.
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


# Link-lifecycle gestures. Each emoji has ONE meaning across both
# channels — the implementation differs only because the starting
# state does (no Pinboard bookmark for a PROPOSED #discovery item;
# bookmark exists for a CONSIDERING #research item).
#
# ➕ — "Save for consideration." Move PROPOSED → CONSIDERING.
#       Discovery: create bookmark `toread=yes shared=yes`, blank desc.
#       Research:  no-op (already CONSIDERING). Acks ⚠️.
# ⏩ — "Earmark as Briefly." Move (PROPOSED|CONSIDERING) → +BRIEF.
#       Discovery: create bookmark + tag `_brief`.
#       Research:  merge `_brief` into existing tags.
# ✅ — "Reviewed, fine link, nothing to do." Move → REVIEWED.
#       Discovery: record judged_interesting=0 with note 'reviewed-fine'.
#       Research:  clear `toread` flag, keep the bookmark.
# 🛑 — "Remove from consideration." Move → REJECTED.
#       Discovery: record judged_interesting=0 with note 'rejected'.
#       Research:  delete the Pinboard bookmark entirely.
#
# Linky's acks: 📌 saved · 🔖 briefed · 👀 reviewed · 🚫 removed ·
#                ⚠️ no-op edge · ❌ error.
_SAVE_REACTION = "➕"
_BRIEF_REACTION = "⏩"
_REVIEWED_REACTION = "✅"
_REJECT_REACTION = "🛑"

_SAVE_ACK = "📌"
_BRIEF_ACK = "🔖"
_REVIEWED_ACK = "👀"
_REJECT_ACK = "🚫"


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
        """Dispatch reactions on Linky's research/discovery cards by emoji.

        Each gesture has one meaning across both channels:
        ``➕`` save · ``⏩`` brief · ``✅`` reviewed · ``🛑`` reject.
        Implementation differs by the row's ``source`` (the starting
        state — PROPOSED for discovery, CONSIDERING for toread).

        All other emojis and non-owner reactions are ignored.
        """
        owner = _owner_id()
        if owner is None or str(payload.user_id) != owner:
            return
        emoji = str(payload.emoji)
        row = db.lookup_research_message(str(payload.message_id))
        if row is None:
            return
        if emoji == _SAVE_REACTION:
            await self._handle_save_reaction(payload, row)
        elif emoji == _BRIEF_REACTION:
            await self._handle_brief_reaction(payload, row)
        elif emoji == _REVIEWED_REACTION:
            await self._handle_reviewed_reaction(payload, row)
        elif emoji == _REJECT_REACTION:
            await self._handle_reject_reaction(payload, row)
        # Any other emoji on a card — ignored. (Linky's own ack
        # reactions land here too but get filtered by the owner check
        # above, since ``self.user.id`` isn't ``DISCORD_OWNER_USER_ID``.)

    async def _handle_save_reaction(
        self, payload: discord.RawReactionActionEvent, row: dict,
    ) -> None:
        """➕ — Save for consideration. Move PROPOSED → CONSIDERING.

        Discovery: create the Pinboard bookmark `toread=yes shared=yes`
        with blank description; ack 📌.
        Research: no-op — the bookmark already exists; ack ⚠️.
        """
        url = (row.get("url") or "").strip()
        if not url:
            return
        source = row.get("source") or ""

        if source == "toread":
            # Already CONSIDERING — nothing to save again.
            await self._react_card(payload, "⚠️")
            return
        if source not in _DISCOVERY_SOURCES:
            return

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
        await self._react_card(payload, _SAVE_ACK if ok else "⚠️")
        if ok:
            _mark_card_researched(
                row, summary="saved via ➕ (blank description)",
                fit_note="saved via ➕ reaction",
            )
        logger.info(
            "linky: save-reaction on %s -> created=%s result=%s",
            url, res.get("created"), res.get("result_code"),
        )

    async def _handle_brief_reaction(
        self, payload: discord.RawReactionActionEvent, row: dict,
    ) -> None:
        """⏩ — Earmark as Briefly. Move (PROPOSED|CONSIDERING) → +BRIEF.

        Discovery: create bookmark + tag `_brief`.
        Research: merge `_brief` into existing tag list, preserving
        title / description / toread / shared.
        Both ack 🔖.
        """
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

    async def _handle_reviewed_reaction(
        self, payload: discord.RawReactionActionEvent, row: dict,
    ) -> None:
        """✅ — Reviewed, fine link, nothing to do. Move → REVIEWED.

        Discovery: write `judged_interesting=0` with note 'reviewed-fine'
        to ``pinboard_popular_seen`` so the URL won't re-surface from
        the same feed or via cross-source uplift.
        Research: clear the Pinboard `toread` flag, keep the bookmark
        as archive.
        Both ack 👀.
        """
        url = (row.get("url") or "").strip()
        if not url:
            return
        source = row.get("source") or ""

        if source == "toread":
            try:
                res = await asyncio.to_thread(pinboard_client.clear_toread, url)
            except Exception:  # noqa: BLE001
                logger.exception("linky: clear_toread failed for %s", url)
                await self._react_card(payload, "❌")
                return
            if res.get("error"):
                await self._react_card(payload, "⚠️")
                logger.info("linky: reviewed (toread) on %s -> no bookmark", url)
                return
            ok = res.get("result_code") == "done"
            await self._react_card(payload, _REVIEWED_ACK if ok else "⚠️")
            logger.info(
                "linky: reviewed (toread) on %s -> cleared=%s result=%s",
                url, ok, res.get("result_code"),
            )
            return

        if source not in _DISCOVERY_SOURCES:
            return

        # Discovery: record the judgment so future scans / uplift skip it.
        try:
            await asyncio.to_thread(
                db.set_popular_seen_judgment,
                url=url,
                interesting=False,
                note="reviewed-fine",
                title=row.get("title"),
                verdict_source=source,
            )
        except Exception:  # noqa: BLE001
            logger.exception("linky: set_popular_seen_judgment failed for %s", url)
            await self._react_card(payload, "❌")
            return
        await self._react_card(payload, _REVIEWED_ACK)
        logger.info("linky: reviewed (discovery) on %s -> judgment=reviewed-fine", url)

    async def _handle_reject_reaction(
        self, payload: discord.RawReactionActionEvent, row: dict,
    ) -> None:
        """🛑 — Remove from consideration. Move → REJECTED.

        Discovery: write `judged_interesting=0` with note 'rejected' to
        ``pinboard_popular_seen``. (Same URL-doesn't-resurface effect as
        ✅, but the editorial intent — and signal — is stronger.)
        Research: delete the Pinboard bookmark entirely via
        ``posts/delete``.
        Both ack 🚫.
        """
        url = (row.get("url") or "").strip()
        if not url:
            return
        source = row.get("source") or ""

        if source == "toread":
            try:
                res = await asyncio.to_thread(pinboard_client.delete_bookmark, url)
            except Exception:  # noqa: BLE001
                logger.exception("linky: delete_bookmark failed for %s", url)
                await self._react_card(payload, "❌")
                return
            ok = res.get("deleted")
            if not ok and res.get("result_code") == "item not found":
                # Bookmark already gone — treat as a soft success.
                await self._react_card(payload, "⚠️")
                logger.info("linky: reject (toread) on %s -> already gone", url)
                return
            await self._react_card(payload, _REJECT_ACK if ok else "⚠️")
            logger.info(
                "linky: reject (toread) on %s -> deleted=%s result=%s",
                url, ok, res.get("result_code"),
            )
            return

        if source not in _DISCOVERY_SOURCES:
            return

        try:
            await asyncio.to_thread(
                db.set_popular_seen_judgment,
                url=url,
                interesting=False,
                note="rejected",
                title=row.get("title"),
                verdict_source=source,
            )
        except Exception:  # noqa: BLE001
            logger.exception("linky: set_popular_seen_judgment failed for %s", url)
            await self._react_card(payload, "❌")
            return
        await self._react_card(payload, _REJECT_ACK)
        logger.info("linky: reject (discovery) on %s -> judgment=rejected", url)

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
