"""``_store_review_comments`` — parse Eddy's review markdown into
``editorial_comments`` rows with stable handles."""

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
from apps.workshop_bot.tools import db, issue_items  # noqa: E402


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


class StoreReviewCommentsTests(_DBCase):

    def _seed(self):
        issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="h1", body_md="x",
        )
        issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="h2", body_md="x",
        )
        issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b1", body_md="x",
        )
        issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="https://j1", body_md="x",
        )

    def test_item_anchored_bullet_gets_item_handle(self):
        self._seed()
        review = (
            "Intro paragraph (no marker, skipped).\n\n"
            "- <!-- target:n1 --> Lead Notable item feels weak; consider swapping with n2.\n\n"
            "- <!-- target:j1 --> Journal post on Tuesday lands well.\n"
        )
        count, _ = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 2)
        comments = issue_items.list_open_comments(349)
        self.assertEqual(len(comments), 2)
        handles = sorted(c["handle"] for c in comments)
        self.assertEqual(handles, ["E349-J1", "E349-N1"])

    def test_section_anchored_bullet_gets_section_handle(self):
        self._seed()
        review = (
            "- <!-- target:brief --> Brief is leaning too tech-heavy this week.\n\n"
            "- <!-- target:intro --> Intro buries the lede in trip logistics.\n"
        )
        count, _ = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 2)
        handles = sorted(c["handle"] for c in issue_items.list_open_comments(349))
        self.assertEqual(handles, ["E349-B1", "E349-I1"])

    def test_hygiene_and_issue_scopes(self):
        review = (
            "- <!-- target:hygiene --> Anchor text on N3 doesn't match its domain.\n\n"
            "- <!-- target:whole --> Word count is on the high end.\n"
        )
        count, _ = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 2)
        handles = sorted(c["handle"] for c in issue_items.list_open_comments(349))
        self.assertEqual(handles, ["E349-W1", "E349-X1"])

    def test_unanchored_segments_skipped(self):
        review = "Just an observation about the issue as a whole, no target marker."
        count, _ = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 0)

    def test_supersedes_prior_pass(self):
        self._seed()
        # First pass.
        review1 = "- <!-- target:n1 --> v1 comment.\n"
        update_draft._store_review_comments(349, review1)
        self.assertEqual(len(issue_items.list_open_comments(349)), 1)
        # Second pass — supersedes.
        review2 = "- <!-- target:n1 --> v2 comment.\n- <!-- target:n2 --> Also this.\n"
        update_draft._store_review_comments(349, review2)
        open_now = issue_items.list_open_comments(349)
        # Only the new pass survives as open.
        self.assertEqual(len(open_now), 2)
        bodies = sorted(c["body_md"] for c in open_now)
        self.assertEqual(bodies, ["Also this.", "v2 comment."])
        # The v1 comment still exists in history under its original handle.
        _v1 = issue_items.get_comment_by_handle("E349-N1")
        # The handle now points at the v2 comment (handles are stable per ordinal).
        # But the original v1 row still exists — we can confirm via the
        # raw count of all comments (open + replaced).
        with db.connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM editorial_comments WHERE issue_number = ?",
                (349,),
            ).fetchone()["n"]
        self.assertEqual(total, 3)

    def test_out_of_range_item_falls_back_to_section_scope(self):
        self._seed()  # only 2 notable rows seeded
        review = "- <!-- target:n5 --> Item that no longer exists.\n"
        count, _ = update_draft._store_review_comments(349, review)
        self.assertEqual(count, 1)
        c = issue_items.list_open_comments(349)[0]
        # Fell back to section scope; handle uses N for notable.
        self.assertEqual(c["handle"], "E349-N1")
        self.assertEqual(c["scope"], "section")
        self.assertEqual(c["section"], "notable")


if __name__ == "__main__":
    unittest.main()
