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

from apps.workshop_bot.tools import cdn, render, s3  # noqa: E402


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
