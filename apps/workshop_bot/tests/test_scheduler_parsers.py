"""Tests for the LLM-output parsers in ``scheduler/handlers``.

Currently covers ``strip_json_fences`` (used by Patty's Thursday
member.json compose). Used to be ad-hoc inline code that could silently
stall a job on malformed LLM output; pulling it out as a helper and
pinning the edge cases here.
"""

from __future__ import annotations

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


from apps.workshop_bot.scheduler import handlers  # noqa: E402


class StripJsonFencesTests(unittest.TestCase):
    def test_passthrough_when_no_fences(self):
        self.assertEqual(handlers.strip_json_fences('{"a": 1}'), '{"a": 1}')

    def test_strips_simple_fences(self):
        out = handlers.strip_json_fences('```\n{"a": 1}\n```')
        self.assertEqual(out, '{"a": 1}')

    def test_strips_json_label(self):
        out = handlers.strip_json_fences('```json\n{"a": 1}\n```')
        self.assertEqual(out, '{"a": 1}')

    def test_uppercase_label(self):
        out = handlers.strip_json_fences('```JSON\n{"a": 1}\n```')
        self.assertEqual(out, '{"a": 1}')

    def test_trailing_whitespace_inside_close_fence(self):
        # The original ad-hoc stripping mishandled this — the closing
        # fence had to be the very last characters, so any trailing
        # whitespace from the LLM broke parsing.
        out = handlers.strip_json_fences('```json\n{"a": 1}\n```   \n')
        self.assertEqual(out, '{"a": 1}')

    def test_leading_blank_line(self):
        out = handlers.strip_json_fences('\n\n```\n{"a": 1}\n```')
        self.assertEqual(out, '{"a": 1}')

    def test_empty_input(self):
        self.assertEqual(handlers.strip_json_fences(""), "")
        self.assertEqual(handlers.strip_json_fences(None), "")  # type: ignore[arg-type]

    def test_no_close_fence_left_alone(self):
        # If the LLM emits a stray opening fence without a close, leave
        # it. We'd rather fail JSON parsing on a recognizable input than
        # silently corrupt the payload.
        original = "```json\n{\"a\": 1"
        self.assertEqual(handlers.strip_json_fences(original), original.strip())


if __name__ == "__main__":
    unittest.main()
