"""Render: <!-- handle:E349-N1 --> → drawer badge + copy button.

Plus _inject_handle_markers parallel-list rewrite."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import update_draft  # noqa: E402
from apps.workshop_bot.tools import db, issue_items, render  # noqa: E402


class HandleMarkerRenderTests(unittest.TestCase):

    def test_prepare_review_md_emits_badge_for_handle_marker(self):
        md = "- <!-- target:n1 --><!-- handle:E349-N1 --> Lead with this one."
        out = render._prepare_review_md(md)
        self.assertIn('class="rv-handle"', out)
        self.assertIn('data-handle="E349-N1"', out)
        self.assertIn('class="rv-handle-text">E349-N1', out)
        self.assertIn('class="rv-handle-copy"', out)
        self.assertIn('aria-label="Copy E349-N1', out)

    def test_invalid_handle_marker_is_dropped(self):
        md = "<!-- handle:not-a-handle --> body"
        out = render._prepare_review_md(md)
        self.assertNotIn("rv-handle", out)
        self.assertIn("body", out)

    def test_handle_marker_uppercases_letter(self):
        md = "<!-- handle:e349-n1 --> body"
        out = render._prepare_review_md(md)
        # Renderer normalizes to uppercase so badges read consistently.
        self.assertIn('data-handle="E349-N1"', out)

    def test_full_page_includes_copy_script_when_review_present(self):
        md = "# Draft\n\nbody"
        review_md = "- <!-- target:n1 --><!-- handle:E349-N1 --> Note."
        page = render.markdown_to_html_page(
            md, title="WT349 — draft", review_md=review_md,
        )
        # CSS for the badge is in the page (part of _CSS).
        self.assertIn(".rv-handle", page)
        self.assertIn(".rv-handle-copy", page)
        # JS for the copy button is wired in _REVIEW_SCRIPT.
        self.assertIn("rv-handle-copy", page)
        self.assertIn("navigator.clipboard", page)
        # The rendered badge appears inside the drawer.
        self.assertIn('data-handle="E349-N1"', page)


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()


class InjectHandleMarkersTests(_DBCase):

    def _seed(self):
        return issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )

    def test_store_returns_segment_handles_parallel_to_segments(self):
        self._seed()
        review = (
            "Intro paragraph (no marker — should skip).\n\n"
            "- <!-- target:n1 --> Lead with this one.\n\n"
            "- <!-- target:hygiene --> Anchor on N3 doesn't match.\n"
        )
        count, handles = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 2)
        # Parallel list: 3 segments (intro paragraph, bullet 1, bullet 2);
        # intro gets "", bullets get their handles.
        self.assertEqual(len(handles), 3)
        self.assertEqual(handles[0], "")
        self.assertEqual(handles[1], "E349-N1")
        self.assertEqual(handles[2], "E349-X1")

    def test_inject_handle_markers_writes_handle_next_to_target(self):
        self._seed()
        review = "- <!-- target:n1 --> Lead with this.\n"
        count, handles = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 1)
        out = update_draft._inject_handle_markers(review, handles)
        self.assertIn("<!-- target:n1 --><!-- handle:E349-N1 -->", out)

    def test_inject_preserves_text_for_segments_without_handles(self):
        review = "- Just an unanchored note.\n"
        count, handles = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 0)
        out = update_draft._inject_handle_markers(review, handles)
        self.assertEqual(out, review)

    def test_inject_handles_multiple_anchored_bullets_in_order(self):
        _a = self._seed()
        issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b", body_md="x",
        )
        review = (
            "- <!-- target:n1 --> First.\n\n"
            "- <!-- target:b1 --> Second.\n"
        )
        count, handles = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 2)
        out = update_draft._inject_handle_markers(review, handles)
        self.assertIn("<!-- target:n1 --><!-- handle:E349-N1 -->", out)
        self.assertIn("<!-- target:b1 --><!-- handle:E349-B1 -->", out)


if __name__ == "__main__":
    unittest.main()
