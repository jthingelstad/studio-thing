"""The planned phase + decoupled define / start_working.

`define` registers a newsletter as a DB row only (no workspace seeding);
`start_working` moves it to build and seeds the pipeline (pointer + first
sync-issue). The web "create newsletter" path calls `define`.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, start_issue  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase as _DBTestCase  # noqa: E402

SAT = "2026-06-27"  # a Saturday


class DefineTests(_DBTestCase):
    def test_define_is_db_row_only(self):
        ctx = _base.JobContext(trigger="web")
        res = asyncio.run(start_issue.define(ctx, number=360, pub_date=SAT, day_count=7))
        self.assertTrue(res.ok, res.message)

        win = db.get_issue_window(360)
        self.assertIsNotNone(win)
        self.assertEqual(win["phase"], "planned")
        self.assertEqual(win["is_active"], 1)

        prod = db.get_production("WT360")
        self.assertIsNotNone(prod)
        self.assertEqual(prod["phase"], "planned")
        self.assertEqual(prod["status"], "active")

        # No workspace seeded: no draft.md, no Currently nudges.
        self.assertNotIn((360, "draft.md"), self.ws.files)

    def test_define_rejects_non_saturday(self):
        ctx = _base.JobContext()
        res = asyncio.run(start_issue.define(ctx, number=360, pub_date="2026-06-28", day_count=7))
        self.assertFalse(res.ok)
        self.assertIn("Sunday", res.message)


class StartWorkingTests(_DBTestCase):
    def test_start_working_flips_to_build_and_seeds(self):
        ctx = _base.JobContext(trigger="web")
        asyncio.run(start_issue.define(ctx, number=360, pub_date=SAT, day_count=7))
        res = asyncio.run(start_issue.start_working(ctx, 360))
        self.assertTrue(res.ok, res.message)

        win = db.get_active_issue_window(360)
        self.assertEqual(win["phase"], "build")
        self.assertEqual(db.get_production("WT360")["phase"], "build")
        # No draft.md seeding — the DB is the draft; start_working chains
        # the upstream sync instead.
        self.assertNotIn((360, "draft.md"), self.ws.files)
        self.assertIn("sync-issue", res.message)

    def test_start_working_without_window_errors(self):
        ctx = _base.JobContext()
        res = asyncio.run(start_issue.start_working(ctx, 999))
        self.assertFalse(res.ok)


if __name__ == "__main__":
    unittest.main()
