"""End-to-end tests for the issue_windows table.

Uses a real SQLite tempfile so the partial-unique-on-is_active index is
actually exercised. The window is the operator-set source of truth for
"which issue is in flight"; getting this wrong silently would route
Patty's Thursday member.json job to the wrong issue.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

# Stubs are installed by test_pure_helpers when it runs first; importing
# from there is the cheapest way to ensure they're in sys.modules before
# the package imports discord/anthropic.
from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402

from apps.workshop_bot.tools import db # noqa: E402
from apps.workshop_bot.tools.content import issue


class IssueWindowDbTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig_path is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_path
        self._tmpdir.cleanup()

    def test_no_active_window_returns_none(self):
        self.assertIsNone(db.get_active_issue_window())
        self.assertEqual(db.list_issue_windows(), [])

    def test_set_then_read_active(self):
        window = issue.compute_window("2026-05-09", 7)
        db.set_issue_window(
            issue_number=348,
            pub_date=window["pub_date"],
            end_date=window["end_date"],
            start_date=window["start_date"],
            day_count=window["day_count"],
            set_by="jamie#0001",
        )
        active = db.get_active_issue_window()
        assert active is not None
        self.assertEqual(active["issue_number"], 348)
        self.assertEqual(active["pub_date"], "2026-05-09")
        self.assertEqual(active["end_date"], "2026-05-08")
        self.assertEqual(active["start_date"], "2026-05-01")
        self.assertEqual(active["day_count"], 7)
        self.assertEqual(active["set_by"], "jamie#0001")

    def test_setting_new_window_deactivates_prior(self):
        # Issue 348 first.
        w1 = issue.compute_window("2026-05-09", 7)
        db.set_issue_window(
            issue_number=348,
            pub_date=w1["pub_date"], end_date=w1["end_date"],
            start_date=w1["start_date"], day_count=w1["day_count"],
        )
        # Then issue 349 — this must atomically deactivate 348 so the
        # partial unique index doesn't trip.
        w2 = issue.compute_window("2026-05-16", 7)
        db.set_issue_window(
            issue_number=349,
            pub_date=w2["pub_date"], end_date=w2["end_date"],
            start_date=w2["start_date"], day_count=w2["day_count"],
        )
        active = db.get_active_issue_window()
        assert active is not None
        self.assertEqual(active["issue_number"], 349)
        # 348 still exists, just deactivated, so agents can read its
        # historical metadata via list_windows.
        all_windows = db.list_issue_windows()
        self.assertEqual([w["issue_number"] for w in all_windows], [349, 348])
        prior = db.get_issue_window(348)
        assert prior is not None
        self.assertEqual(prior["is_active"], 0)

    def test_resetting_same_issue_updates_in_place(self):
        # Jamie can correct a typo by re-running with the same number.
        w1 = issue.compute_window("2026-05-09", 7)
        db.set_issue_window(
            issue_number=348,
            pub_date=w1["pub_date"], end_date=w1["end_date"],
            start_date=w1["start_date"], day_count=w1["day_count"],
        )
        w2 = issue.compute_window("2026-05-09", 14)  # was meant to be a double
        db.set_issue_window(
            issue_number=348,
            pub_date=w2["pub_date"], end_date=w2["end_date"],
            start_date=w2["start_date"], day_count=w2["day_count"],
        )
        active = db.get_active_issue_window()
        assert active is not None
        self.assertEqual(active["issue_number"], 348)
        self.assertEqual(active["day_count"], 14)
        # Only one row exists.
        self.assertEqual(len(db.list_issue_windows()), 1)

    def test_current_window_tool_returns_error_when_unset(self):
        out = issue.t_current_issue_window(deps=None)
        self.assertIn("error", out)

    def test_current_window_tool_returns_active(self):
        w = issue.compute_window("2026-05-09", 7)
        db.set_issue_window(
            issue_number=348,
            pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"],
        )
        out = issue.t_current_issue_window(deps=None)
        self.assertEqual(out["issue_number"], 348)


if __name__ == "__main__":
    unittest.main()
