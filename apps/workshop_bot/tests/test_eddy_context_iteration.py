"""Iteration-aware fields in ``build_eddy_context`` —
draft_iteration_count, open_comments breakdown, review_tier."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tests._fixtures import DBTestCase  # noqa: E402
from apps.workshop_bot.tools import db, issue_items  # noqa: E402
from apps.workshop_bot.tools.content import context  # noqa: E402


class _DBCase(DBTestCase):
    """Temp-DB + in-memory S3 workspace (FakeWorkspace). The S3 stub matters
    for ``build_eddy_context`` → ``draft.section_status`` so it reads the fake
    workspace instead of reaching real S3/AWS (which fails with
    NoCredentialsError in CI). Adds an issue-window helper."""

    def _window(self, n=349, pub="2026-05-23"):
        from apps.workshop_bot.tools.content import issue as issue_mod

        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(
            issue_number=n,
            pub_date=w["pub_date"],
            end_date=w["end_date"],
            start_date=w["start_date"],
            day_count=w["day_count"],
            set_by="test",
        )


class IterationCountTests(_DBCase):
    """Iteration counts come from Eddy's review agent_runs inside the
    issue window (draft_digests died with the update-draft projection)."""

    def test_one_when_no_prior_reviews(self):
        self._window(349)
        self.assertEqual(context._draft_iteration_count(349), 1)

    def test_counts_prior_review_runs(self):
        self._window(349)
        for _ in range(3):
            with db.AgentRun("eddy", trigger="eddy-review") as run:
                run.records_written = 1
        self.assertEqual(context._draft_iteration_count(349), 4)


class OpenCommentsCountsTests(_DBCase):
    def test_empty_when_no_comments(self):
        out = context._open_comments_counts(349)
        self.assertEqual(out, {"total": 0, "by_scope": {}, "by_section": {}})

    def test_breaks_down_by_scope_and_section(self):
        a = issue_items.upsert_item(
            issue_number=349,
            section="notable",
            source="pinboard",
            source_id="a",
            body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349,
            section="brief",
            source="pinboard",
            source_id="b",
            body_md="x",
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
            issue_number=349,
            section="notable",
            source="pinboard",
            source_id="a",
            body_md="x",
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
        # One prior review pass (agent_runs is the iteration signal now).
        with db.AgentRun("eddy", trigger="eddy-review") as run:
            run.records_written = 1
        a = issue_items.upsert_item(
            issue_number=349,
            section="notable",
            source="pinboard",
            source_id="a",
            body_md="x",
        )
        issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        # Simulate today = Wed, pub = Sat (3 days out, 1 prior pass → early).
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 20))
        self.assertEqual(ctx["draft_iteration_count"], 2)
        self.assertEqual(ctx["open_comments"]["total"], 1)
        self.assertEqual(ctx["open_comments"]["by_scope"]["item"], 1)
        self.assertEqual(ctx["open_comments"]["by_section"]["notable"], 1)
        self.assertEqual(ctx["days_to_pub"], 3)
        self.assertEqual(ctx["review_tier"], "early")

    def test_ship_eve_tier_late_in_cycle(self):
        self._window(n=349, pub="2026-05-23")
        for _ in range(9):
            with db.AgentRun("eddy", trigger="eddy-review") as run:
                run.records_written = 1
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 22))  # 1 day out
        self.assertEqual(ctx["review_tier"], "ship_eve")
        self.assertEqual(ctx["days_to_pub"], 1)
        self.assertEqual(ctx["draft_iteration_count"], 10)


if __name__ == "__main__":
    unittest.main()
