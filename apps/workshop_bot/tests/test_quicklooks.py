"""Tests for the per-persona quick-look commands added in commit 6 of
the per-persona slash-tree split: /linky pile / stats, /marky engagement
/ referrers, /patty progress / nonprofit / supporters."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import (  # noqa: E402
    _base, linky_quicklook, marky_quicklook, patty_quicklook,
)
from apps.workshop_bot.systems.buttondown import client as buttondown_client  # noqa: E402
from apps.workshop_bot.systems.pinboard import client as pinboard_client  # noqa: E402
from apps.workshop_bot.systems.stripe import client as stripe_client  # noqa: E402
from apps.workshop_bot.systems.tinylytics import client as tinylytics_client  # noqa: E402
from apps.workshop_bot.tools import context, db, support_state  # noqa: E402


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


# ── /linky pile ──────────────────────────────────────────────────────

class LinkyPileTests(unittest.TestCase):
    def test_pile_lists_brief_bookmarks(self):
        rows = [
            {"href": "http://a", "description": "Alpha", "extended": "About alpha", "time": "2026-05-10T00:00:00Z"},
            {"href": "http://b", "description": "Beta", "extended": "", "time": "2026-05-09T00:00:00Z"},
        ]
        with patch.object(pinboard_client, "recent_posts", return_value=rows):
            res = asyncio.run(linky_quicklook.pile(_base.JobContext(deps=None), limit=10))
        self.assertTrue(res.ok)
        self.assertEqual(res.data["count"], 2)
        self.assertIn("Alpha", res.message)
        self.assertIn("Beta", res.message)
        self.assertIn("About alpha", res.message)

    def test_pile_empty(self):
        with patch.object(pinboard_client, "recent_posts", return_value=[]):
            res = asyncio.run(linky_quicklook.pile(_base.JobContext(deps=None)))
        self.assertTrue(res.ok)
        self.assertEqual(res.data["count"], 0)
        self.assertIn("No", res.message)


# ── /linky stats ─────────────────────────────────────────────────────

class LinkyStatsTests(_DBCase):
    def test_stats_aggregates_by_source(self):
        with db.connect() as conn:
            for i, src in enumerate(["lobsters", "hackernews", "lobsters", "tildes"]):
                conn.execute(
                    "INSERT INTO linky_research_messages (discord_message_id, url, source, title) "
                    "VALUES (?, ?, ?, ?)",
                    (f"msg{i}", f"http://x/{i}", src, f"title {i}"),
                )
        res = asyncio.run(linky_quicklook.stats(_base.JobContext(deps=None), days=7))
        self.assertTrue(res.ok)
        self.assertEqual(res.data["count"], 4)
        self.assertEqual(res.data["by_source"]["lobsters"], 2)
        self.assertEqual(res.data["by_source"]["hackernews"], 1)

    def test_stats_empty_window(self):
        res = asyncio.run(linky_quicklook.stats(_base.JobContext(deps=None), days=7))
        self.assertTrue(res.ok)
        self.assertEqual(res.data["count"], 0)


# ── /marky engagement ────────────────────────────────────────────────

class MarkyEngagementTests(unittest.TestCase):
    def test_engagement_composes_growth_and_summary(self):
        growth = {"added": 14, "churned": 2, "net": 12, "by_source": {"embed": 14}}
        summary = {"total_hits": 4321, "top_pages": [{"path": "/archive/458/", "hits": 200}], "top_referrers": []}
        with patch.object(buttondown_client, "subscriber_growth", return_value=growth), \
             patch.object(tinylytics_client, "summary", return_value=summary):
            res = asyncio.run(marky_quicklook.engagement(_base.JobContext(deps=None), days=7))
        self.assertTrue(res.ok)
        self.assertIn("+14", res.message)
        self.assertIn("4,321", res.message)
        self.assertIn("/archive/458/", res.message)


# ── /marky referrers ─────────────────────────────────────────────────

class MarkyReferrersTests(unittest.TestCase):
    def test_referrers_lists_top(self):
        rows = [{"referrer": "linkedin.com", "hits": 50}, {"referrer": "twitter.com", "hits": 20}]
        with patch.object(tinylytics_client, "referrers", return_value=rows):
            res = asyncio.run(marky_quicklook.referrers(_base.JobContext(deps=None), days=30))
        self.assertTrue(res.ok)
        self.assertIn("linkedin.com", res.message)
        self.assertIn("50", res.message)

    def test_referrers_empty(self):
        with patch.object(tinylytics_client, "referrers", return_value=[]):
            res = asyncio.run(marky_quicklook.referrers(_base.JobContext(deps=None), days=30))
        self.assertTrue(res.ok)
        self.assertIn("No referrers", res.message)


# ── /patty progress ──────────────────────────────────────────────────

class PattyProgressTests(_DBCase):
    def test_progress_with_active_goal(self):
        fake_ctx = {
            "active_goal": {
                "kind": "members", "target_value": 100, "started_at": "2026-04-01",
                "current_progress": 73, "remaining": 27,
            },
            "next_anniversary": "2027-05-13",
            "days_to_anniversary": 364,
            "expected_issues_before_anniversary": 40,
            "recent_achieved_goals": [],
        }
        with patch.object(context, "build_patty_context", return_value=fake_ctx):
            res = asyncio.run(patty_quicklook.progress(_base.JobContext(deps=None)))
        self.assertTrue(res.ok)
        self.assertTrue(res.data["has_active_goal"])
        self.assertIn("100", res.message)
        self.assertIn("73", res.message)
        self.assertIn("27", res.message)
        self.assertIn("2027-05-13", res.message)

    def test_progress_no_active_goal(self):
        fake_ctx = {"active_goal": None, "next_anniversary": "2027-05-13",
                    "days_to_anniversary": 364, "expected_issues_before_anniversary": 40,
                    "recent_achieved_goals": []}
        with patch.object(context, "build_patty_context", return_value=fake_ctx):
            res = asyncio.run(patty_quicklook.progress(_base.JobContext(deps=None)))
        self.assertTrue(res.ok)
        self.assertFalse(res.data["has_active_goal"])
        self.assertIn("No active goal", res.message)


# ── /patty nonprofit ─────────────────────────────────────────────────

class PattyNonprofitTests(unittest.TestCase):
    def test_nonprofit_shows_current_and_past(self):
        state = {"support": {
            "current": {"nonprofit": "Electronic Frontier Foundation", "year_label": "2025", "description": "EFF defends civil liberties online."},
            "past": [{"nonprofit": "Creative Commons", "year_label": "2024"}],
        }}
        with patch.object(support_state, "read", return_value=state):
            res = asyncio.run(patty_quicklook.nonprofit(_base.JobContext(deps=None)))
        self.assertTrue(res.ok)
        self.assertIn("Electronic Frontier Foundation", res.message)
        self.assertIn("Creative Commons", res.message)

    def test_nonprofit_no_current(self):
        with patch.object(support_state, "read", return_value={"support": {}}):
            res = asyncio.run(patty_quicklook.nonprofit(_base.JobContext(deps=None)))
        self.assertTrue(res.ok)
        self.assertIn("no current nonprofit", res.message)


# ── /patty supporters ────────────────────────────────────────────────

class PattySupportersTests(unittest.TestCase):
    def test_supporters_shows_ytd_and_recent_in_window(self):
        ytd = {"year": 2026, "count": 18, "total_usd": 720.0, "average_usd": 40.0}
        now = datetime.now(timezone.utc).isoformat()
        recent = [{"created": now, "amount_usd": 40, "donor_handle": "abcd1234"}]
        with patch.object(stripe_client, "year_to_date", return_value=ytd), \
             patch.object(stripe_client, "recent_donations", return_value=recent):
            res = asyncio.run(patty_quicklook.supporters(_base.JobContext(deps=None), days=14))
        self.assertTrue(res.ok)
        self.assertIn("$720", res.message)
        self.assertIn("`abcd1234", res.message)


if __name__ == "__main__":
    unittest.main()
