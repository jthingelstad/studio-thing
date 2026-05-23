"""Tests for tools/render.py (markdown → HTML preview) and tools/cdn.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import cdn, db, issue_items, render, s3  # noqa: E402


def _seed_348_items() -> None:
    """Seed the rows the row-driven legend / anchor pass needs.

    Mirrors the WT348-shaped fixtures used elsewhere — 2 Notable, 1
    Briefly, 1 Journal — keyed to URLs the test markdown carries."""
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

    def test_review_md_adds_a_toggle_drawer_hidden_by_default(self):
        page = render.markdown_to_html_page(
            "# WT458\n\n## Notable\n\n### [A](http://a)\n\nblurb.",
            title="WT458 — draft", subtitle="DRAFT · WT458",
            review_md="## Notable\n\n- The `wuphf` blurb runs long — cut the Office tangent.\n",
        )
        # The toggle button + the drawer + the rendered review are all there.
        self.assertIn('<button id="rv-toggle"', page)
        self.assertIn('<aside id="rv-panel"', page)
        self.assertIn("Editorial review", page)
        self.assertIn("the Office tangent", page)
        # Hidden by default: the drawer is off-screen until body.rv-open.
        self.assertIn("transform: translateX(100%)", page)
        self.assertIn("body.rv-open #rv-panel { transform: translateX(0); }", page)
        # When open (and there's room) the draft shifts left so the panel
        # doesn't cover it.
        self.assertIn("body.rv-open {", page)
        # A toggle script wires the button to body.rv-open.
        self.assertIn("classList.toggle('rv-open')", page)
        # The actual draft content is untouched (not edited by the review).
        self.assertIn("<h2>Notable</h2>", page)
        self.assertIn('<a href="http://a">A</a>', page)

    def test_review_target_markers_add_anchors_and_connector_chrome(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["WORKSHOP_DB_PATH"] = str(Path(tmp) / "t.db")
            try:
                db.run_migrations()
                _seed_348_items()
                md = (
                    "<!-- block:intro -->\nOpening note.\n<!-- /block:intro -->\n\n"
                    "## Notable\n\n"
                    "<!-- block:notable -->\n"
                    "### [A](http://a)\n\nblurb.\n\n\n"
                    "### [B](http://b)\n\nsecond blurb.\n"
                    "<!-- /block:notable -->\n\n"
                    "## Briefly\n\n"
                    "<!-- block:brief -->\nBrief note → **[C](http://c)**\n<!-- /block:brief -->"
                )
                page = render.markdown_to_html_page(
                    md,
                    title="WT458 — draft",
                    strip_block_markers=True,
                    review_md="- <!-- target:n2 --> The second Notable item should move up.\n",
                    issue_number=458,
                )
            finally:
                os.environ.pop("WORKSHOP_DB_PATH", None)
        self.assertIn('id="rv-target-intro"', page)
        self.assertIn('data-review-anchor="n1"', page)
        self.assertIn('data-review-anchor="n2"', page)
        self.assertIn('data-review-anchor="b1"', page)
        self.assertIn('class="rv-target-ref" data-review-target="n2"', page)
        self.assertIn('<svg id="rv-connectors"', page)
        self.assertIn("rv-target-active", page)
        self.assertIn("data-review-target", page)
        self.assertIn("mouseenter',function(){activate(item,true);}", page)
        self.assertIn("focusin',function(){activate(item,true);}", page)
        self.assertNotIn("target:n2", page)
        self.assertNotIn("block:notable", page)

    def test_review_target_legend_lists_sections_and_items(self):
        md = (
            "<!-- block:intro -->\nOpening note.\n<!-- /block:intro -->\n\n"
            "## Notable\n\n"
            "<!-- block:notable -->\n"
            "### [A](http://a)\n\nblurb.\n"
            "<!-- /block:notable -->\n\n"
            "## Journal\n\n"
            "<!-- block:journal -->\n"
            "[Tuesday @ 3:02 PM](https://example.com/post)\n\nstatus.\n"
            "<!-- /block:journal -->"
        )
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["WORKSHOP_DB_PATH"] = str(Path(tmp) / "t.db")
            try:
                db.run_migrations()
                _seed_348_items()
                legend = render.review_target_legend(md, issue_number=458)
            finally:
                os.environ.pop("WORKSHOP_DB_PATH", None)
        self.assertIn("`intro`", legend)
        self.assertIn("`notable`", legend)
        self.assertIn("`n1` — Notable: A", legend)
        self.assertIn("`j1` — Journal: Tuesday @ 3:02 PM", legend)

    def test_no_review_md_no_chrome(self):
        page = render.markdown_to_html_page("# X\n\nbody.", title="t")
        self.assertNotIn('id="rv-toggle"', page)
        self.assertNotIn('id="rv-panel"', page)
        self.assertNotIn('id="rv-connectors"', page)
        self.assertNotIn("<script>", page)
        # Empty / whitespace review_md is treated the same as none.
        page2 = render.markdown_to_html_page("# X\n\nbody.", title="t", review_md="   \n  ")
        self.assertNotIn('id="rv-toggle"', page2)


class RenderAndUploadHtmlTests(unittest.TestCase):
    def test_uploads_and_returns_url(self):
        calls = {}

        def fake_write_html(issue, filename, html_text):
            calls["issue"], calls["filename"], calls["len"] = issue, filename, len(html_text)
            return {"url": f"https://files.thingelstad.com/weekly-thing/{issue}/{filename}", "key": "k"}

        with patch.object(s3, "write_issue_html", fake_write_html):
            url = render.render_and_upload_html(458, "draft", "# WT458\n\nbody", title="WT458 — draft",
                                                subtitle="DRAFT", strip_block_markers=True)
        self.assertEqual(url, "https://files.thingelstad.com/weekly-thing/458/draft.html")
        self.assertEqual(calls["filename"], "draft.html")
        self.assertGreater(calls["len"], 0)

    def test_returns_none_on_failure(self):
        with patch.object(s3, "write_issue_html", side_effect=RuntimeError("s3 down")):
            url = render.render_and_upload_html(458, "draft", "x", title="t")
        self.assertIsNone(url)


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
