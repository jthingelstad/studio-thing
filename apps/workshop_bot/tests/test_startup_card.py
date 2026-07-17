"""Tests for Eddy's startup card.

``on_ready`` formats a one-line readiness card via
:func:`startup.format_persona_line`. Eddy carries the deployment header
(git hash + dirty flag) on top of his line.
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

from apps.workshop_bot.tools.discord import startup


def _fake_bot(name="Eddy", persona="eddy"):
    bot = MagicMock()
    bot.name = name
    bot.persona = persona
    return bot


class FormatPersonaLineTests(unittest.TestCase):
    def test_clean_persona_line_is_just_the_status_line(self):
        """Clean boot: a single bare line ``✓ **Eddy** online``. No
        channel list (operator noise), no command list."""
        bot = _fake_bot()
        rows = [
            ("DISCORD_CHANNEL_EDITORIAL", "editorial", []),
            ("DISCORD_CHANNEL_WORKSHOP", "workshop", []),
            ("DISCORD_CHANNEL_CHATTER", "chatter", []),
        ]
        line = startup.format_persona_line(bot, rows)
        self.assertEqual(line, "✓ **Eddy** online")
        # Specifically — channels are NOT listed when everything is clean.
        self.assertNotIn("#editorial", line)
        self.assertNotIn("#workshop", line)
        self.assertNotIn("#chatter", line)

    def test_persona_line_with_issue_surfaces_only_the_broken_channel(self):
        bot = _fake_bot()
        rows = [
            ("DISCORD_CHANNEL_EDITORIAL", "editorial", []),
            ("DISCORD_CHANNEL_WORKSHOP", None, ["env var not set"]),
        ]
        line = startup.format_persona_line(bot, rows)
        self.assertTrue(line.startswith("⚠️ **Eddy** online — "))
        self.assertIn("env var not set", line)
        # The clean #editorial is NOT echoed — only the broken row is.
        self.assertNotIn("#editorial", line)

    def test_header_prepended_when_lead_persona(self):
        bot = _fake_bot()
        rows = [("DISCORD_CHANNEL_EDITORIAL", "editorial", [])]
        line = startup.format_persona_line(
            bot,
            rows,
            header="**workshop-bot online** — `abc1234`",
        )
        lines = line.split("\n")
        self.assertEqual(lines[0], "**workshop-bot online** — `abc1234`")
        self.assertEqual(lines[1], "✓ **Eddy** online")
        # No third line — no command summary rendered any more.
        self.assertEqual(len(lines), 2)

    def test_commands_summary_param_is_accepted_but_ignored(self):
        """Back-compat: callers that still pass ``commands_summary``
        (legacy code paths) shouldn't break — the kwarg is accepted but
        the slash-verb list is no longer rendered."""
        bot = _fake_bot()
        rows = [("DISCORD_CHANNEL_EDITORIAL", "editorial", [])]
        line = startup.format_persona_line(
            bot,
            rows,
            commands_summary="/eddy commands: foo · bar",
        )
        self.assertEqual(line, "✓ **Eddy** online")
        self.assertNotIn("/eddy commands", line)
        self.assertNotIn("↳", line)


class AuditOneTests(unittest.TestCase):
    def test_audit_one_returns_per_env_rows(self):
        import os

        bot = _fake_bot(name="Eddy", persona="eddy")
        bot.get_channel = MagicMock(return_value=None)
        # The audit checks the env vars in CHANNELS_BY_PERSONA["eddy"].
        orig = {
            k: os.environ.get(k)
            for k in (
                "DISCORD_CHANNEL_EDITORIAL",
                "DISCORD_CHANNEL_WORKSHOP",
                "DISCORD_CHANNEL_CHATTER",
            )
        }
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
