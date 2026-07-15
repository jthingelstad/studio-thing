"""Tests for Eddy's slash-command surface.

Studio now runs one assistant, Eddy. These tests cover the wiring layer:

  - the register fn attaches the ``/eddy`` top-level group to a fresh tree.
  - the expected subgroups + verbs exist.
  - the top-level group requires ``manage_guild`` permission.
  - retired persona surfaces and legacy commands are gone.
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
            {"echoes", "reorder", "haiku", "subject"},
        )

    def test_eddy_issue_has_no_production_verbs(self):
        # Issue lifecycle work belongs in the Studio web surface; the chat
        # tree stays focused on Eddy's editorial helpers.
        tree = commands_module.register_eddy_commands(_stub_bot())
        issue = _subgroup(_top_group(tree, "eddy"), "issue")
        names = _cmd_names(issue)
        for moved in ("start", "update", "status", "build", "built",
                      "reopen", "publish", "put-to-bed", "reset"):
            self.assertNotIn(moved, names, msg=f"production verb '{moved}' still on /eddy issue")

    def test_eddy_top_level_status(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        names = _cmd_names(_top_group(tree, "eddy"))
        self.assertIn("status", names)

    def test_eddy_followup_verbs(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        followup = _subgroup(_top_group(tree, "eddy"), "followup")
        self.assertEqual(_cmd_names(followup), {"list", "add", "cancel"})

    def test_eddy_requires_manage_guild(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        eddy = _top_group(tree, "eddy")
        self.assertIsNotNone(eddy.default_permissions)


# ── retired surfaces ──────────────────────────────────────────────────

class RetiredSurfacesTests(unittest.TestCase):
    def test_no_workshop_register_fn(self):
        # The /workshop tree was removed in commit 4 of the per-persona migration.
        self.assertFalse(hasattr(commands_module, "register_workshop_commands"))

    def test_retired_persona_register_fns_absent(self):
        for fn_name in (
            "register_scout_commands",
            "register_linky_commands",
            "register_marky_commands",
            "register_patty_commands",
        ):
            self.assertFalse(hasattr(commands_module, fn_name), msg=f"{fn_name} should be retired")

    def test_retired_command_names_absent_across_all_trees(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        for g in tree.groups:
            names = _all_command_names(g)
            for retired in ("heartbeat", "next-issue", "job"):
                self.assertNotIn(retired, names, msg=f"retired '{retired}' found in {g.name}")


class DescriptionLengthTests(unittest.TestCase):
    """Discord rejects any command/group/parameter description outside 1–100
    chars (HTTP 400, error 50035), which silently fails that persona's *entire*
    command-tree sync at startup. Guards the 'marky campaign add' (105) and
    'eddy issue reset' (108) regressions."""

    @staticmethod
    def _collect(node, path):
        """Walk a group/command node, yielding (label, description) for the
        group/command description and every parameter description."""
        out = []
        commands = getattr(node, "commands", None)
        if commands is not None:  # a group (top-level or nested subgroup)
            out.append((f"{path} (group)", getattr(node, "description", None)))
            for child in commands:
                name = getattr(child, "name", None) or getattr(child, "_cmd_name", None)
                out.extend(DescriptionLengthTests._collect(child, f"{path} {name}"))
        else:  # a leaf command function
            out.append((path, getattr(node, "_cmd_description", None)))
            for pname, pdesc in (getattr(node, "_describe", {}) or {}).items():
                out.append((f"{path} [{pname}]", pdesc))
        return out

    def test_all_descriptions_within_discord_limit(self):
        tree = commands_module.register_eddy_commands(_stub_bot())
        for group in tree.groups:
            for label, desc in self._collect(group, f"/{group.name}"):
                self.assertIsInstance(desc, str, msg=f"{label}: missing description")
                self.assertTrue(
                    1 <= len(desc) <= 100,
                    msg=f"{label}: description is {len(desc)} chars (Discord limit 1–100): {desc!r}",
                )


class ProductionOwnershipReferenceTests(unittest.TestCase):
    """Model-visible references should not point at retired command surfaces."""

    def test_retired_command_references_absent(self):
        paths = [
            "apps/workshop_bot/tools/content/issue.py",
            "apps/workshop_bot/tools/issue_items.py",
            "apps/workshop_bot/tools/llm/local_tools.py",
            "apps/workshop_bot/prompts/eddy/prompt.md",
            "apps/workshop_bot/tools/README.md",
            "apps/workshop_bot/CLAUDE.md",
            "docs/phases/build.md",
            "docs/phases/publish.md",
            "docs/publishing-process.md",
        ]
        stale = (
            "/scout",
            "/linky",
            "/marky",
            "/patty",
            "/eddy issue start",
            "/eddy issue update",
            "/eddy issue built",
            "/eddy issue publish",
            "/eddy issue reset",
        )
        for rel in paths:
            text = (REPO / rel).read_text(encoding="utf-8")
            for needle in stale:
                self.assertNotIn(needle, text, msg=f"{needle!r} still present in {rel}")


if __name__ == "__main__":
    unittest.main()
