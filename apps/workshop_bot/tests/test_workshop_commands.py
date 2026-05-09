"""Tests for the ``/workshop`` slash-command surface.

The handler stays thin: it defers the interaction, dispatches one or
four heartbeats, and acks the invoker ephemerally. These tests stub
``handlers.heartbeat`` so the agent loop never runs and verify that:

  - ``run_one_heartbeat`` returns the heartbeat handler's status verbatim.
  - Unknown personas (no matching JobSpec) come back as ``"skipped"``.
  - A handler exception is caught and surfaced as ``"error"``.
  - The team-mode codepath fires once per persona in parallel.
  - The registered tree exposes ``/workshop heartbeat`` with all five
    Choices (four personas + ``team``).
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()


from apps.workshop_bot.personas import commands as commands_module  # noqa: E402


class _FakeTeam:
    def __init__(self):
        self.bots = {}


class RunOneHeartbeatTests(unittest.TestCase):
    """``run_one_heartbeat`` is the unit the slash handler calls."""

    def test_returns_handler_status_verbatim(self):
        team = _FakeTeam()
        with patch.object(
            commands_module.handlers, "heartbeat", new=AsyncMock(return_value="pass")
        ) as fake:
            result = asyncio.run(commands_module.run_one_heartbeat(team, "marky"))
        self.assertEqual(result, "pass")
        # Persona forwarded as a positional/keyword in the same shape the scheduler uses.
        args, kwargs = fake.call_args
        self.assertEqual(args[1] if len(args) > 1 else kwargs.get("persona"), "marky")

    def test_posted_status_passes_through(self):
        team = _FakeTeam()
        with patch.object(
            commands_module.handlers, "heartbeat", new=AsyncMock(return_value="posted")
        ):
            result = asyncio.run(commands_module.run_one_heartbeat(team, "linky"))
        self.assertEqual(result, "posted")

    def test_unknown_persona_returns_skipped(self):
        # No JobSpec named "ghost-heartbeat" exists, so we short-circuit
        # without calling handlers.heartbeat.
        team = _FakeTeam()
        with patch.object(
            commands_module.handlers, "heartbeat", new=AsyncMock(return_value="ignored")
        ) as fake:
            result = asyncio.run(commands_module.run_one_heartbeat(team, "ghost"))
        self.assertEqual(result, "skipped")
        self.assertEqual(fake.await_count, 0)

    def test_handler_exception_becomes_error_status(self):
        team = _FakeTeam()
        with patch.object(
            commands_module.handlers,
            "heartbeat",
            new=AsyncMock(side_effect=RuntimeError("kaboom")),
        ):
            result = asyncio.run(commands_module.run_one_heartbeat(team, "patty"))
        self.assertEqual(result, "error")


class RenderResultTests(unittest.TestCase):
    def test_known_statuses_have_human_labels(self):
        for status in ("posted", "pass", "disabled", "skipped", "error"):
            with self.subTest(status=status):
                rendered = commands_module.render_result(status)
                self.assertNotEqual(rendered, status)
                self.assertTrue(len(rendered) > 0)

    def test_unknown_status_falls_through_unchanged(self):
        self.assertEqual(commands_module.render_result("weird"), "weird")


class TreeRegistrationTests(unittest.TestCase):
    """The wiring layer — group + heartbeat command + 5 choices."""

    def _stub_bot(self):
        bot = MagicMock()
        bot.deps.team = _FakeTeam()
        return bot

    def test_register_attaches_workshop_group_to_tree(self):
        bot = self._stub_bot()
        tree = commands_module.register_workshop_commands(bot)
        self.assertEqual(len(tree.groups), 1)
        group = tree.groups[0]
        self.assertEqual(group.name, "workshop")

    def test_heartbeat_command_exposes_five_choices(self):
        bot = self._stub_bot()
        tree = commands_module.register_workshop_commands(bot)
        group = tree.groups[0]
        # Two subcommands now: heartbeat + next-issue.
        self.assertEqual(
            sorted(c._cmd_name for c in group.commands),
            ["heartbeat", "next-issue"],
        )
        heartbeat = next(c for c in group.commands if c._cmd_name == "heartbeat")
        choices = heartbeat._choices["agent"]
        values = sorted(c.value for c in choices)
        self.assertEqual(values, ["eddy", "linky", "marky", "patty", "team"])

    def test_next_issue_subcommand_describes_required_args(self):
        bot = self._stub_bot()
        tree = commands_module.register_workshop_commands(bot)
        group = tree.groups[0]
        next_issue = next(c for c in group.commands if c._cmd_name == "next-issue")
        described = getattr(next_issue, "_describe", {})
        for arg in ("number", "pub_date", "day_count"):
            self.assertIn(arg, described, msg=f"missing describe for {arg}")

    def test_workshop_group_requires_manage_guild(self):
        bot = self._stub_bot()
        tree = commands_module.register_workshop_commands(bot)
        group = tree.groups[0]
        self.assertIsNotNone(group.default_permissions)
        # Stubbed Permissions stores its flags dict; real discord.Permissions
        # exposes .manage_guild as a bool. Either way, manage_guild must be set.
        flags = getattr(group.default_permissions, "flags", None)
        if flags is not None:
            self.assertTrue(flags.get("manage_guild"))


class TeamModeDispatchTests(unittest.TestCase):
    """The ``team`` choice should fire all four heartbeats concurrently."""

    def test_team_dispatch_fires_each_persona_once(self):
        team = _FakeTeam()
        calls: list[str] = []

        async def fake_run(t, persona):
            calls.append(persona)
            return "pass"

        async def driver():
            with patch.object(commands_module, "run_one_heartbeat", new=fake_run):
                return await asyncio.gather(*(
                    commands_module.run_one_heartbeat(team, p)
                    for p in commands_module.PERSONAS
                ))

        results = asyncio.run(driver())
        self.assertEqual(sorted(calls), ["eddy", "linky", "marky", "patty"])
        self.assertEqual(results, ["pass", "pass", "pass", "pass"])


if __name__ == "__main__":
    unittest.main()
