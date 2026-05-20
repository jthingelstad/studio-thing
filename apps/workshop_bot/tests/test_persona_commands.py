"""Tests for the per-persona slash-command surface.

Each persona owns its own slash tree (``/eddy``, ``/linky``, ``/marky``,
``/patty``), each registered on that persona's Discord bot. These
tests cover the wiring layer:

  - the four register fns each attach the right top-level group to a
    fresh tree.
  - the expected subgroups + verbs exist for each persona.
  - the top-level group requires ``manage_guild`` permission.
  - ``issue start`` describes its required args (under /eddy).
  - retired surfaces (``/workshop``, ``heartbeat``, ``next-issue``,
    ``job``) are gone.
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
    return MagicMock()


def _top_group(tree, name):
    """Find the top-level group in ``tree`` with the given name."""
    return next(g for g in tree.groups if getattr(g, "name", None) == name)


def _subgroup(group, name):
    return next(c for c in group.commands if getattr(c, "name", None) == name)


def _cmd_names(group) -> set[str]:
    return {getattr(c, "_cmd_name", None) for c in group.commands}


def _all_command_names(group) -> list[str]:
    names: list[str] = []
    for c in group.commands:
        names.append(getattr(c, "_cmd_name", None))
        names.append(getattr(c, "name", None))
        for sub in getattr(c, "commands", []) or []:
            names.append(getattr(sub, "_cmd_name", None))
    return names


# ── /eddy ─────────────────────────────────────────────────────────────

class EddyTreeTests(unittest.TestCase):
    def test_register_attaches_eddy_group(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        self.assertEqual(len(tree.groups), 1)
        self.assertEqual(tree.groups[0].name, "eddy")

    def test_eddy_subgroups(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        eddy = _top_group(tree, "eddy")
        subs = {getattr(c, "name", None) for c in eddy.commands}
        for name in ("issue", "followup"):
            self.assertIn(name, subs)

    def test_eddy_issue_verbs(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        issue = _subgroup(_top_group(tree, "eddy"), "issue")
        self.assertEqual(
            _cmd_names(issue),
            {"start", "update", "status", "reorder", "haiku", "subject",
             "publish", "reset"},
        )

    def test_eddy_issue_publish_destinations(self):
        # Discord limits group nesting to one level — publish lives as
        # a leaf with a destination choice arg, not a subgroup.
        tree = commands_module.register_eddy_commands(_stub_bot())
        issue = _subgroup(_top_group(tree, "eddy"), "issue")
        publish_cmd = next(
            c for c in issue.commands if getattr(c, "_cmd_name", None) == "publish"
        )
        choices = getattr(publish_cmd, "_choices", {}).get("destination", [])
        choice_values = {c.value for c in choices}
        self.assertEqual(choice_values, {"all", "audio", "buttondown", "website"})

    def test_eddy_top_level_status(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        names = _cmd_names(_top_group(tree, "eddy"))
        self.assertIn("status", names)

    def test_eddy_followup_verbs(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        followup = _subgroup(_top_group(tree, "eddy"), "followup")
        self.assertEqual(_cmd_names(followup), {"list", "add", "cancel"})

    def test_eddy_issue_start_describes_required_args(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        issue = _subgroup(_top_group(tree, "eddy"), "issue")
        start = next(c for c in issue.commands if getattr(c, "_cmd_name", None) == "start")
        described = getattr(start, "_describe", {})
        for arg in ("number", "pub_date", "day_count"):
            self.assertIn(arg, described, msg=f"missing describe for {arg}")

    def test_eddy_requires_manage_guild(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        eddy = _top_group(tree, "eddy")
        self.assertIsNotNone(eddy.default_permissions)


# ── /linky ────────────────────────────────────────────────────────────

class LinkyTreeTests(unittest.TestCase):
    def test_linky_tree(self):
        tree = commands_module.register_linky_commands(_stub_bot())
        linky = _top_group(tree, "linky")
        self.assertIn("scan", _cmd_names(linky))
        self.assertIn("followup", {getattr(c, "name", None) for c in linky.commands})

    def test_linky_followup_verbs(self):
        tree = commands_module.register_linky_commands(_stub_bot())
        followup = _subgroup(_top_group(tree, "linky"), "followup")
        self.assertEqual(_cmd_names(followup), {"list", "add", "cancel"})

    def test_linky_requires_manage_guild(self):
        tree = commands_module.register_linky_commands(_stub_bot())
        self.assertIsNotNone(_top_group(tree, "linky").default_permissions)


# ── /marky ────────────────────────────────────────────────────────────

class MarkyTreeTests(unittest.TestCase):
    def test_marky_top_level_verbs(self):
        tree = commands_module.register_marky_commands(_stub_bot())
        names = _cmd_names(_top_group(tree, "marky"))
        for v in ("prep", "metrics"):
            self.assertIn(v, names)

    def test_marky_campaign_verbs(self):
        tree = commands_module.register_marky_commands(_stub_bot())
        campaign = _subgroup(_top_group(tree, "marky"), "campaign")
        self.assertEqual(
            _cmd_names(campaign),
            {"add", "edit", "report", "copy", "sunset"},
        )

    def test_marky_followup_verbs(self):
        tree = commands_module.register_marky_commands(_stub_bot())
        followup = _subgroup(_top_group(tree, "marky"), "followup")
        self.assertEqual(_cmd_names(followup), {"list", "add", "cancel"})


# ── /patty ────────────────────────────────────────────────────────────

class PattyTreeTests(unittest.TestCase):
    def test_patty_top_level_cta(self):
        tree = commands_module.register_patty_commands(_stub_bot())
        names = _cmd_names(_top_group(tree, "patty"))
        self.assertIn("cta", names)

    def test_patty_goal_verbs(self):
        tree = commands_module.register_patty_commands(_stub_bot())
        goal = _subgroup(_top_group(tree, "patty"), "goal")
        self.assertEqual(_cmd_names(goal), {"set", "done"})

    def test_patty_followup_verbs(self):
        tree = commands_module.register_patty_commands(_stub_bot())
        followup = _subgroup(_top_group(tree, "patty"), "followup")
        self.assertEqual(_cmd_names(followup), {"list", "add", "cancel"})


# ── retired surfaces ──────────────────────────────────────────────────

class RetiredSurfacesTests(unittest.TestCase):
    def test_no_workshop_register_fn(self):
        # The /workshop tree was removed in commit 4 of the per-persona migration.
        self.assertFalse(hasattr(commands_module, "register_workshop_commands"))

    def test_retired_command_names_absent_across_all_trees(self):
        for fn in (
            commands_module.register_eddy_commands,
            commands_module.register_linky_commands,
            commands_module.register_marky_commands,
            commands_module.register_patty_commands,
        ):
            tree = fn(_stub_bot())
            for g in tree.groups:
                names = _all_command_names(g)
                for retired in ("heartbeat", "next-issue", "job"):
                    self.assertNotIn(retired, names, msg=f"retired '{retired}' found in {g.name}")


if __name__ == "__main__":
    unittest.main()
