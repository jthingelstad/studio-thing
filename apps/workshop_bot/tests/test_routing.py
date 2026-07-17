"""Tests for Eddy's PersonaBot routing helpers.

These exercise pure-Python parts of ``personas/base.py`` against fake
discord.py shapes. Full ``on_message`` dispatch isn't tested
end-to-end (it requires async signal handling + channel cache), but
message parsing and model resolution are testable in isolation.
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

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()


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
