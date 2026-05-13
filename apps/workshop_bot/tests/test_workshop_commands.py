"""Tests for the ``/workshop`` slash-command surface.

The slash surface is grouped by content artifact — ``/workshop issue …``,
``/workshop links …``, ``/workshop promo …``, ``/workshop campaign …``,
``/workshop goal …``, plus a top-level ``/workshop status``. These tests
cover the wiring layer:

  - ``register_workshop_commands`` attaches a ``workshop`` group to the tree.
  - the expected subgroups exist with their commands.
  - the group requires ``manage_guild`` permission.
  - ``issue start`` describes its required args.
  - the retired ``heartbeat`` / ``next-issue`` / ``job`` surfaces are gone.
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


def _subgroup(workshop_group, name):
    return next(c for c in workshop_group.commands if getattr(c, "name", None) == name)


def _cmd_names(group) -> set[str]:
    return {getattr(c, "_cmd_name", None) for c in group.commands}


def _all_command_names(workshop_group) -> list[str]:
    names: list[str] = []
    for c in workshop_group.commands:
        names.append(getattr(c, "_cmd_name", None))
        names.append(getattr(c, "name", None))
        for sub in getattr(c, "commands", []) or []:
            names.append(getattr(sub, "_cmd_name", None))
    return names


class TreeRegistrationTests(unittest.TestCase):
    def test_register_attaches_workshop_group_to_tree(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        self.assertEqual(len(tree.groups), 1)
        self.assertEqual(tree.groups[0].name, "workshop")

    def test_workshop_group_has_artifact_subgroups(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        subgroup_names = {getattr(c, "name", None) for c in workshop.commands}
        for name in ("issue", "links", "promo", "campaign", "goal"):
            self.assertIn(name, subgroup_names)

    def test_issue_subgroup_commands(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        issue = _subgroup(tree.groups[0], "issue")
        self.assertEqual(
            _cmd_names(issue),
            {"start", "update", "status", "final", "haiku", "subject", "cta", "publish"},
        )

    def test_promo_and_campaign_and_goal_commands(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        self.assertEqual(_cmd_names(_subgroup(workshop, "links")), {"scan"})
        self.assertEqual(_cmd_names(_subgroup(workshop, "promo")), {"prep", "metrics"})
        self.assertEqual(
            _cmd_names(_subgroup(workshop, "campaign")), {"add", "edit", "report", "copy", "sunset"}
        )
        self.assertEqual(_cmd_names(_subgroup(workshop, "goal")), {"set", "done"})

    def test_workshop_group_has_top_level_status_command(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        top_names = {getattr(c, "_cmd_name", None) for c in workshop.commands}
        self.assertIn("status", top_names)

    def test_issue_start_describes_required_args(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        issue = _subgroup(tree.groups[0], "issue")
        start = next(c for c in issue.commands if getattr(c, "_cmd_name", None) == "start")
        described = getattr(start, "_describe", {})
        for arg in ("number", "pub_date", "day_count"):
            self.assertIn(arg, described, msg=f"missing describe for {arg}")

    def test_workshop_group_requires_manage_guild(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        workshop = tree.groups[0]
        self.assertIsNotNone(workshop.default_permissions)
        flags = getattr(workshop.default_permissions, "flags", None)
        if flags is not None:
            self.assertTrue(flags.get("manage_guild"))

    def test_retired_surfaces_are_gone(self):
        tree = commands_module.register_workshop_commands(_stub_bot())
        names = _all_command_names(tree.groups[0])
        self.assertNotIn("heartbeat", names)
        self.assertNotIn("next-issue", names)
        self.assertNotIn("job", names)


if __name__ == "__main__":
    unittest.main()
