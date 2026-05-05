"""Tests for ``tools/conversation``.

Includes the regression test for the ``_short_bot_name`` rename: a
build_history pass over channel content that includes a peer bot's
message must not crash. (One of those crashes shipped in production
before this test existed.)
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _install_stubs() -> None:
    if "discord" not in sys.modules:
        discord = types.ModuleType("discord")
        discord.Client = object  # type: ignore[attr-defined]
        discord.Intents = type("I", (), {"default": staticmethod(lambda: types.SimpleNamespace(message_content=False, guilds=False))})  # type: ignore[attr-defined]
        discord.Message = object  # type: ignore[attr-defined]
        discord.DiscordException = Exception  # type: ignore[attr-defined]
        abc_mod = types.ModuleType("discord.abc")
        abc_mod.Messageable = object  # type: ignore[attr-defined]
        sys.modules["discord"] = discord
        sys.modules["discord.abc"] = abc_mod


_install_stubs()


from apps.workshop_bot.tools import conversation  # noqa: E402


# ---------- minimal fakes for discord.py history iteration ----------

class _FakeAuthor:
    def __init__(self, *, id, bot=False, display_name="", name=""):
        self.id = id
        self.bot = bot
        self.display_name = display_name
        self.name = name


class _FakeMessage:
    def __init__(self, *, author, content):
        self.author = author
        self.content = content


class _FakeChannel:
    def __init__(self, messages: list[_FakeMessage], *, raise_on_history: bool = False):
        # ``messages`` is oldest-first; discord.py's history() yields
        # newest-first by default.
        self._messages = messages
        self._raise = raise_on_history

    async def _async_iter(self, items):
        for item in items:
            yield item

    def history(self, *, limit, before=None):
        if self._raise:
            async def gen():  # noqa: ANN202
                raise RuntimeError("history fetch failed")
                yield  # pragma: no cover
            return gen()
        # newest-first
        ordered = list(reversed(self._messages))[:limit]
        return self._async_iter(ordered)


def _run(coro):
    return asyncio.run(coro)


# ---------- tests ----------

class CoalesceMessagesTests(unittest.TestCase):
    def test_consecutive_same_role_merge(self):
        out = conversation.coalesce_messages([
            ("user", "first"),
            ("user", "second"),
            ("assistant", "reply"),
        ])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["content"], "first\n\nsecond")
        self.assertEqual(out[1]["content"], "reply")

    def test_trims_leading_assistant_turns(self):
        out = conversation.coalesce_messages([
            ("assistant", "reply 1"),
            ("assistant", "reply 2"),
            ("user", "question"),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["role"], "user")

    def test_empty_input_is_empty(self):
        self.assertEqual(conversation.coalesce_messages([]), [])

    def test_all_assistant_input_returns_empty(self):
        out = conversation.coalesce_messages([
            ("assistant", "a"),
            ("assistant", "b"),
        ])
        self.assertEqual(out, [])


class StripMentionsTests(unittest.TestCase):
    def test_strips_user_and_nick(self):
        self.assertEqual(
            conversation.strip_mentions("hi <@123> and <@!456>"),
            "hi  and",
        )

    def test_handles_none_safely(self):
        self.assertEqual(conversation.strip_mentions(None), "")


class BuildHistoryTests(unittest.TestCase):
    """The original regression: a peer-bot message used to crash because
    the internal callsite called ``_short_bot_name`` while the function
    had been renamed to ``short_bot_name``. This pins the fix."""

    def test_peer_bot_message_does_not_crash(self):
        bot_id = 100
        peer_id = 200
        human_id = 300
        msgs = [
            _FakeMessage(
                author=_FakeAuthor(id=human_id, bot=False),
                content="hey there",
            ),
            _FakeMessage(
                author=_FakeAuthor(
                    id=peer_id, bot=True, display_name="Weekly Thing - Marky", name="marky"
                ),
                content="dropping by",
            ),
            _FakeMessage(
                author=_FakeAuthor(id=bot_id, bot=True, display_name="Weekly Thing - Eddy"),
                content="my reply",
            ),
        ]
        history = _run(
            conversation.build_history(
                _FakeChannel(msgs), before=None, bot_user_id=bot_id, limit=10,
            )
        )
        # Peer bot rendered with its short name; self message is assistant.
        roles = [m["role"] for m in history]
        contents = [m["content"] for m in history]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        self.assertTrue(any("[Marky]" in c for c in contents))
        self.assertTrue(any("hey there" in c for c in contents))

    def test_self_messages_become_assistant_role(self):
        bot_id = 100
        msgs = [
            _FakeMessage(
                author=_FakeAuthor(id=999, bot=False),
                content="ask",
            ),
            _FakeMessage(
                author=_FakeAuthor(id=bot_id, bot=True),
                content="answer",
            ),
        ]
        history = _run(
            conversation.build_history(
                _FakeChannel(msgs), before=None, bot_user_id=bot_id, limit=10,
            )
        )
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertEqual(history[-1]["content"], "answer")

    def test_history_fetch_failure_returns_empty_not_raise(self):
        bot_id = 100
        history = _run(
            conversation.build_history(
                _FakeChannel([], raise_on_history=True),
                before=None, bot_user_id=bot_id, limit=10,
            )
        )
        self.assertEqual(history, [])

    def test_empty_after_mention_strip_skipped(self):
        bot_id = 100
        msgs = [
            _FakeMessage(
                author=_FakeAuthor(id=999, bot=False),
                content="<@100>",  # entirely the mention
            ),
            _FakeMessage(
                author=_FakeAuthor(id=999, bot=False),
                content="real question",
            ),
        ]
        history = _run(
            conversation.build_history(
                _FakeChannel(msgs), before=None, bot_user_id=bot_id, limit=10,
            )
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["content"], "real question")


if __name__ == "__main__":
    unittest.main()
