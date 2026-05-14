"""Goal/campaign ops jobs, the ``/workshop status`` snapshot, and the
popular-feed avoid-domains filter."""

from __future__ import annotations

import asyncio
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

from apps.workshop_bot.jobs import _base, ops, status as status_job  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402


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


def _run(coro):
    return asyncio.run(coro)


class SetGoalTests(_DBCase):
    def test_refuses_when_a_goal_is_already_active(self):
        # schema.sql seeds an active goal (members → 50).
        self.assertIsNotNone(db.get_active_goal())
        res = _run(ops.set_goal(_base.JobContext(), kind="dollars", value=1000))
        self.assertFalse(res.ok)
        self.assertIn("already an active goal", res.message)

    def test_open_a_new_goal_after_closing_the_old(self):
        seeded = db.get_active_goal()
        db.mark_goal_achieved(int(seeded["id"]))
        res = _run(ops.set_goal(_base.JobContext(), kind="DOLLARS", value=1000, notes="post-EFF push"))
        self.assertTrue(res.ok, res.message)
        active = db.get_active_goal()
        self.assertEqual(active["target_kind"], "dollars")
        self.assertEqual(active["target_value"], 1000)
        self.assertEqual(active["notes"], "post-EFF push")

    def test_bad_kind_rejected(self):
        seeded = db.get_active_goal()
        db.mark_goal_achieved(int(seeded["id"]))
        res = _run(ops.set_goal(_base.JobContext(), kind="visitors", value=10))
        self.assertFalse(res.ok)
        self.assertIn("goal kind must be one of", res.message)

    def test_nonpositive_value_rejected(self):
        seeded = db.get_active_goal()
        db.mark_goal_achieved(int(seeded["id"]))
        res = _run(ops.set_goal(_base.JobContext(), kind="members", value=0))
        self.assertFalse(res.ok)


class GoalAchievedTests(_DBCase):
    def test_marks_active_goal_and_merges_notes(self):
        seeded = db.get_active_goal()
        # give the seeded goal a note so we can check merge behaviour
        with db.connect() as conn:
            conn.execute("UPDATE goals SET notes = ? WHERE id = ?", ("set when opened", seeded["id"]))
        res = _run(ops.goal_achieved(_base.JobContext(), notes="hit it"))
        self.assertTrue(res.ok, res.message)
        self.assertIsNone(db.get_active_goal())
        achieved = db.recent_achieved_goals(limit=1)[0]
        self.assertEqual(achieved["notes"], "set when opened · hit it")

    def test_refuses_when_no_active_goal(self):
        seeded = db.get_active_goal()
        db.mark_goal_achieved(int(seeded["id"]))
        res = _run(ops.goal_achieved(_base.JobContext()))
        self.assertFalse(res.ok)
        self.assertIn("no active goal", res.message.lower())


class CampaignSunsetTests(_DBCase):
    def test_unknown_campaign_rejected(self):
        res = _run(ops.campaign_sunset(_base.JobContext(), name="nope"))
        self.assertFalse(res.ok)

    def test_sunsets_and_is_idempotent(self):
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15")
        res = _run(ops.campaign_sunset(_base.JobContext(), name="dd-may"))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(db.active_campaigns(), [])
        again = _run(ops.campaign_sunset(_base.JobContext(), name="dd-may"))
        self.assertTrue(again.ok)
        self.assertIn("already sunset", again.message)


class RecentAgentRunsTests(_DBCase):
    def test_orders_newest_first(self):
        with db.AgentRun("eddy", trigger="manual"):
            pass
        with db.AgentRun("linky", trigger="pinboard-scan"):
            pass
        rows = db.recent_agent_runs(limit=5)
        self.assertEqual([r["agent_name"] for r in rows], ["linky", "eddy"])
        self.assertEqual(rows[0]["status"], "success")


class StatusJobTests(_DBCase):
    def test_empty_ish_snapshot(self):
        res = _run(status_job.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("workshop_bot status", res.message)
        self.assertIn("issue window: *(none", res.message)
        # seeded goal shows
        self.assertIn("members → 50", res.message)
        self.assertIn("none live", res.message)
        self.assertIn("none held", res.message)
        self.assertIn("none recorded yet", res.message)

    def test_populated_snapshot(self):
        db.set_issue_window(issue_number=460, pub_date="2026-05-30", end_date="2026-05-29",
                            start_date="2026-05-22", day_count=7)
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15")
        with db.AgentRun("eddy", trigger="manual"):
            pass
        held = db.acquire_job_lock(asset="460/draft.md", job="update-draft", pid=os.getpid())
        self.assertIsNone(held)
        try:
            res = _run(status_job.run(_base.JobContext()))
        finally:
            db.release_job_lock("460/draft.md")
        self.assertTrue(res.ok)
        self.assertIn("WT460", res.message)
        self.assertIn("dd-may", res.message)
        self.assertIn("460/draft.md", res.message)
        self.assertIn("update-draft", res.message)
        self.assertIn("eddy", res.message)
        self.assertEqual(res.data["issue_window"]["issue_number"], 460)


class PopularUnseenAvoidDomainsTests(_DBCase):
    def test_excluded_domains_filtered_before_dedup(self):
        from apps.workshop_bot.systems.pinboard import client, server as pb_server

        feed = [
            {"url": "https://example.com/a", "title": "A", "description": "", "posted_by": "x"},
            {"url": "https://en.wikipedia.org/wiki/Thing", "title": "Wiki", "description": "", "posted_by": "x"},
            {"url": "https://www.thingelstad.com/2026/05/01/own-post/", "title": "Own", "description": "", "posted_by": "jamie"},
            {"url": "https://t.co/abc", "title": "Shortened", "description": "", "posted_by": "x"},
            {"url": "https://blog.example.org/post", "title": "B", "description": "", "posted_by": "y"},
        ]
        with patch.object(client, "popular", lambda limit=30: list(feed)):
            out = pb_server._handle_popular_unseen(None)
        urls = {it["url"] for it in out}
        self.assertEqual(urls, {"https://example.com/a", "https://blog.example.org/post"})


class WiringTests(unittest.TestCase):
    def test_ops_jobs_and_status_command_wired(self):
        from apps.workshop_bot.personas import commands
        # /patty goal {set,done}
        patty_tree = commands.register_patty_commands(MagicMock())
        patty = next(g for g in patty_tree.groups if getattr(g, "name", None) == "patty")
        goal = next(c for c in patty.commands if getattr(c, "name", None) == "goal")
        self.assertEqual({getattr(c, "_cmd_name", None) for c in goal.commands}, {"set", "done"})
        # /marky campaign sunset
        marky_tree = commands.register_marky_commands(MagicMock())
        marky = next(g for g in marky_tree.groups if getattr(g, "name", None) == "marky")
        campaign = next(c for c in marky.commands if getattr(c, "name", None) == "campaign")
        self.assertIn("sunset", {getattr(c, "_cmd_name", None) for c in campaign.commands})
        # /eddy status is a top-level subcommand on Eddy's tree.
        eddy_tree = commands.register_eddy_commands(MagicMock())
        eddy = next(g for g in eddy_tree.groups if getattr(g, "name", None) == "eddy")
        top_names = {getattr(c, "_cmd_name", None) for c in eddy.commands}
        self.assertIn("status", top_names)


if __name__ == "__main__":
    unittest.main()
