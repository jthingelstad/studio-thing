"""Tests for PersonaBot routing + peer-reaction slot rule.

These exercise pure-Python parts of ``personas/base.py`` against fake
discord.py shapes. Full ``on_message`` dispatch isn't tested
end-to-end (it requires async signal handling + channel cache) but
the message-classification and slot rule are testable in isolation.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _install_stubs() -> None:
    if "discord" not in sys.modules:
        discord = types.ModuleType("discord")

        class _Client:
            def __init__(self, *a, **k):
                self.user = None

        class _Intents:
            message_content = False
            guilds = False

            @staticmethod
            def default():
                return _Intents()

        discord.Client = _Client  # type: ignore[attr-defined]
        discord.Intents = _Intents  # type: ignore[attr-defined]
        discord.Message = object  # type: ignore[attr-defined]
        discord.RawReactionActionEvent = object  # type: ignore[attr-defined]
        discord.DiscordException = Exception  # type: ignore[attr-defined]
        abc_mod = types.ModuleType("discord.abc")
        abc_mod.Messageable = object  # type: ignore[attr-defined]
        sys.modules["discord"] = discord
        sys.modules["discord.abc"] = abc_mod

    if "anthropic" not in sys.modules:
        anthropic = types.ModuleType("anthropic")
        anthropic.Anthropic = type("A", (), {"__init__": lambda self, *a, **k: None})  # type: ignore[attr-defined]
        sys.modules["anthropic"] = anthropic


_install_stubs()


from apps.workshop_bot.personas import base  # noqa: E402
from apps.workshop_bot.personas.eddy import EddyBot  # noqa: E402


# ---------- minimal discord.py shapes for testing ----------

class _FakeUser:
    def __init__(self, *, id, bot=False, display_name="", name=""):
        self.id = id
        self.bot = bot
        self.display_name = display_name
        self.name = name


class _FakeMessage:
    def __init__(self, *, author, content, mentions=None, role_mentions=None):
        self.author = author
        self.content = content
        self.mentions = mentions or []
        self.role_mentions = role_mentions or []
        self.id = id(self)
        self.channel = None
        self.guild = object()


class _FakeChannel:
    def __init__(self, messages):
        self._messages = messages
        self.id = id(self)

    def history(self, *, limit, before=None):
        async def gen():
            for m in list(reversed(self._messages))[:limit]:
                yield m
        return gen()


def _run(coro):
    return asyncio.run(coro)


def _make_eddy() -> EddyBot:
    """Construct an EddyBot without touching the real discord.py
    Client.__init__. We bypass the parent constructor and set the
    attributes ``PersonaBot`` actually relies on."""
    bot = EddyBot.__new__(EddyBot)
    bot.user = _FakeUser(id=1000, bot=True, display_name="Weekly Thing - Eddy")
    bot.deps = types.SimpleNamespace(team=None, corpus=None)
    bot.ready_event = asyncio.Event()
    bot._home_channel_id = None
    return bot


# ---------- _parse_body ----------

class ParseBodyTests(unittest.TestCase):
    def setUp(self):
        self.bot = _make_eddy()

    def test_strips_self_mention(self):
        msg = _FakeMessage(
            author=_FakeUser(id=42, bot=False),
            content="<@1000> what about RSS?",
        )
        body, model = self.bot._parse_body(msg)
        self.assertEqual(body, "what about RSS?")
        self.assertIsNone(model)

    def test_strips_nick_mention(self):
        msg = _FakeMessage(
            author=_FakeUser(id=42, bot=False),
            content="<@!1000> hello",
        )
        body, model = self.bot._parse_body(msg)
        self.assertEqual(body, "hello")

    def test_recognizes_model_flag_haiku(self):
        msg = _FakeMessage(
            author=_FakeUser(id=42, bot=False),
            content="<@1000> --haiku tell me about #287",
        )
        body, model = self.bot._parse_body(msg)
        self.assertEqual(model, "haiku")
        self.assertNotIn("--haiku", body)

    def test_recognizes_model_flag_opus(self):
        msg = _FakeMessage(
            author=_FakeUser(id=42, bot=False),
            content="critique this --opus please",
        )
        body, model = self.bot._parse_body(msg)
        self.assertEqual(model, "opus")
        self.assertNotIn("--opus", body)

    def test_no_flag_returns_none(self):
        msg = _FakeMessage(
            author=_FakeUser(id=42, bot=False),
            content="hello",
        )
        _body, model = self.bot._parse_body(msg)
        self.assertIsNone(model)

    def test_multiple_mention_forms_handled(self):
        msg = _FakeMessage(
            author=_FakeUser(id=42, bot=False),
            content="<@1000> <@!1000> three things",
        )
        body, _model = self.bot._parse_body(msg)
        self.assertEqual(body, "three things")


# ---------- _can_react_to_peer slot rule ----------

class CanReactToPeerTests(unittest.TestCase):
    def setUp(self):
        self.bot = _make_eddy()

    def test_no_human_anchor_means_no_react(self):
        # Channel has only bot messages — no human anchor in window.
        ch = _FakeChannel([
            _FakeMessage(
                author=_FakeUser(id=2000, bot=True),
                content="bot 1 says",
            ),
            _FakeMessage(
                author=_FakeUser(id=3000, bot=True),
                content="bot 2 says",
            ),
        ])
        self.assertFalse(_run(self.bot._can_react_to_peer(ch)))

    def test_human_anchor_with_no_self_post_can_react(self):
        ch = _FakeChannel([
            _FakeMessage(
                author=_FakeUser(id=42, bot=False),
                content="Jamie's question",
            ),
            _FakeMessage(
                author=_FakeUser(id=2000, bot=True),
                content="other bot replied",
            ),
        ])
        self.assertTrue(_run(self.bot._can_react_to_peer(ch)))

    def test_human_anchor_with_self_post_blocked(self):
        # Eddy already posted since the human anchor — slot used.
        ch = _FakeChannel([
            _FakeMessage(
                author=_FakeUser(id=42, bot=False),
                content="Jamie's question",
            ),
            _FakeMessage(
                author=_FakeUser(id=1000, bot=True),  # self
                content="Eddy already replied",
            ),
            _FakeMessage(
                author=_FakeUser(id=2000, bot=True),
                content="another bot",
            ),
        ])
        self.assertFalse(_run(self.bot._can_react_to_peer(ch)))

    def test_history_failure_returns_false(self):
        class _Boom:
            def history(self, *, limit, before=None):
                async def gen():
                    raise RuntimeError("boom")
                    yield  # pragma: no cover
                return gen()
        self.assertFalse(_run(self.bot._can_react_to_peer(_Boom())))


# ---------- home channel resolution ----------

class HomeChannelTests(unittest.TestCase):
    def test_no_env_var_means_not_home(self):
        bot = _make_eddy()
        bot._home_channel_id = None
        self.assertFalse(bot._is_home_channel(12345))

    def test_matching_id_is_home(self):
        bot = _make_eddy()
        bot._home_channel_id = 999
        self.assertTrue(bot._is_home_channel(999))
        self.assertFalse(bot._is_home_channel(1000))


# ---------- model resolution cascade ----------

class ResolveModelTests(unittest.TestCase):
    def test_override_wins_over_preferred(self):
        bot = _make_eddy()
        bot.preferred_model = "opus"  # type: ignore[misc]
        self.assertEqual(bot._resolve_model("sonnet"), "sonnet")

    def test_preferred_wins_over_default_when_no_override(self):
        bot = _make_eddy()
        bot.preferred_model = "opus"  # type: ignore[misc]
        # _resolve_model(None) -> preferred -> opus
        self.assertEqual(bot._resolve_model(None), "opus")

    def test_falls_back_to_anthropic_default_when_neither(self):
        bot = _make_eddy()
        bot.preferred_model = None  # type: ignore[misc]
        # default_model() reads WORKSHOP_DEFAULT_MODEL or returns "haiku"
        original = os.environ.pop("WORKSHOP_DEFAULT_MODEL", None)
        try:
            self.assertEqual(bot._resolve_model(None), "haiku")
        finally:
            if original is not None:
                os.environ["WORKSHOP_DEFAULT_MODEL"] = original


if __name__ == "__main__":
    unittest.main()
