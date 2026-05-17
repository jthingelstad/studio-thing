"""Iteration-aware fields in ``build_eddy_context`` —
draft_iteration_count, open_comments breakdown, review_tier."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import db, issue_items  # noqa: E402
from apps.workshop_bot.tools.content import context  # noqa: E402


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

    def _window(self, n=349, pub="2026-05-23"):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"],
                            end_date=w["end_date"], start_date=w["start_date"],
                            day_count=w["day_count"], set_by="test")


class IterationCountTests(_DBCase):

    def test_zero_when_no_digests(self):
        self.assertEqual(context._draft_iteration_count(349), 0)

    def test_counts_digest_rows(self):
        for _ in range(3):
            db.insert_draft_digest(
                issue=349, word_count=100,
                notable_count=0, brief_count=0, journal_count=0,
                intro_present=0, currently_present=0, haiku_present=0,
                cover_present=0, source_hash="abc",
            )
        self.assertEqual(context._draft_iteration_count(349), 3)


class OpenCommentsCountsTests(_DBCase):

    def test_empty_when_no_comments(self):
        out = context._open_comments_counts(349)
        self.assertEqual(out, {"total": 0, "by_scope": {}, "by_section": {}})

    def test_breaks_down_by_scope_and_section(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b", body_md="x",
        )
        issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        issue_items.write_comment(issue_number=349, scope="item", item_id=b, body_md="…")
        issue_items.write_comment(issue_number=349, scope="hygiene", body_md="…")
        issue_items.write_comment(issue_number=349, scope="issue", body_md="…")
        out = context._open_comments_counts(349)
        self.assertEqual(out["total"], 5)
        self.assertEqual(out["by_scope"]["item"], 3)
        self.assertEqual(out["by_scope"]["hygiene"], 1)
        self.assertEqual(out["by_scope"]["issue"], 1)
        self.assertEqual(out["by_section"]["notable"], 2)
        self.assertEqual(out["by_section"]["brief"], 1)

    def test_excludes_superseded(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v1")
        c2 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v2")
        issue_items.supersede(c1["id"], c2["id"])
        out = context._open_comments_counts(349)
        self.assertEqual(out["total"], 1)


class ReviewTierTests(unittest.TestCase):

    def test_ship_eve_when_close_to_publish(self):
        self.assertEqual(context._review_tier(days_to_pub=0, iteration_count=5), "ship_eve")
        self.assertEqual(context._review_tier(days_to_pub=1, iteration_count=1), "ship_eve")

    def test_early_when_few_iterations_and_runway(self):
        self.assertEqual(context._review_tier(days_to_pub=5, iteration_count=1), "early")
        self.assertEqual(context._review_tier(days_to_pub=5, iteration_count=2), "early")

    def test_mid_after_several_iterations(self):
        self.assertEqual(context._review_tier(days_to_pub=5, iteration_count=3), "mid")
        self.assertEqual(context._review_tier(days_to_pub=2, iteration_count=10), "mid")

    def test_missing_days_to_pub_defaults_to_mid(self):
        self.assertEqual(context._review_tier(days_to_pub=None, iteration_count=1), "mid")


class BuildEddyContextTests(_DBCase):

    def test_includes_iteration_fields(self):
        self._window(n=349, pub="2026-05-23")  # pub Saturday
        # Two prior runs.
        for _ in range(2):
            db.insert_draft_digest(
                issue=349, word_count=100,
                notable_count=1, brief_count=2, journal_count=3,
                intro_present=1, currently_present=1, haiku_present=0,
                cover_present=1, source_hash="abc",
            )
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        # Simulate today = Wed, pub = Sat (3 days out, 2 iterations done → early).
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 20))
        self.assertEqual(ctx["draft_iteration_count"], 2)
        self.assertEqual(ctx["open_comments"]["total"], 1)
        self.assertEqual(ctx["open_comments"]["by_scope"]["item"], 1)
        self.assertEqual(ctx["open_comments"]["by_section"]["notable"], 1)
        self.assertEqual(ctx["days_to_pub"], 3)
        self.assertEqual(ctx["review_tier"], "early")

    def test_ship_eve_tier_late_in_cycle(self):
        self._window(n=349, pub="2026-05-23")
        for _ in range(10):
            db.insert_draft_digest(
                issue=349, word_count=3000,
                notable_count=4, brief_count=10, journal_count=15,
                intro_present=1, currently_present=1, haiku_present=1,
                cover_present=1, source_hash="ghi",
            )
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 22))  # 1 day out
        self.assertEqual(ctx["review_tier"], "ship_eve")
        self.assertEqual(ctx["days_to_pub"], 1)
        self.assertEqual(ctx["draft_iteration_count"], 10)


if __name__ == "__main__":
    unittest.main()
