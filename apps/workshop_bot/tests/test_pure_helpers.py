"""Unit tests for the workshop-bot pure-Python helpers.

These exercise functions that don't need Discord, Anthropic, or SQLite at
runtime — but the modules under test do *import* discord/anthropic at
load time. We install minimal stubs in ``sys.modules`` before the package
gets imported so the test process never needs the real SDKs.

Broader integration runs through ``apps/workshop_bot/eval.py``.
"""

from __future__ import annotations

import sys
import types
import unittest
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _install_stubs() -> None:
    """Stub the heavyweight third-party deps so the package imports cleanly."""
    if "discord" not in sys.modules:
        discord = types.ModuleType("discord")

        class _Client:  # noqa: D401 — stub
            def __init__(self, *args, **kwargs):
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
        discord.DiscordException = Exception  # type: ignore[attr-defined]

        # discord.abc submodule for type annotations like discord.abc.Messageable.
        abc_mod = types.ModuleType("discord.abc")
        abc_mod.Messageable = object  # type: ignore[attr-defined]
        sys.modules["discord"] = discord
        sys.modules["discord.abc"] = abc_mod

    if "anthropic" not in sys.modules:
        anthropic = types.ModuleType("anthropic")

        class _Anthropic:
            def __init__(self, *args, **kwargs):
                pass

        anthropic.Anthropic = _Anthropic  # type: ignore[attr-defined]
        sys.modules["anthropic"] = anthropic


_install_stubs()


from apps.workshop_bot.personas import base  # noqa: E402
from apps.workshop_bot.personas import team as team_mod  # noqa: E402
from apps.workshop_bot.tools import agent_loop, agent_tools, conversation, discord_io  # noqa: E402


class IsPassResponseTests(unittest.TestCase):
    """``is_pass_response`` gates whether a peer reaction goes to the channel.
    False positives are catastrophic — the model's rationale would leak."""

    def test_plain_pass(self):
        self.assertTrue(base.is_pass_response("PASS"))

    def test_lowercase(self):
        self.assertTrue(base.is_pass_response("pass"))

    def test_with_punctuation(self):
        for s in ("PASS.", "pass!", "PASS,", "*PASS*", "**PASS**", "`PASS`", '"pass"'):
            with self.subTest(s=s):
                self.assertTrue(base.is_pass_response(s))

    def test_with_whitespace(self):
        self.assertTrue(base.is_pass_response("  PASS  \n"))

    def test_pass_with_rationale_fails(self):
        # If the model adds rationale we MUST treat it as a real reply,
        # otherwise we'd silently drop a real message.
        self.assertFalse(base.is_pass_response("PASS — nothing to add"))
        self.assertFalse(base.is_pass_response("Pass on this one"))
        self.assertFalse(base.is_pass_response("I'll pass"))

    def test_empty_string(self):
        self.assertFalse(base.is_pass_response(""))

    def test_none_safe(self):
        self.assertFalse(base.is_pass_response(None))  # type: ignore[arg-type]


class SplitForDiscordTests(unittest.TestCase):
    """Discord caps messages at 2000 chars; the splitter must never produce
    a chunk larger than that, and should prefer paragraph/line breaks.
    """

    def test_short_text_passthrough(self):
        out = discord_io.split_for_discord("hello world")
        self.assertEqual(out, ["hello world"])

    def test_splits_at_paragraph_break(self):
        text = "A" * 1500 + "\n\n" + "B" * 1000
        out = discord_io.split_for_discord(text)
        self.assertGreaterEqual(len(out), 2)
        for chunk in out:
            self.assertLessEqual(len(chunk), 2000)
        self.assertTrue(out[0].endswith("A"))
        self.assertTrue(out[1].startswith("B"))

    def test_long_unbroken_text_hard_cuts(self):
        text = "x" * 5000
        out = discord_io.split_for_discord(text)
        for chunk in out:
            self.assertLessEqual(len(chunk), 2000)
        # Round-tripping through the splitter shouldn't lose characters.
        self.assertEqual("".join(out), text)

    def test_custom_limit(self):
        text = "ab cd ef gh ij"
        out = discord_io.split_for_discord(text, limit=5)
        for chunk in out:
            self.assertLessEqual(len(chunk), 5)


class ShortBotNameTests(unittest.TestCase):
    """`Weekly Thing - Marky` → `Marky`. Used in conversation history so each
    persona can tell who's speaking.
    """

    def test_strips_prefix(self):
        self.assertEqual(conversation.short_bot_name("Weekly Thing - Marky"), "Marky")

    def test_no_separator(self):
        self.assertEqual(conversation.short_bot_name("Eddy"), "Eddy")

    def test_blank(self):
        self.assertEqual(conversation.short_bot_name(""), "")

    def test_takes_last_segment(self):
        self.assertEqual(
            conversation.short_bot_name("Some - Bot - Patty"), "Patty"
        )


class StripMentionsTests(unittest.TestCase):
    def test_strips(self):
        self.assertEqual(
            conversation.strip_mentions("hey <@123456> what's up"),
            "hey  what's up".strip(),
        )

    def test_strips_nick_mention(self):
        self.assertEqual(
            conversation.strip_mentions("<@!987654> ping"),
            "ping",
        )

    def test_handles_none(self):
        self.assertEqual(conversation.strip_mentions(None), "")


class TruncateMarkerTests(unittest.TestCase):
    """The truncated tool-result suffix must read as plain text — earlier
    code emitted ``..."[truncated]"`` which made the result invalid JSON."""

    def test_marker_is_plain_text(self):
        big_value = "x" * (agent_loop.MAX_TOOL_RESULT_CHARS + 10)
        agent_tools.SPECS["__test__"] = {
            "name": "__test__",
            "description": "test",
            "input_schema": {"type": "object", "properties": {}},
        }

        def fake(_deps, **_kwargs):
            return big_value

        agent_tools.FUNCS["__test__"] = fake
        try:
            result = agent_loop._execute_tool("__test__", deps=None, raw_input={})
            self.assertIn("[truncated;", result)
            self.assertNotIn('..."[truncated]"', result)
            self.assertLessEqual(
                len(result), agent_loop.MAX_TOOL_RESULT_CHARS + 200
            )
        finally:
            agent_tools.SPECS.pop("__test__", None)
            agent_tools.FUNCS.pop("__test__", None)


class TrimOrderedSetTests(unittest.TestCase):
    """``_trim_ordered_set`` evicts oldest entries first. The prior trim
    relied on plain-set order, which Python sets don't guarantee."""

    def test_trim_oldest(self):
        d: "OrderedDict[int, None]" = OrderedDict()
        for i in range(10):
            d[i] = None
        team_mod._trim_ordered_set(d, cap=4)
        self.assertEqual(list(d.keys()), [6, 7, 8, 9])

    def test_no_trim_when_under_cap(self):
        d: "OrderedDict[int, None]" = OrderedDict()
        for i in range(3):
            d[i] = None
        team_mod._trim_ordered_set(d, cap=10)
        self.assertEqual(list(d.keys()), [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
