"""Tests for tools/content/reorder.py — strict permutation validation and
lossless reassembly of the three section shapes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools.content import chunks, reorder  # noqa: E402


class ValidateOrderTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            chunks.NotableItem(id="n1", title="A", url="https://a/", raw_bytes="### [A](https://a/)"),
            chunks.NotableItem(id="n2", title="B", url="https://b/", raw_bytes="### [B](https://b/)"),
            chunks.NotableItem(id="n3", title="C", url="https://c/", raw_bytes="### [C](https://c/)"),
        ]

    def test_clean_permutation_passes(self):
        reorder.validate_order(self.items, ["n2", "n3", "n1"], section="notable")  # no raise

    def test_identity_passes(self):
        reorder.validate_order(self.items, ["n1", "n2", "n3"], section="notable")  # no raise

    def test_missing_id_raises(self):
        with self.assertRaises(reorder.StrictValidationError) as cx:
            reorder.validate_order(self.items, ["n1", "n2"], section="notable")
        self.assertIn("missing", str(cx.exception))
        self.assertIn("n3", str(cx.exception))

    def test_extra_id_raises(self):
        with self.assertRaises(reorder.StrictValidationError) as cx:
            reorder.validate_order(self.items, ["n1", "n2", "n3", "n4"], section="notable")
        self.assertIn("don't exist", str(cx.exception))
        self.assertIn("n4", str(cx.exception))

    def test_duplicate_id_raises(self):
        with self.assertRaises(reorder.StrictValidationError) as cx:
            reorder.validate_order(self.items, ["n1", "n1", "n2", "n3"], section="notable")
        self.assertIn("duplicate", str(cx.exception))
        self.assertIn("n1", str(cx.exception))

    def test_section_label_appears_in_message(self):
        # Useful for the #editorial refuse-card surface.
        for section in ("notable", "brief", "journal"):
            with self.subTest(section=section):
                with self.assertRaises(reorder.StrictValidationError) as cx:
                    reorder.validate_order(self.items, [], section=section)
                self.assertTrue(str(cx.exception).startswith(f"{section}:"))


class ReorderNotableTests(unittest.TestCase):
    def test_reorder_writes_correct_byte_sequence(self):
        block = (
            "_pre_\n\n"
            "### [A](https://a/)\n\nbody A\n\n\n"
            "### [B](https://b/)\n\nbody B\n\n\n"
            "### [C](https://c/)\n\nbody C"
        )
        pre, items = chunks.parse_notable(block)
        rebuilt = reorder.reorder_notable(pre, items, ["n3", "n1", "n2"])
        self.assertEqual(
            rebuilt,
            "_pre_\n\n"
            "### [C](https://c/)\n\nbody C\n\n\n"
            "### [A](https://a/)\n\nbody A\n\n\n"
            "### [B](https://b/)\n\nbody B",
        )

    def test_reorder_propagates_validation_errors(self):
        items = [chunks.NotableItem(id="n1", title="A", url="x", raw_bytes="X")]
        with self.assertRaises(reorder.StrictValidationError):
            reorder.reorder_notable("", items, ["n2"])


class ReorderBriefTests(unittest.TestCase):
    def test_reorder_writes_correct_byte_sequence(self):
        block = (
            "First. → **[A](https://a/)**\n\n"
            "Second. → **[B](https://b/)**\n\n"
            "Third. → **[C](https://c/)**"
        )
        items = chunks.parse_brief(block)
        rebuilt = reorder.reorder_brief(items, ["b3", "b1", "b2"])
        self.assertEqual(
            rebuilt,
            "Third. → **[C](https://c/)**\n\n"
            "First. → **[A](https://a/)**\n\n"
            "Second. → **[B](https://b/)**",
        )


class ReorderJournalTests(unittest.TestCase):
    def test_reorder_writes_correct_byte_sequence(self):
        block = (
            "[Sunday @ 4:16 PM](https://p1)\n\nbody1\n\n\n"
            "[Monday @ 9:02 AM](https://p2)\n\nbody2"
        )
        items = chunks.parse_journal(block)
        rebuilt = reorder.reorder_journal(items, ["j2", "j1"])
        self.assertEqual(
            rebuilt,
            "[Monday @ 9:02 AM](https://p2)\n\nbody2\n\n\n"
            "[Sunday @ 4:16 PM](https://p1)\n\nbody1",
        )


class ValidateLosslessTests(unittest.TestCase):
    def test_clean_permutation_is_lossless(self):
        draft = (
            "_pre_\n\n"
            "### [A](https://a/)\n\nbody A\n\n\n"
            "### [B](https://b/)\n\nbody B\n\n\n"
            "### [C](https://c/)\n\nbody C"
        )
        pre, items = chunks.parse_notable(draft)
        final = reorder.reorder_notable(pre, items, ["n3", "n2", "n1"])
        reorder.validate_lossless(draft, final, section="notable")  # no raise

    def test_modified_chunk_is_caught(self):
        draft = (
            "_pre_\n\n"
            "### [A](https://a/)\n\nbody A\n\n\n"
            "### [B](https://b/)\n\nbody B"
        )
        # Manually tamper with the final — change a single word.
        tampered = draft.replace("body A", "body Z")
        with self.assertRaises(reorder.StrictValidationError) as cx:
            reorder.validate_lossless(draft, tampered, section="notable")
        self.assertIn("notable", str(cx.exception))

    def test_dropped_chunk_is_caught(self):
        draft = (
            "_pre_\n\n"
            "### [A](https://a/)\n\nbody A\n\n\n"
            "### [B](https://b/)\n\nbody B"
        )
        final = "_pre_\n\n### [A](https://a/)\n\nbody A"  # B dropped
        with self.assertRaises(reorder.StrictValidationError):
            reorder.validate_lossless(draft, final, section="notable")

    def test_preamble_mismatch_is_caught(self):
        draft = "_pre A_\n\n### [A](https://a/)\n\nbody A"
        final = "_pre B_\n\n### [A](https://a/)\n\nbody A"
        with self.assertRaises(reorder.StrictValidationError) as cx:
            reorder.validate_lossless(draft, final, section="notable")
        self.assertIn("preamble", str(cx.exception))

    def test_brief_lossless(self):
        draft = (
            "One. → **[A](https://a/)**\n\n"
            "Two. → **[B](https://b/)**\n\n"
            "Three. → **[C](https://c/)**"
        )
        items = chunks.parse_brief(draft)
        final = reorder.reorder_brief(items, ["b2", "b3", "b1"])
        reorder.validate_lossless(draft, final, section="brief")  # no raise

    def test_journal_lossless(self):
        draft = (
            "[Sun @ 1:00 PM](https://p1)\n\nbody1\n\n\n"
            "[Mon @ 2:00 PM](https://p2)\n\nbody2\n\n\n"
            "[Tue @ 3:00 PM](https://p3)\n\nbody3"
        )
        items = chunks.parse_journal(draft)
        final = reorder.reorder_journal(items, ["j3", "j1", "j2"])
        reorder.validate_lossless(draft, final, section="journal")  # no raise

    def test_unknown_section_raises(self):
        with self.assertRaises(ValueError):
            reorder.validate_lossless("", "", section="nonsense")


if __name__ == "__main__":
    unittest.main()
