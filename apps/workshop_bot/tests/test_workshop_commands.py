"""Tests for the ``/workshop`` slash-command surface.

All workshop_bot user-facing actions are jobs, fired via
``/workshop job <name>``. This build wires ``start-issue`` (records the
in-flight issue window in workshop.db). These tests cover the wiring
layer:

  - ``register_workshop_commands`` attaches a ``workshop`` group to the tree.
  - the group has a ``job`` subcommand group with a ``start-issue`` command.
  - the group requires ``manage_guild`` permission.
  - ``start-issue`` describes its required args.
  - the retired ``heartbeat`` / ``next-issue`` commands are gone.
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


from apps.workshop_bot.personas import commands as commands_module  # noqa: E402


def _stub_bot():
    bot = MagicMock()
    return bot


def _all_command_names(workshop_group) -> list[str]:
    names: list[str] = []
    for c in workshop_group.commands:
        names.append(getattr(c, "_cmd_name", None))
        for sub in getattr(c, "commands", []) or []:
            names.append(getattr(sub, "_cmd_name", None))
    return names


class TreeRegistrationTests(unittest.TestCase):
    def test_register_attaches_workshop_group_to_tree(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        self.assertEqual(len(tree.groups), 1)
        self.assertEqual(tree.groups[0].name, "workshop")

    def test_workshop_group_has_job_subgroup(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        subgroup_names = [getattr(c, "name", None) for c in workshop.commands]
        self.assertIn("job", subgroup_names)

    def test_job_subgroup_has_the_wired_jobs(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        job = next(c for c in workshop.commands if getattr(c, "name", None) == "job")
        cmd_names = {getattr(c, "_cmd_name", None) for c in job.commands}
        for name in (
            "start-issue", "update-draft", "issue-status",
            "set-goal", "goal-achieved", "campaign-sunset",
        ):
            self.assertIn(name, cmd_names)

    def test_workshop_group_has_top_level_status_command(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        top_names = {getattr(c, "_cmd_name", None) for c in workshop.commands}
        self.assertIn("status", top_names)

    def test_start_issue_describes_required_args(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        job = next(c for c in workshop.commands if getattr(c, "name", None) == "job")
        start_issue = next(
            c for c in job.commands if getattr(c, "_cmd_name", None) == "start-issue"
        )
        described = getattr(start_issue, "_describe", {})
        for arg in ("number", "pub_date", "day_count"):
            self.assertIn(arg, described, msg=f"missing describe for {arg}")

    def test_workshop_group_requires_manage_guild(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        self.assertIsNotNone(workshop.default_permissions)
        flags = getattr(workshop.default_permissions, "flags", None)
        if flags is not None:
            self.assertTrue(flags.get("manage_guild"))

    def test_retired_commands_are_gone(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        names = _all_command_names(tree.groups[0])
        self.assertNotIn("heartbeat", names)
        self.assertNotIn("next-issue", names)


if __name__ == "__main__":
    unittest.main()
