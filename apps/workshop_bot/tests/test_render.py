"""Tests for tools/render.py (markdown → HTML preview) and tools/cdn.py."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import cdn, content_store, issue_items, render  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase as _DBTestCase  # noqa: E402


def _seed_348_items() -> None:
    """Seed the rows the row-driven legend needs.

    Mirrors the WT348-shaped fixtures used elsewhere — 2 Notable, 1
    Briefly, 1 Journal."""
    issue_items.upsert_item(
        issue_number=458, section="notable", source="manual",
        source_id="n-a", url="http://a", title="A", body_md="blurb.",
    )
    issue_items.upsert_item(
        issue_number=458, section="notable", source="manual",
        source_id="n-b", url="http://b", title="B", body_md="second blurb.",
    )
    issue_items.upsert_item(
        issue_number=458, section="brief", source="manual",
        source_id="b-c", url="http://c", title="C", body_md="Brief note",
    )
    issue_items.upsert_item(
        issue_number=458, section="journal", source="manual",
        source_id="j-p", url="https://example.com/post",
        title="", body_md="status.",
        metadata={"label": "Tuesday @ 3:02 PM"},
    )


class MarkdownToHtmlPageTests(unittest.TestCase):
    def test_basic_page_structure(self):
        page = render.markdown_to_html_page("# Hi\n\nSome **bold** text.", title="WT458 — draft")
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>WT458 — draft</title>", page)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', page)
        self.assertIn("<style>", page)              # self-contained CSS
        self.assertIn("<h1>Hi</h1>", page)          # markdown rendered
        self.assertIn("<strong>bold</strong>", page)
        self.assertIn("</html>", page)

    def test_escapes_title(self):
        page = render.markdown_to_html_page("x", title="<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_subtitle_renders_as_banner(self):
        page = render.markdown_to_html_page("x", title="t", subtitle="DRAFT · WT458 · not final")
        self.assertIn('<p class="banner">DRAFT · WT458 · not final</p>', page)
        # No subtitle → no banner.
        self.assertNotIn('class="banner"', render.markdown_to_html_page("x", title="t"))

    def test_convenience_links_render_in_banner(self):
        page = render.markdown_to_html_page(
            "x", title="t",
            subtitle="DRAFT · WT458",
            convenience_links=[
                ("buttondown.md", "https://files.example/458/buttondown.md"),
                ("archive.md", "https://files.example/458/archive.md"),
                ("transcript-full.txt", "https://files.example/458/transcript-full.txt"),
            ],
        )
        # The links sit inside the same banner element so the status row
        # reads as one block.
        self.assertIn('<p class="banner">', page)
        self.assertIn('<span class="banner-links">', page)
        self.assertIn('href="https://files.example/458/buttondown.md"', page)
        self.assertIn('href="https://files.example/458/archive.md"', page)
        self.assertIn('href="https://files.example/458/transcript-full.txt"', page)
        # The labels render with the ↗ glyph.
        self.assertIn("↗ buttondown.md", page)
        self.assertIn("↗ transcript-full.txt", page)

    def test_convenience_links_alone_with_no_subtitle(self):
        page = render.markdown_to_html_page(
            "x", title="t",
            convenience_links=[("archive.md", "https://files.example/458/archive.md")],
        )
        # Banner still appears (just with the links, no subtitle text).
        self.assertIn('<p class="banner">', page)
        self.assertIn("↗ archive.md", page)

    def test_meta_block_renders_subject_and_description(self):
        page = render.markdown_to_html_page(
            "# Body content\n\nMore.",
            title="t",
            meta={"subject": "WT458 — A theme & a quote", "description": "topic one, topic two"},
        )
        self.assertIn('<dl class="meta">', page)
        self.assertIn("<dt>Subject</dt>", page)
        # `&` in the subject must be HTML-escaped.
        self.assertIn("WT458 — A theme &amp; a quote", page)
        self.assertIn("<dt>Description</dt>", page)
        self.assertIn("topic one, topic two", page)
        # Meta block lands ABOVE the article body, not inside it.
        self.assertLess(page.index('<dl class="meta">'), page.index("<article>"))

    def test_meta_omits_rows_with_empty_values(self):
        # When description is empty / None, the description row doesn't
        # render — keeps the chrome quiet during the early-issue window
        # before compose-meta has filled the field.
        page = render.markdown_to_html_page(
            "x", title="t",
            meta={"subject": "WT458 — pending", "description": ""},
        )
        self.assertIn("<dt>Subject</dt>", page)
        self.assertNotIn("<dt>Description</dt>", page)

    def test_no_meta_no_block(self):
        # No meta dict → no dl element at all (don't draw an empty box).
        page = render.markdown_to_html_page("x", title="t")
        self.assertNotIn('<dl class="meta">', page)
        page2 = render.markdown_to_html_page("x", title="t", meta={"subject": "", "description": ""})
        self.assertNotIn('<dl class="meta">', page2)

    def test_strips_block_markers(self):
        md = ("<!-- block:intro -->\nHello.\n<!-- /block:intro -->\n\n## Notable\n\n"
              "<!-- block:notable -->\n### [A](http://a)\n<!-- /block:notable -->")
        page = render.markdown_to_html_page(md, title="t", strip_block_markers=True)
        self.assertNotIn("block:intro", page)
        self.assertNotIn("block:notable", page)
        self.assertIn("Hello.", page)
        self.assertIn("<h2>Notable</h2>", page)
        self.assertIn('<a href="http://a">A</a>', page)

    def test_renders_image(self):
        page = render.markdown_to_html_page("![cap](https://files.thingelstad.com/x.jpg)", title="t")
        self.assertIn('<img alt="cap" src="https://files.thingelstad.com/x.jpg"', page)

    def test_no_markdown_lib_falls_back_to_pre(self):
        # If python-markdown isn't importable, the preview shows raw source
        # in a <pre> rather than crashing.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "markdown":
                raise ImportError("simulated")
            return real_import(name, *a, **k)

        with patch.object(builtins, "__import__", fake_import):
            page = render.markdown_to_html_page("# raw\n\nstuff", title="t")
        self.assertIn("<pre>", page)
        self.assertIn("# raw", page)

    def test_no_drawer_chrome_or_script(self):
        # The retired editorial-review drawer never renders — the preview
        # page is pure article HTML with no JS at all.
        page = render.markdown_to_html_page("# X\n\nbody.", title="t")
        self.assertNotIn('id="rv-toggle"', page)
        self.assertNotIn('id="rv-panel"', page)
        self.assertNotIn('id="rv-connectors"', page)
        self.assertNotIn("<script>", page)


class ReviewTargetLegendTests(_DBTestCase):
    """``review_target_legend`` derives section presence from DB state
    (``section_status`` + the content store) — the rendered body carries
    no block markers anymore, so nothing is parsed from markdown."""

    def test_legend_lists_sections_and_items_from_db_state(self):
        content_store.write_issue(458, "intro.md", "Opening note.")
        _seed_348_items()
        legend = render.review_target_legend(issue_number=458)
        self.assertIn("- `intro`", legend)
        self.assertIn("- `notable`", legend)
        self.assertIn("- `journal`", legend)
        self.assertIn("- `brief`", legend)
        self.assertIn("`n1` — Notable: A", legend)
        self.assertIn("`n2` — Notable: B", legend)
        self.assertIn("`b1` — Briefly: C", legend)
        self.assertIn("`j1` — Journal: Tuesday @ 3:02 PM", legend)
        # Nothing seeded for these — they stay out of the legend.
        self.assertNotIn("- `haiku`", legend)
        self.assertNotIn("- `outro`", legend)
        self.assertNotIn("- `cover`", legend)

    def test_empty_issue_has_no_targets(self):
        legend = render.review_target_legend(issue_number=458)
        self.assertEqual(legend, "- No precise review targets are available.")


class CdnInvalidateTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("WEEKLY_THING_CDN_DISTRIBUTION_ID", None)

    def test_empty_paths_noop(self):
        self.assertIsNone(cdn.invalidate([]))
        self.assertIsNone(cdn.invalidate([""]))

    def test_no_distribution_id_skips(self):
        os.environ["WEEKLY_THING_CDN_DISTRIBUTION_ID"] = ""
        self.assertIsNone(cdn.invalidate(["/weekly-thing/458/draft.html"]))

    def test_issues_invalidation(self):
        os.environ["WEEKLY_THING_CDN_DISTRIBUTION_ID"] = "DIST123"
        fake_client = MagicMock()
        fake_client.create_invalidation.return_value = {"Invalidation": {"Id": "INV1"}}
        fake_boto3 = MagicMock()
        fake_boto3.client.return_value = fake_client
        with patch.dict(sys.modules, {"boto3": fake_boto3}):
            inv_id = cdn.invalidate(["weekly-thing/458/draft.html", "/weekly-thing/458/final.html"])
        self.assertEqual(inv_id, "INV1")
        batch = fake_client.create_invalidation.call_args.kwargs
        self.assertEqual(batch["DistributionId"], "DIST123")
        # Both paths forced to start with "/".
        self.assertEqual(batch["InvalidationBatch"]["Paths"]["Items"],
                         ["/weekly-thing/458/draft.html", "/weekly-thing/458/final.html"])

    def test_invalidation_failure_swallowed(self):
        os.environ["WEEKLY_THING_CDN_DISTRIBUTION_ID"] = "DIST123"
        fake_boto3 = MagicMock()
        fake_boto3.client.side_effect = RuntimeError("no creds")
        with patch.dict(sys.modules, {"boto3": fake_boto3}):
            self.assertIsNone(cdn.invalidate(["/x"]))  # never raises


if __name__ == "__main__":
    unittest.main()
