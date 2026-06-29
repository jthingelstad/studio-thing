"""The production-type registry — phase-vocabulary invariants."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools.content import production_types as pt  # noqa: E402


class ProductionTypesTests(unittest.TestCase):
    def test_every_type_has_ordered_phases_and_terminal(self):
        for key, t in pt.PRODUCTION_TYPES.items():
            self.assertEqual(t.key, key)
            self.assertTrue(t.phases, f"{key} has no phases")
            self.assertIn(t.terminal_phase, t.phases,
                          f"{key} terminal {t.terminal_phase!r} not in phases")
            self.assertEqual(pt.default_phase(key), t.phases[0])

    def test_id_prefixes_are_unique(self):
        prefixes = [t.id_prefix for t in pt.PRODUCTION_TYPES.values()]
        self.assertEqual(len(prefixes), len(set(prefixes)))

    def test_expected_vocabularies(self):
        self.assertEqual(pt.phases_for("newsletter"), ("planned", "write", "build", "publish", "share"))
        self.assertEqual(pt.phases_for("article"), ("idea", "outline", "draft", "publish"))
        self.assertEqual(pt.phases_for("podcast"),
                         ("idea", "outline", "script", "record", "publish"))
        self.assertEqual(pt.phases_for("project"), ("open", "done"))

    def test_is_valid_phase(self):
        self.assertTrue(pt.is_valid_phase("newsletter", "share"))
        self.assertFalse(pt.is_valid_phase("newsletter", "record"))
        # unknown type answers False, does not raise
        self.assertFalse(pt.is_valid_phase("zine", "idea"))

    def test_is_terminal(self):
        self.assertTrue(pt.is_terminal("article", "publish"))
        self.assertFalse(pt.is_terminal("article", "draft"))
        self.assertTrue(pt.is_terminal("project", "done"))

    def test_get_type_raises_on_unknown(self):
        with self.assertRaises(ValueError):
            pt.get_type("zine")
        with self.assertRaises(ValueError):
            pt.default_phase("zine")


if __name__ == "__main__":
    unittest.main()
