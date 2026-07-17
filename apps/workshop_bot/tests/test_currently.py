"""Tests for jobs/_currently.py — the ``## Currently`` section renderer
(DB-backed: reads ``currently_entries`` joined with ``currently_types``)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _currently  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402


class RenderCurrentlyTests(DBTestCase):
    def test_empty_when_no_entries(self):
        self.assertEqual(_currently.render(348), "")

    def test_single_entry(self):
        db.currently_set_entry(348, "Reading", "A book.")
        self.assertEqual(_currently.render(348), "**Reading:** A book.")

    def test_multiple_entries_render_in_position_order(self):
        db.currently_set_entry(348, "Listening", "The new Noah Kahan album.")
        db.currently_set_entry(348, "Watching", "Shrinking on Apple TV.")
        db.currently_set_entry(348, "Printing", "Clash Royale crowns.")
        self.assertEqual(
            _currently.render(348),
            "**Listening:** The new Noah Kahan album.\n\n"
            "**Watching:** Shrinking on Apple TV.\n\n"
            "**Printing:** Clash Royale crowns.",
        )

    def test_reorder_changes_render_order(self):
        db.currently_set_entry(348, "Listening", "L")
        db.currently_set_entry(348, "Watching", "W")
        db.currently_set_entry(348, "Reading", "R")
        db.currently_reorder(348, ["Watching", "Reading", "Listening"])
        self.assertEqual(
            _currently.render(348),
            "**Watching:** W\n\n**Reading:** R\n\n**Listening:** L",
        )

    def test_clear_drops_and_renumbers(self):
        db.currently_set_entry(348, "Listening", "L")
        db.currently_set_entry(348, "Watching", "W")
        db.currently_set_entry(348, "Reading", "R")
        deleted = db.currently_clear_entry(348, "Watching")
        self.assertTrue(deleted)
        # After clear, the two surviving entries renumber 1..2 by their
        # prior relative order (insertion order minus the dropped one).
        rows = db.currently_get_entries(348)
        self.assertEqual(
            [(r["type_label"], r["position"]) for r in rows], [("Listening", 1), ("Reading", 2)]
        )
        self.assertEqual(
            _currently.render(348),
            "**Listening:** L\n\n**Reading:** R",
        )

    def test_value_strip_and_label_canonicalisation(self):
        db.currently_set_entry(348, "  reading  ", "  The Lathe of Heaven  ")
        rows = db.currently_get_entries(348)
        # currently_set_entry canonicalises against the seed label casing.
        self.assertEqual(rows[0]["type_label"], "Reading")
        self.assertEqual(_currently.render(348), "**Reading:** The Lathe of Heaven")

    def test_markdown_links_pass_through_verbatim(self):
        value = (
            "The new [Noah Kahan](https://noahkahan.com) album, "
            "[The Great Divide](https://noahkahan.lnk.to/thegreatdivideTLOTB)."
        )
        db.currently_set_entry(348, "Listening", value)
        self.assertEqual(_currently.render(348), f"**Listening:** {value}")

    def test_set_requires_known_type(self):
        with self.assertRaises(db.CurrentlyError):
            db.currently_set_entry(348, "Surfing", "the waves")
        # After add_type, the same set succeeds.
        db.currently_add_type("Surfing")
        db.currently_set_entry(348, "Surfing", "the waves")
        self.assertEqual(_currently.render(348), "**Surfing:** the waves")

    def test_add_type_duplicate_refused(self):
        with self.assertRaises(db.CurrentlyError):
            db.currently_add_type("Reading")  # already seeded
        with self.assertRaises(db.CurrentlyError):
            db.currently_add_type("reading")  # case-insensitive duplicate

    def test_last_used_max_not_overwrite(self):
        db.currently_set_entry(348, "Listening", "newer")
        self.assertEqual(db.currently_get_type("Listening")["last_used_issue"], 348)
        # Setting an older issue should not move last_used backwards.
        db.currently_set_entry(347, "Listening", "older")
        self.assertEqual(db.currently_get_type("Listening")["last_used_issue"], 348)

    def test_clear_recomputes_last_used(self):
        db.currently_set_entry(347, "Listening", "older")
        db.currently_set_entry(348, "Listening", "newer")
        self.assertEqual(db.currently_get_type("Listening")["last_used_issue"], 348)
        db.currently_clear_entry(348, "Listening")
        self.assertEqual(db.currently_get_type("Listening")["last_used_issue"], 347)
        db.currently_clear_entry(347, "Listening")
        self.assertIsNone(db.currently_get_type("Listening")["last_used_issue"])

    def test_reorder_strict_permutation_required(self):
        db.currently_set_entry(348, "Listening", "L")
        db.currently_set_entry(348, "Watching", "W")
        with self.assertRaises(db.CurrentlyError):
            db.currently_reorder(348, ["Listening"])  # missing
        with self.assertRaises(db.CurrentlyError):
            db.currently_reorder(348, ["Listening", "Watching", "Reading"])  # extra

    def test_suggest_stale_orders_never_used_first(self):
        db.currently_set_entry(347, "Listening", "x")  # used
        db.currently_set_entry(348, "Watching", "x")  # used
        top = db.currently_suggest_stale(349, k=3)
        # Never-used labels rank before used ones, alphabetically.
        self.assertEqual(top[0]["last_used_issue"], None)
        # Among the used ones at the bottom of the K window, the older
        # (lower last_used_issue) ranks earlier.


if __name__ == "__main__":
    unittest.main()
