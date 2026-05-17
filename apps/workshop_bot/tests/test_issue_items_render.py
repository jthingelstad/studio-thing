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
        "id": 1, "section": "notable", "position": 1, "is_promoted": 0,
        "url": url, "title": title, "body_md": body_md, "metadata": None,
    }


def _brief_row(*, url: str, title: str, body_md: str = "") -> dict:
    return {
        "id": 1, "section": "brief", "position": 1, "is_promoted": 0,
        "url": url, "title": title, "body_md": body_md, "metadata": None,
    }


def _journal_row(*, url: str, title: str = "", body_md: str = "", label: str = "Saturday @ 4:00 PM") -> dict:
    return {
        "id": 1, "section": "journal", "position": 1, "is_promoted": 0,
        "url": url, "title": title, "body_md": body_md,
        "metadata": {"label": label, "published": "2026-05-16T21:00:00Z"},
    }


class NotableRenderTests(unittest.TestCase):

    def test_empty_rows_returns_empty_string(self):
        self.assertEqual(issue_items_render.render_notable([], 349), "")

    def test_preamble_present(self):
        out = issue_items_render.render_notable(
            [_notable_row(url="https://a", title="A")], 349,
        )
        self.assertTrue(out.startswith("_You can discuss any of these links at the [Weekly Thing 349 tag in r/WeeklyThing]"))

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
            [_notable_row(url="https://a", title="A")], 349,
        )
        self.assertIn("### [A](https://a)", out)
        self.assertNotIn("### [A](https://a)\n\n", out.split("### [A](https://a)", 1)[1].split("\n")[0])


class BriefRenderTests(unittest.TestCase):

    def test_commentary_then_arrow_then_link(self):
        out = issue_items_render.render_brief([
            _brief_row(url="https://a", title="A", body_md="great piece"),
            _brief_row(url="https://b", title="B"),
        ])
        self.assertIn("great piece → **[A](https://a)**", out)
        self.assertIn("**[B](https://b)**", out)

    def test_one_blank_line_between_items(self):
        out = issue_items_render.render_brief([
            _brief_row(url="https://a", title="A", body_md="x"),
            _brief_row(url="https://b", title="B", body_md="y"),
        ])
        self.assertEqual(out.count("\n\n"), 1)
        self.assertNotIn("\n\n\n", out)


class JournalRenderTests(unittest.TestCase):

    def test_titled_post_elevated_form(self):
        out = issue_items_render.render_journal([
            _journal_row(url="https://x", title="A long-form post", body_md="body"),
        ])
        self.assertEqual(
            out,
            "### [A long-form post](https://x)  \nSaturday @ 4:00 PM\n\nbody",
        )

    def test_status_post_inline_link(self):
        out = issue_items_render.render_journal([
            _journal_row(url="https://x", body_md="quick note"),
        ])
        self.assertEqual(
            out,
            "[Saturday @ 4:00 PM](https://x)\n\nquick note",
        )

    def test_two_blank_lines_between_entries(self):
        out = issue_items_render.render_journal([
            _journal_row(url="https://a", body_md="x"),
            _journal_row(url="https://b", body_md="y"),
        ])
        self.assertIn("\n\n\n", out)

    def test_label_falls_back_to_published_when_metadata_missing(self):
        row = {
            "id": 1, "section": "journal", "position": 1, "is_promoted": 0,
            "url": "https://a", "title": "", "body_md": "x",
            "metadata": {"published": "2026-05-16T21:00:00Z"},
        }
        out = issue_items_render.render_journal([row])
        # 21:00 UTC = 16:00 CT in May (CDT) → Saturday @ 4:00 PM
        self.assertIn("Saturday @ 4:00 PM", out)


class FeaturedSectionTests(unittest.TestCase):

    def test_featured_journal_renders_with_heading(self):
        row = _journal_row(url="https://x", title="The Weekly Thing Team", body_md="body")
        row["is_promoted"] = 1
        row["promoted_heading"] = "Featured · The Weekly Thing Team"
        out = issue_items_render.render_featured_section(row)
        self.assertTrue(out.startswith("## Featured · The Weekly Thing Team\n\n"))
        # The promoted body is rendered the same way it would render in
        # its parent section.
        self.assertIn("### [The Weekly Thing Team](https://x)  \nSaturday @ 4:00 PM\n\nbody", out)

    def test_missing_heading_raises(self):
        row = _journal_row(url="https://x", title="X", body_md="body")
        row["is_promoted"] = 1
        with self.assertRaises(ValueError):
            issue_items_render.render_featured_section(row)


if __name__ == "__main__":
    unittest.main()
