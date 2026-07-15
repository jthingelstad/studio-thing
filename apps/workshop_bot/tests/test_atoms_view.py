"""The read-side atom projection (atom editor, build 1)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tests._fixtures import TempDBTestCase as _DBCase  # noqa: E402
from apps.workshop_bot.tools import content_store, db, issue_items  # noqa: E402
from apps.workshop_bot.tools.content import atoms_view  # noqa: E402


class AtomsViewTests(_DBCase):

    def _seed(self):
        content_store.set("WT349", "intro.md", "Hello **reader**.", by="t")
        content_store.set("WT349", "haiku.md", "five / seven / five", by="t")
        content_store.set(
            "WT349", "cover.json",
            '{"caption": "Sunset.", "location": "Cannon Lake, MN"}', by="t")
        db.currently_add_type("Building")
        db.currently_set_entry(349, "Building", "the atom editor")
        self.n1 = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="p1", url="https://a", title="A pin", body_md="notable body")
        self.b1 = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="p2", url="https://b", title="B pin", body_md="brief body")
        self.j1 = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="m1", url="https://j", title="A day", body_md="journal body")

    def test_reading_order_and_shape(self):
        self._seed()
        atoms = atoms_view.build(349)
        kinds = [a["kind"] for a in atoms]
        # Reading order: intro, currently, photo, notable, journal, brief,
        # outro, echoes, closer — empty authored kinds still present.
        self.assertEqual(kinds, ["intro", "currently", "photo", "notable",
                                 "journal", "brief", "outro", "echoes", "closer"])
        intro = atoms[0]
        self.assertEqual(intro["body"], "Hello **reader**.")
        self.assertTrue(intro["editable"])
        self.assertEqual(intro["key"], "content:intro.md")
        cur = atoms[1]
        self.assertEqual((cur["title"], cur["body"]), ("Building", "the atom editor"))
        photo = atoms[2]
        self.assertIn("Sunset.", photo["body"])
        self.assertIn("Cannon Lake", photo["body"])
        notable = atoms[3]
        self.assertEqual(notable["item_id"], self.n1)
        self.assertTrue(notable["editable"])
        self.assertTrue(notable["flippable"])
        self.assertEqual(notable["url"], "https://a")
        journal = atoms[4]
        self.assertFalse(journal["flippable"])  # journal doesn't flip
        closer = atoms[-1]
        self.assertEqual(closer["key"], "content:haiku.md")
        self.assertEqual(closer["source"], "generated")

    def test_flip_and_deselect_reflected(self):
        self._seed()
        issue_items.set_section_override(self.b1, "notable")
        issue_items.set_excluded(self.j1, True)
        atoms = atoms_view.build(349)
        flipped = [a for a in atoms if a["item_id"] == self.b1][0]
        self.assertEqual(flipped["kind"], "notable")
        self.assertTrue(flipped["overridden"])
        journal = [a for a in atoms if a["item_id"] == self.j1][0]
        self.assertFalse(journal["selected"])   # deselected but still listed
        # Order respects the flip: both notable atoms precede journal.
        kinds = [a["kind"] for a in atoms]
        self.assertEqual(kinds.count("notable"), 2)
        self.assertEqual(kinds.count("brief"), 0)

    def test_body_override_reflected(self):
        self._seed()
        issue_items.set_body_override(self.n1, "Edited **body**.")
        notable = [a for a in atoms_view.build(349) if a["item_id"] == self.n1][0]
        self.assertEqual(notable["body"], "Edited **body**.")
        self.assertIn("Edited", notable["rendered_body"])
        self.assertEqual(notable["source_body"], "notable body")
        self.assertTrue(notable["body_overridden"])

    def test_empty_issue_still_projects_skeleton(self):
        atoms = atoms_view.build(999)
        kinds = [a["kind"] for a in atoms]
        self.assertEqual(kinds, ["intro", "photo", "outro", "echoes", "closer"])
        self.assertTrue(all(a["body"] == "" or a["kind"] == "photo" for a in atoms))


if __name__ == "__main__":
    unittest.main()
