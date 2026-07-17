"""issue_items_render — rows → section markdown."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import issue_items_render  # noqa: E402


def _notable_row(*, url: str, title: str, body_md: str = "") -> dict:
    return {
        "id": 1,
        "section": "notable",
        "position": 1,
        "is_promoted": 0,
        "url": url,
        "title": title,
        "body_md": body_md,
        "metadata": None,
    }


def _brief_row(*, url: str, title: str, body_md: str = "") -> dict:
    return {
        "id": 1,
        "section": "brief",
        "position": 1,
        "is_promoted": 0,
        "url": url,
        "title": title,
        "body_md": body_md,
        "metadata": None,
    }


def _journal_row(
    *,
    url: str,
    title: str = "",
    body_md: str = "",
    label: str = "Saturday @ 4:00 PM",
    published: str = "2026-05-16T21:00:00Z",
    row_id: int = 1,
) -> dict:
    return {
        "id": row_id,
        "section": "journal",
        "position": 1,
        "is_promoted": 0,
        "url": url,
        "title": title,
        "body_md": body_md,
        "metadata": {"label": label, "published": published},
    }


class NotableRenderTests(unittest.TestCase):
    def test_empty_rows_returns_empty_string(self):
        self.assertEqual(issue_items_render.render_notable([], 349), "")

    def test_preamble_present(self):
        out = issue_items_render.render_notable(
            [_notable_row(url="https://a", title="A")],
            349,
        )
        self.assertTrue(
            out.startswith(
                "_You can discuss any of these links at the [Weekly Thing 349 tag in r/WeeklyThing]"
            )
        )

    def test_two_items_separated_by_two_blank_lines(self):
        rows = [
            _notable_row(url="https://a", title="A", body_md="comma"),
            _notable_row(url="https://b", title="B", body_md="other"),
        ]
        out = issue_items_render.render_notable(rows, 349)
        body = out.split("\n", 2)[-1].lstrip("\n")
        self.assertIn("\n\n\n", body)
        # Spot-check the items render with their commentary.
        self.assertIn("### [A](https://a)\n\ncomma", out)
        self.assertIn("### [B](https://b)\n\nother", out)

    def test_item_without_commentary_renders_bare_heading(self):
        out = issue_items_render.render_notable(
            [_notable_row(url="https://a", title="A")],
            349,
        )
        self.assertIn("### [A](https://a)", out)
        self.assertNotIn(
            "### [A](https://a)\n\n", out.split("### [A](https://a)", 1)[1].split("\n")[0]
        )


class BriefRenderTests(unittest.TestCase):
    def test_commentary_then_arrow_then_link(self):
        out = issue_items_render.render_brief(
            [
                _brief_row(url="https://a", title="A", body_md="great piece"),
                _brief_row(url="https://b", title="B"),
            ]
        )
        self.assertIn("great piece → **[A](https://a)**", out)
        self.assertIn("**[B](https://b)**", out)

    def test_one_blank_line_between_items(self):
        out = issue_items_render.render_brief(
            [
                _brief_row(url="https://a", title="A", body_md="x"),
                _brief_row(url="https://b", title="B", body_md="y"),
            ]
        )
        self.assertEqual(out.count("\n\n"), 1)
        self.assertNotIn("\n\n\n", out)


class JournalRenderTests(unittest.TestCase):
    def test_day_header_emitted_above_entries(self):
        """Every Journal section opens with a day H3 sub-header derived
        from the local-time date of the first entry on that day."""
        out = issue_items_render.render_journal(
            [
                _journal_row(url="https://x", title="A long-form post", body_md="body"),
            ]
        )
        # 21:00 UTC on 2026-05-16 = 16:00 America/Chicago (CDT) = Saturday.
        self.assertTrue(out.startswith("### Saturday, May 16\n\n"))

    def test_titled_post_renders_with_time_paragraph_below_heading(self):
        out = issue_items_render.render_journal(
            [
                _journal_row(url="https://x", title="A long-form post", body_md="body"),
            ]
        )
        self.assertEqual(
            out,
            "### Saturday, May 16\n\n### [A long-form post](https://x)\n\n4:00 PM\n\nbody",
        )

    def test_note_renders_as_compact_em_dash_paragraph(self):
        out = issue_items_render.render_journal(
            [
                _journal_row(url="https://x", body_md="quick note"),
            ]
        )
        self.assertEqual(
            out,
            "### Saturday, May 16\n\n[4:00 PM](https://x) — quick note",
        )

    def test_note_without_body_renders_as_bare_linked_time(self):
        out = issue_items_render.render_journal(
            [
                _journal_row(url="https://x"),
            ]
        )
        self.assertEqual(out, "### Saturday, May 16\n\n[4:00 PM](https://x)")

    def test_multi_day_groups_under_separate_headers(self):
        """Entries on different days bucket under their own day headers,
        joined with a blank line between day blocks."""
        rows = [
            _journal_row(
                row_id=1,
                url="https://a",
                body_md="sat note",
                published="2026-05-16T19:00:00Z",  # 14:00 CT Saturday
            ),
            _journal_row(
                row_id=2,
                url="https://b",
                title="Sunday post",
                body_md="sun body",
                published="2026-05-17T18:00:00Z",  # 13:00 CT Sunday
            ),
        ]
        out = issue_items_render.render_journal(rows)
        self.assertIn("### Saturday, May 16", out)
        self.assertIn("### Sunday, May 17", out)
        # Day blocks are separated by two blank lines (\n\n\n joiner).
        self.assertIn("\n\n\n### Sunday, May 17", out)
        # Saturday's note sits inside the Saturday block.
        self.assertIn("### Saturday, May 16\n\n[2:00 PM](https://a) — sat note", out)

    def test_empty_days_are_skipped(self):
        """Only days with ≥1 entry produce a header."""
        out = issue_items_render.render_journal(
            [
                _journal_row(url="https://a", body_md="x", published="2026-05-16T19:00:00Z"),
                _journal_row(url="https://b", body_md="y", published="2026-05-18T19:00:00Z"),
            ]
        )
        self.assertIn("### Saturday, May 16", out)
        self.assertIn("### Monday, May 18", out)
        # Sunday (between) had no entries — no header for it.
        self.assertNotIn("Sunday", out)

    def test_empty_rows_returns_empty_string(self):
        self.assertEqual(issue_items_render.render_journal([]), "")

    def test_day_label_falls_back_when_published_missing(self):
        """Rows without ``metadata.published`` use the legacy ``label``
        field's weekday portion for the day header. Bucketing keys them
        under a stable ``undated`` bucket."""
        row = {
            "id": 1,
            "section": "journal",
            "position": 1,
            "is_promoted": 0,
            "url": "https://a",
            "title": "",
            "body_md": "x",
            "metadata": {"label": "Friday @ 9:00 AM"},
        }
        out = issue_items_render.render_journal([row])
        self.assertIn("### Friday", out)
        self.assertIn("9:00 AM", out)


class FeaturedSectionTests(unittest.TestCase):
    def test_featured_journal_renders_with_heading(self):
        row = _journal_row(url="https://x", title="The Weekly Thing Team", body_md="body")
        row["is_promoted"] = 1
        row["promoted_heading"] = "Featured · The Weekly Thing Team"
        out = issue_items_render.render_featured_section(row)
        self.assertTrue(out.startswith("## Featured · The Weekly Thing Team\n\n"))
        # The promoted body is rendered the same way an entry would in
        # the per-day Journal block — title heading, time paragraph,
        # body. No day header (this is a standalone featured section,
        # not part of the Journal-section day-grouping).
        self.assertIn("### [The Weekly Thing Team](https://x)\n\n4:00 PM\n\nbody", out)

    def test_missing_heading_raises(self):
        row = _journal_row(url="https://x", title="X", body_md="body")
        row["is_promoted"] = 1
        with self.assertRaises(ValueError):
            issue_items_render.render_featured_section(row)


if __name__ == "__main__":
    unittest.main()
