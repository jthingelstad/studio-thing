"""Tests for tools/content/chunks.py — the strict parser that splits
``draft.md`` section blocks into typed items with byte-exact ``raw_bytes``
slices. The reorder + reassembly path depends on parse / reassemble being
exact inverses, so these tests focus on:

- Item boundary detection per section (H3-link for Notable; bolded-link
  paragraph for Brief; weekday/H3 for Journal entries).
- Round-trip identity: parse + reassemble in the original order must
  yield the input block byte-for-byte.
- Permutation correctness: parse + reassemble in a *different* order
  must still preserve every item's bytes.
- Fuzz against a handful of real Buttondown-era bodies in
  ``data/buttondown/bodies/`` so we don't regress on shapes that ship
  every week.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools.content import chunks  # noqa: E402


# ---------- helpers ----------

def _notable_block(*items: str, preamble: str = "_disco preamble._") -> str:
    """Render a Notable block the way update_draft._render_notable would:
    preamble · one blank line · items two blank lines apart."""
    if items:
        return preamble + "\n\n" + "\n\n\n".join(items)
    return preamble


def _brief_block(*items: str) -> str:
    return "\n\n".join(items)


def _journal_block(*entries: str) -> str:
    return "\n\n\n".join(entries)


# ---------- Notable ----------

class NotableParseTests(unittest.TestCase):
    def test_empty_block(self):
        self.assertEqual(chunks.parse_notable(""), ("", []))
        self.assertEqual(chunks.parse_notable("   \n  "), ("", []))

    def test_preamble_only_no_items(self):
        text = "_just a preamble, no H3s._"
        pre, items = chunks.parse_notable(text)
        self.assertEqual(pre, "_just a preamble, no H3s._")
        self.assertEqual(items, [])

    def test_single_item_with_commentary(self):
        block = _notable_block(
            "### [Title One](https://one.example/a)\n\nFirst para.\n\nSecond para."
        )
        pre, items = chunks.parse_notable(block)
        self.assertEqual(pre, "_disco preamble._")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "n1")
        self.assertEqual(items[0].title, "Title One")
        self.assertEqual(items[0].url, "https://one.example/a")
        # raw_bytes is the full slice (H3 + commentary), no trailing whitespace.
        self.assertTrue(items[0].raw_bytes.startswith("### [Title One]"))
        self.assertTrue(items[0].raw_bytes.endswith("Second para."))

    def test_multiple_items_assigned_sequential_ids(self):
        block = _notable_block(
            "### [A](https://a.example/)\n\nbody A",
            "### [B](https://b.example/)\n\nbody B",
            "### [C](https://c.example/)\n\nbody C",
        )
        _, items = chunks.parse_notable(block)
        self.assertEqual([i.id for i in items], ["n1", "n2", "n3"])
        self.assertEqual([i.title for i in items], ["A", "B", "C"])

    def test_item_without_commentary(self):
        block = _notable_block("### [Just A Headline](https://hd.example/)")
        _, items = chunks.parse_notable(block)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].raw_bytes, "### [Just A Headline](https://hd.example/)")

    def test_h3_with_three_blank_lines_in_commentary_does_not_split(self):
        # update_draft never emits this shape, but if a body contained it, we'd
        # want to be defensive: only H3s split. The `\n\n\n` between items is a
        # separator inserted by the renderer, not a within-item delimiter.
        block = (
            "_pre_\n\n"
            "### [Solo](https://solo.example/)\n\n"
            "para one\n\n"
            "para two"
        )
        _, items = chunks.parse_notable(block)
        self.assertEqual(len(items), 1)
        self.assertIn("para two", items[0].raw_bytes)


class NotableRoundTripTests(unittest.TestCase):
    def test_roundtrip_in_original_order(self):
        block = _notable_block(
            "### [A](https://a.example/)\n\nbody A",
            "### [B](https://b.example/)\n\nbody B",
            "### [C](https://c.example/)\n\nbody C",
        )
        pre, items = chunks.parse_notable(block)
        rebuilt = chunks.reassemble_notable(pre, items)
        self.assertEqual(rebuilt, block)

    def test_permuted_order_preserves_bytes_per_item(self):
        block = _notable_block(
            "### [A](https://a.example/)\n\nbody A",
            "### [B](https://b.example/)\n\nbody B has\n\nmultiple paragraphs",
            "### [C](https://c.example/)\n\nbody C",
        )
        pre, items = chunks.parse_notable(block)
        # Permute B, C, A.
        by_id = {i.id: i for i in items}
        rebuilt = chunks.reassemble_notable(
            pre, [by_id["n2"], by_id["n3"], by_id["n1"]]
        )
        # Bytes per item are preserved.
        self.assertIn("### [B](https://b.example/)\n\nbody B has\n\nmultiple paragraphs", rebuilt)
        self.assertIn("### [A](https://a.example/)\n\nbody A", rebuilt)
        # Preamble + two-blank-line glue.
        self.assertTrue(rebuilt.startswith("_disco preamble._\n\n### [B]"))
        # B and C are separated by two blank lines (`\n\n\n`).
        self.assertIn("multiple paragraphs\n\n\n### [C]", rebuilt)

    def test_no_preamble_no_items_is_empty(self):
        self.assertEqual(chunks.reassemble_notable("", []), "")

    def test_preamble_only_reassembles_to_preamble(self):
        self.assertEqual(chunks.reassemble_notable("_pre_", []), "_pre_")


# ---------- Briefly ----------

class BriefParseTests(unittest.TestCase):
    def test_empty_block(self):
        self.assertEqual(chunks.parse_brief(""), [])

    def test_single_item_with_arrow(self):
        block = "Commentary here. → **[Title](https://t.example/)**"
        items = chunks.parse_brief(block)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "b1")
        self.assertEqual(items[0].title, "Title")
        self.assertEqual(items[0].url, "https://t.example/")
        self.assertEqual(items[0].raw_bytes, block)

    def test_single_item_link_only_no_commentary(self):
        block = "**[Solo](https://solo.example/)**"
        items = chunks.parse_brief(block)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Solo")

    def test_multiple_items_assigned_sequential_ids(self):
        block = _brief_block(
            "First. → **[One](https://1.example/)**",
            "Second. → **[Two](https://2.example/)**",
            "Third. → **[Three](https://3.example/)**",
        )
        items = chunks.parse_brief(block)
        self.assertEqual([i.id for i in items], ["b1", "b2", "b3"])
        self.assertEqual([i.title for i in items], ["One", "Two", "Three"])

    def test_inline_links_in_commentary_dont_confuse_parser(self):
        # The brief link is always at the end, bolded. Inline non-bolded
        # links in the commentary must not be matched as the item link.
        block = (
            "We've seen [other coverage](https://other.example/) but this is the deeper read. → "
            "**[The Real Story](https://real.example/)**"
        )
        items = chunks.parse_brief(block)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://real.example/")

    def test_paragraphs_without_bolded_link_are_skipped(self):
        block = _brief_block(
            "Just commentary, no link.",
            "Real. → **[Real](https://real.example/)**",
        )
        items = chunks.parse_brief(block)
        self.assertEqual([i.id for i in items], ["b1"])


class BriefRoundTripTests(unittest.TestCase):
    def test_roundtrip_in_original_order(self):
        block = _brief_block(
            "One. → **[A](https://a.example/)**",
            "Two. → **[B](https://b.example/)**",
            "Three. → **[C](https://c.example/)**",
        )
        items = chunks.parse_brief(block)
        self.assertEqual(chunks.reassemble_brief(items), block)

    def test_permuted_preserves_per_item_bytes(self):
        block = _brief_block(
            "One. → **[A](https://a.example/)**",
            "Two. → **[B](https://b.example/)**",
            "Three. → **[C](https://c.example/)**",
        )
        items = chunks.parse_brief(block)
        by_id = {i.id: i for i in items}
        rebuilt = chunks.reassemble_brief([by_id["b3"], by_id["b1"], by_id["b2"]])
        self.assertEqual(
            rebuilt,
            "Three. → **[C](https://c.example/)**\n\n"
            "One. → **[A](https://a.example/)**\n\n"
            "Two. → **[B](https://b.example/)**",
        )


# ---------- Journal ----------

class JournalParseTests(unittest.TestCase):
    def test_empty_block(self):
        self.assertEqual(chunks.parse_journal(""), [])

    def test_status_entry_with_body(self):
        block = (
            "[Sunday @ 4:16 PM](https://www.thingelstad.com/p1)\n\n"
            "Short status body."
        )
        items = chunks.parse_journal(block)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "j1")
        self.assertEqual(items[0].label, "Sunday @ 4:16 PM")
        self.assertEqual(items[0].url, "https://www.thingelstad.com/p1")
        self.assertEqual(items[0].title, "")
        self.assertEqual(items[0].raw_bytes, block)

    def test_titled_entry(self):
        block = (
            "### [Hypergrowth](https://www.thingelstad.com/2026/04/22/hypergrowth.html)  \n"
            "Tuesday @ 11:04 AM\n\n"
            "Reflection paragraph."
        )
        items = chunks.parse_journal(block)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Hypergrowth")
        self.assertEqual(items[0].label, "Tuesday @ 11:04 AM")
        self.assertEqual(items[0].url, "https://www.thingelstad.com/2026/04/22/hypergrowth.html")

    def test_multiple_entries_sequential_ids(self):
        block = _journal_block(
            "[Sunday @ 4:16 PM](https://post1)\n\nBody one.",
            "[Monday @ 9:02 AM](https://post2)\n\nBody two.",
            "[Friday @ 6:21 PM](https://post3)\n\nBody three.",
        )
        items = chunks.parse_journal(block)
        self.assertEqual([i.id for i in items], ["j1", "j2", "j3"])

    def test_unrecognized_chunks_are_skipped(self):
        block = _journal_block(
            "[Sunday @ 4:16 PM](https://post1)\n\nBody one.",
            "_couldn't pull from micro.blog — placeholder line_",
            "[Friday @ 6:21 PM](https://post3)\n\nBody three.",
        )
        items = chunks.parse_journal(block)
        # Placeholder skipped; real entries renumbered j1, j2.
        self.assertEqual([i.label for i in items], ["Sunday @ 4:16 PM", "Friday @ 6:21 PM"])

    def test_journal_entry_with_inline_img_preserved(self):
        block = (
            "[Saturday @ 10:00 AM](https://post-with-photo)\n\n"
            '<img src="https://files.thingelstad.com/weekly-thing/345/journal/abc.jpg" alt="x" />\n\n'
            "Caption-ish paragraph."
        )
        items = chunks.parse_journal(block)
        self.assertEqual(len(items), 1)
        self.assertIn('<img src=', items[0].raw_bytes)


class JournalRoundTripTests(unittest.TestCase):
    def test_roundtrip_in_original_order(self):
        block = _journal_block(
            "[Sunday @ 4:16 PM](https://post1)\n\nBody one.",
            "### [Elevated Post](https://post2)  \nTuesday @ 11:04 AM\n\nBody two.",
            "[Friday @ 6:21 PM](https://post3)\n\nBody three.",
        )
        items = chunks.parse_journal(block)
        self.assertEqual(chunks.reassemble_journal(items), block)

    def test_permuted_preserves_per_entry_bytes(self):
        block = _journal_block(
            "[Sunday @ 4:16 PM](https://post1)\n\nBody one.",
            "[Tuesday @ 9:02 AM](https://post2)\n\nBody two.",
        )
        items = chunks.parse_journal(block)
        by_id = {i.id: i for i in items}
        rebuilt = chunks.reassemble_journal([by_id["j2"], by_id["j1"]])
        self.assertEqual(
            rebuilt,
            "[Tuesday @ 9:02 AM](https://post2)\n\nBody two.\n\n\n"
            "[Sunday @ 4:16 PM](https://post1)\n\nBody one.",
        )


# ---------- fuzz: real bodies ----------

class RealBodyFuzzTests(unittest.TestCase):
    """Spot-check against actual published bodies. We pull the section
    between ``## Notable`` (or ``## Briefly`` / ``## Journal``) and the
    next ``## ``/``---`` boundary and parse it as if it were a draft
    block. Round-trip must be byte-identical for canonical Buttondown-
    era bodies.

    Limited to a small set of recent issues — the parser only needs to
    cover the shape ``update-draft`` produces, which matches the
    Buttondown-era format. Older eras are out of scope (see module docs).
    """

    BODIES = REPO / "data" / "buttondown" / "bodies"
    SAMPLES = ("345.md", "344.md", "343.md")  # recent, Buttondown-era

    def _extract_section(self, body: str, heading: str) -> str:
        """Carve out a section between `## {heading}` and the next top-level
        boundary (`## `, `---`, or EOF). Skips the heading line itself."""
        pattern = rf"^## {re.escape(heading)}\s*$"
        m = re.search(pattern, body, re.MULTILINE)
        if not m:
            return ""
        start = m.end()
        # Look for the next H2 or `---` separator.
        rest = body[start:]
        stop = re.search(r"\n(?:## |---\s*\n)", rest)
        end = stop.start() if stop else len(rest)
        return rest[:end].strip()

    def test_notable_roundtrip_on_recent_bodies(self):
        for sample in self.SAMPLES:
            path = self.BODIES / sample
            if not path.exists():
                continue
            body = path.read_text(encoding="utf-8")
            section = self._extract_section(body, "Notable")
            if not section:
                continue
            with self.subTest(sample=sample):
                pre, items = chunks.parse_notable(section)
                # We expect at least a few items in any real Notable section.
                self.assertGreaterEqual(
                    len(items), 3,
                    f"{sample}: parsed only {len(items)} Notable items",
                )
                rebuilt = chunks.reassemble_notable(pre, items)
                self.assertEqual(
                    rebuilt, section,
                    f"{sample}: Notable round-trip diverged",
                )

    def test_brief_roundtrip_on_recent_bodies(self):
        for sample in self.SAMPLES:
            path = self.BODIES / sample
            if not path.exists():
                continue
            body = path.read_text(encoding="utf-8")
            section = self._extract_section(body, "Briefly")
            if not section:
                continue
            with self.subTest(sample=sample):
                items = chunks.parse_brief(section)
                self.assertGreaterEqual(len(items), 3, f"{sample}: too few brief items")
                rebuilt = chunks.reassemble_brief(items)
                self.assertEqual(rebuilt, section, f"{sample}: Briefly round-trip diverged")

    def test_journal_roundtrip_on_recent_bodies(self):
        for sample in self.SAMPLES:
            path = self.BODIES / sample
            if not path.exists():
                continue
            body = path.read_text(encoding="utf-8")
            section = self._extract_section(body, "Journal")
            if not section:
                continue
            with self.subTest(sample=sample):
                items = chunks.parse_journal(section)
                if not items:
                    continue  # not every issue has Journal
                rebuilt = chunks.reassemble_journal(items)
                self.assertEqual(rebuilt, section, f"{sample}: Journal round-trip diverged")


if __name__ == "__main__":
    unittest.main()
