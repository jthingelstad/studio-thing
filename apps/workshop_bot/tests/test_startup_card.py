"""Tests for the per-persona startup card (commit 7 of the per-persona
slash-tree split).

Each persona's ``on_ready`` formats its own one-line readiness card via
:func:`startup.format_persona_line`. Eddy as lead carries the
deployment header (git hash + dirty flag) on top of his line.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import startup  # noqa: E402


def _fake_bot(name="Eddy", persona="eddy"):
    bot = MagicMock()
    bot.name = name
    bot.persona = persona
    return bot


class FormatPersonaLineTests(unittest.TestCase):
    def test_clean_persona_line(self):
        bot = _fake_bot()
        rows = [
            ("DISCORD_CHANNEL_EDITORIAL", "editorial", []),
            ("DISCORD_CHANNEL_WORKSHOP", "workshop", []),
            ("DISCORD_CHANNEL_CHATTER", "chatter", []),
        ]
        line = startup.format_persona_line(bot, rows)
        self.assertTrue(line.startswith("✓ **Eddy** online"))
        self.assertIn("#editorial", line)
        self.assertIn("#workshop", line)
        self.assertIn("#chatter", line)

    def test_persona_line_with_issue(self):
        bot = _fake_bot()
        rows = [
            ("DISCORD_CHANNEL_EDITORIAL", "editorial", []),
            ("DISCORD_CHANNEL_WORKSHOP", None, ["env var not set"]),
        ]
        line = startup.format_persona_line(bot, rows)
        self.assertTrue(line.startswith("⚠️ **Eddy** online"))
        self.assertIn("env var not set", line)

    def test_persona_line_with_header_and_commands(self):
        bot = _fake_bot()
        rows = [("DISCORD_CHANNEL_EDITORIAL", "editorial", [])]
        line = startup.format_persona_line(
            bot, rows,
            header="**workshop-bot online** — `abc1234`",
            commands_summary="/eddy commands: foo · bar",
        )
        lines = line.split("\n")
        self.assertEqual(lines[0], "**workshop-bot online** — `abc1234`")
        self.assertTrue(lines[1].startswith("✓ **Eddy** online"))
        self.assertTrue(lines[2].startswith("   ↳ /eddy commands"))


class AuditOneTests(unittest.TestCase):
    def test_audit_one_returns_per_env_rows(self):
        import os
        bot = _fake_bot(name="Linky", persona="linky")
        bot.get_channel = MagicMock(return_value=None)
        # The audit checks the env vars in CHANNELS_BY_PERSONA["linky"].
        orig = {k: os.environ.get(k) for k in ("DISCORD_CHANNEL_RESEARCH",
                                                "DISCORD_CHANNEL_WORKSHOP",
                                                "DISCORD_CHANNEL_CHATTER")}
        try:
            for k in orig:
                os.environ.pop(k, None)
            rows = startup.audit_one(bot)
            # Each row is (env_key, channel_name, issues).
            self.assertEqual(len(rows), 3)
            # Every row has an 'env var is not set' issue.
            for env_key, name, issues in rows:
                self.assertEqual(name, None)
                self.assertTrue(any("not set" in s for s in issues), issues)
        finally:
            for k, v in orig.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
