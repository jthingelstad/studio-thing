"""Linky's Discord-side handlers — reply-to-card descriptions, save reactions,
and Briefly-tag reactions.

Pulled out of ``test_content_jobs.py`` in Batch F of the project-
integrity sweep. These tests exercise ``LinkyBot.on_message`` (the
reply-shortcuts to update a Pinboard description) and
``LinkyBot.on_raw_reaction_add`` (the save / save-and-tag-as-Briefly
gestures). They depend on ``_DBTestCase`` for the
``linky_research_messages`` table the handlers read.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase as _DBTestCase  # noqa: E402


class LinkyReplyHandlerTests(_DBTestCase):
    """LinkyBot's research-reply listener: Jamie's reply to a per-link
    research card writes his text as the Pinboard bookmark's description.
    """

    def setUp(self):
        super().setUp()
        import types
        from apps.workshop_bot.personas.linky import LinkyBot
        self.bot = LinkyBot.__new__(LinkyBot)
        self.bot.user = MagicMock()
        self.bot.user.id = 1000
        self.bot.deps = types.SimpleNamespace(team=None, corpus=None)
        os.environ["DISCORD_OWNER_USER_ID"] = "777"

    def tearDown(self):
        os.environ.pop("DISCORD_OWNER_USER_ID", None)
        super().tearDown()

    def _msg(self, *, author_id, content, reference_id=None):
        m = MagicMock()
        m.guild = object()
        m.author = MagicMock()
        m.author.id = author_id
        m.author.bot = False
        m.author.__eq__ = lambda s, other: False  # not Linky
        m.content = content
        if reference_id is not None:
            m.reference = MagicMock()
            m.reference.message_id = reference_id
        else:
            m.reference = None
        m.add_reaction = AsyncMock()
        m.reply = AsyncMock()
        return m

    def _patch_set(self, *, side_effect=None, return_value=None):
        from apps.workshop_bot.systems.pinboard import client as pbc
        return patch.object(pbc, "set_description",
                            side_effect=side_effect, return_value=return_value)

    def test_non_reply_passes_through(self):
        m = self._msg(author_id=777, content="hi")
        out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertFalse(out)

    def test_reply_to_unknown_message_passes_through(self):
        m = self._msg(author_id=777, content="hi", reference_id=99999)
        out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertFalse(out)

    def test_reply_from_non_owner_passes_through(self):
        db.record_research_message(
            discord_message_id="1001", url="http://x", source="toread",
        )
        m = self._msg(author_id=888, content="hi", reference_id=1001)
        out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertFalse(out)

    def test_jamie_reply_to_toread_card_writes_description(self):
        db.record_research_message(
            discord_message_id="1001", url="http://x", source="toread",
            title="Some Title",
        )
        m = self._msg(
            author_id=777, content="Loved this take.", reference_id=1001,
        )
        with self._patch_set(return_value={
            "result_code": "done", "created": False, "replaced": True,
        }) as p:
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertTrue(out)
        # set_description was called with the URL + Jamie's reply verbatim.
        args, kwargs = p.call_args
        self.assertEqual(args[0], "http://x")
        self.assertEqual(args[1], "Loved this take.")
        self.assertEqual(kwargs["fallback_title"], "Some Title")
        m.add_reaction.assert_awaited_with("✅")

    def test_jamie_reply_to_popular_card_creates_bookmark_with_pin_emoji(self):
        db.record_research_message(
            discord_message_id="1002", url="http://y", source="popular",
            title="Popular Title",
        )
        m = self._msg(author_id=777, content="Bookmark with this take.", reference_id=1002)
        with self._patch_set(return_value={
            "result_code": "done", "created": True, "replaced": False,
        }):
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertTrue(out)
        # 📌 distinguishes "new bookmark created" from "existing one updated".
        m.add_reaction.assert_awaited_with("📌")

    def test_empty_reply_consumed_with_question_mark(self):
        db.record_research_message(
            discord_message_id="1003", url="http://x", source="toread",
        )
        m = self._msg(author_id=777, content="", reference_id=1003)
        with self._patch_set(return_value={"result_code": "done"}) as p:
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        # Consumed (so the LLM doesn't ALSO reply), reacted ❓, but
        # set_description was NOT called.
        self.assertTrue(out)
        p.assert_not_called()
        m.add_reaction.assert_awaited_with("❓")

    def test_set_description_failure_reacts_with_x(self):
        db.record_research_message(
            discord_message_id="1004", url="http://x", source="toread",
        )
        m = self._msg(author_id=777, content="text", reference_id=1004)
        with self._patch_set(side_effect=RuntimeError("boom")):
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertTrue(out)
        m.add_reaction.assert_awaited_with("❌")
        m.reply.assert_awaited()


class LinkySaveReactionTests(_DBTestCase):
    """Owner reactions ✅/👍 on a popular-feed research card → save the
    URL to Pinboard as toread+public with a blank description."""

    def setUp(self):
        super().setUp()
        import types
        from apps.workshop_bot.personas.linky import LinkyBot
        self.bot = LinkyBot.__new__(LinkyBot)
        self.bot.user = MagicMock()
        self.bot.user.id = 1000
        self.bot.deps = types.SimpleNamespace(team=None, corpus=None)
        # Patch _react_card to capture the emoji we'd render onto the card
        # without going through discord fetch_channel / fetch_message.
        self.reactions: list[str] = []
        async def _fake_react(payload, emoji):
            self.reactions.append(emoji)
        self.bot._react_card = _fake_react
        os.environ["DISCORD_OWNER_USER_ID"] = "777"

    def tearDown(self):
        os.environ.pop("DISCORD_OWNER_USER_ID", None)
        super().tearDown()

    def _payload(self, *, user_id, emoji, message_id, channel_id=999):
        p = MagicMock()
        p.user_id = user_id
        p.message_id = message_id
        p.channel_id = channel_id
        p.emoji = MagicMock()
        p.emoji.__str__ = lambda s: emoji
        return p

    def _patch_pinboard(
        self, *, existing_posts=None, add_result=None, add_side_effect=None,
        get_side_effect=None,
    ):
        from apps.workshop_bot.systems.pinboard import client as pbc
        get_mock = MagicMock(return_value={"posts": existing_posts or []})
        if get_side_effect is not None:
            get_mock.side_effect = get_side_effect
        add_mock = MagicMock(return_value=add_result or {"result_code": "done"})
        if add_side_effect is not None:
            add_mock.side_effect = add_side_effect
        return (
            patch.object(pbc, "posts_get", get_mock),
            patch.object(pbc, "posts_add", add_mock),
            add_mock,
        )

    def test_save_reaction_on_popular_creates_bookmark(self):
        db.record_research_message(
            discord_message_id="2001", url="http://p/1", source="popular",
            title="Popular Title",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2001)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs["url"], "http://p/1")
        self.assertEqual(kwargs["description"], "")
        self.assertTrue(kwargs["toread"])
        self.assertTrue(kwargs["shared"])
        self.assertFalse(kwargs["replace"])
        self.assertEqual(self.reactions, ["📌"])

    def test_thumbs_up_works_too(self):
        db.record_research_message(
            discord_message_id="2002", url="http://p/2", source="popular",
        )
        p = self._payload(user_id=777, emoji="👍", message_id=2002)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_called_once()
        self.assertEqual(self.reactions, ["📌"])

    def test_other_emoji_ignored(self):
        db.record_research_message(
            discord_message_id="2003", url="http://p/3", source="popular",
        )
        p = self._payload(user_id=777, emoji="❤️", message_id=2003)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()
        self.assertEqual(self.reactions, [])

    def test_non_owner_reaction_ignored(self):
        db.record_research_message(
            discord_message_id="2004", url="http://p/4", source="popular",
        )
        p = self._payload(user_id=888, emoji="✅", message_id=2004)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()

    def test_toread_card_save_reaction_is_noop(self):
        # Toread URLs are already bookmarked — nothing to do.
        db.record_research_message(
            discord_message_id="2005", url="http://t/1", source="toread",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2005)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()
        self.assertEqual(self.reactions, [])  # no acknowledgment either

    def test_unknown_message_id_ignored(self):
        p = self._payload(user_id=777, emoji="✅", message_id=999999)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()

    def test_already_bookmarked_just_acknowledges(self):
        db.record_research_message(
            discord_message_id="2006", url="http://p/6", source="popular",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2006)
        # posts_get returns an existing bookmark; posts_add should NOT be called.
        get_p, add_p, add_mock = self._patch_pinboard(
            existing_posts=[{"href": "http://p/6"}],
        )
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()
        self.assertEqual(self.reactions, ["📌"])

    def test_posts_add_failure_reacts_with_x(self):
        db.record_research_message(
            discord_message_id="2007", url="http://p/7", source="popular",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2007)
        get_p, add_p, _ = self._patch_pinboard(
            add_side_effect=RuntimeError("boom"),
        )
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        self.assertEqual(self.reactions, ["❌"])

    def test_save_reaction_on_hackernews_card_creates_bookmark(self):
        db.record_research_message(
            discord_message_id="2009", url="https://x.example/hn-link",
            source="hackernews", title="An HN Story",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2009)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        # HN items behave just like Pinboard popular and Lobsters for save.
        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs["url"], "https://x.example/hn-link")
        self.assertEqual(kwargs["title"], "An HN Story")
        self.assertTrue(kwargs["toread"])
        self.assertTrue(kwargs["shared"])
        self.assertEqual(self.reactions, ["📌"])

    def test_save_reaction_on_lobsters_card_creates_bookmark(self):
        db.record_research_message(
            discord_message_id="2008", url="https://kde.org/news",
            source="lobsters", title="KDE Funding",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2008)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        # Lobsters items behave just like Pinboard popular for the save flow.
        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs["url"], "https://kde.org/news")
        self.assertEqual(kwargs["title"], "KDE Funding")
        self.assertTrue(kwargs["toread"])
        self.assertTrue(kwargs["shared"])
        self.assertEqual(self.reactions, ["📌"])

    # ---------- ⭐ Briefly reaction ----------

    def _patch_tag_as_brief(self, *, return_value=None, side_effect=None):
        from apps.workshop_bot.systems.pinboard import client as pbc
        m = MagicMock(return_value=return_value or {
            "result_code": "done", "pinboard_url": "", "created": False,
            "tags": "_brief",
        })
        if side_effect is not None:
            m.side_effect = side_effect
        return patch.object(pbc, "tag_as_brief", m), m

    def test_brief_reaction_on_discovery_card_calls_tag_as_brief(self):
        db.record_research_message(
            discord_message_id="3001", url="https://x.example/d1",
            source="popular", title="A Discovery Item",
        )
        p = self._payload(user_id=777, emoji="⭐", message_id=3001)
        patch_obj, tag_mock = self._patch_tag_as_brief(return_value={
            "result_code": "done", "created": True, "tags": "_brief", "pinboard_url": "",
        })
        patch_obj.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            patch_obj.stop()
        tag_mock.assert_called_once()
        # Positional URL + keyword fallback_title.
        args, kwargs = tag_mock.call_args
        self.assertEqual(args[0], "https://x.example/d1")
        self.assertEqual(kwargs["fallback_title"], "A Discovery Item")
        # 🔖 ack distinguishes Briefly-save from regular save (📌).
        self.assertEqual(self.reactions, ["🔖"])

    def test_brief_reaction_on_toread_card_calls_tag_as_brief(self):
        # Unlike the ✅/👍 save which is discovery-only, ⭐ works on
        # toread cards too — the helper merges `_brief` into the
        # existing bookmark's tags.
        db.record_research_message(
            discord_message_id="3002", url="https://x.example/t1",
            source="toread", title="A Toread Item",
        )
        p = self._payload(user_id=777, emoji="⭐", message_id=3002)
        patch_obj, tag_mock = self._patch_tag_as_brief()
        patch_obj.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            patch_obj.stop()
        tag_mock.assert_called_once()
        self.assertEqual(tag_mock.call_args.args[0], "https://x.example/t1")
        self.assertEqual(self.reactions, ["🔖"])

    def test_brief_reaction_ignored_when_no_card_row(self):
        p = self._payload(user_id=777, emoji="⭐", message_id=999999)
        patch_obj, tag_mock = self._patch_tag_as_brief()
        patch_obj.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            patch_obj.stop()
        tag_mock.assert_not_called()
        self.assertEqual(self.reactions, [])

    def test_brief_reaction_ignored_from_non_owner(self):
        db.record_research_message(
            discord_message_id="3003", url="https://x.example/d2",
            source="popular", title="x",
        )
        p = self._payload(user_id=888, emoji="⭐", message_id=3003)  # not owner
        patch_obj, tag_mock = self._patch_tag_as_brief()
        patch_obj.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            patch_obj.stop()
        tag_mock.assert_not_called()

    def test_brief_reaction_on_already_bookmarked_discovery_merges_tag(self):
        """⭐ on a discovery URL that Jamie ALSO previously bookmarked
        (e.g. he ✅'d it earlier) goes through the tag-merge path —
        ``tag_as_brief`` does the fetch-merge-write, the helper returns
        ``created=False`` and a tag-list with ``_brief`` appended."""
        db.record_research_message(
            discord_message_id="3005", url="https://x.example/d4",
            source="popular", title="Previously bookmarked",
        )
        p = self._payload(user_id=777, emoji="⭐", message_id=3005)
        patch_obj, tag_mock = self._patch_tag_as_brief(return_value={
            "result_code": "done", "created": False, "tags": "ai _brief",
            "pinboard_url": "",
        })
        patch_obj.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            patch_obj.stop()
        tag_mock.assert_called_once()
        # 🔖 ack still fires — Jamie sees that his Briefly intent landed,
        # whether or not the URL was already bookmarked.
        self.assertEqual(self.reactions, ["🔖"])

    def test_brief_reaction_failure_reacts_with_x(self):
        db.record_research_message(
            discord_message_id="3004", url="https://x.example/d3",
            source="popular", title="x",
        )
        p = self._payload(user_id=777, emoji="⭐", message_id=3004)
        patch_obj, _ = self._patch_tag_as_brief(side_effect=RuntimeError("boom"))
        patch_obj.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            patch_obj.stop()
        self.assertEqual(self.reactions, ["❌"])


if __name__ == "__main__":
    unittest.main()
