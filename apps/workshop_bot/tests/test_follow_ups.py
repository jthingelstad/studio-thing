"""Tests for Eddy follow-ups, the `follow-up-sweep` job, and tools."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, follow_up  # noqa: E402
from apps.workshop_bot.tools import db # noqa: E402
from apps.workshop_bot.tools.llm import agent_tools
from apps.workshop_bot.tests._fixtures import TempDBTestCase as _DBCase  # noqa: E402


# ---------- pure trigger parsing ----------

class TriggerParsingTests(unittest.TestCase):
    def test_when_date_becomes_evening(self):
        self.assertEqual(follow_up.resolve_trigger(when="2026-06-01"), ("time", "2026-06-01T18:00:00", None))

    def test_when_datetime_kept(self):
        self.assertEqual(follow_up.resolve_trigger(when="2026-05-13T18:30"), ("time", "2026-05-13T18:30:00", None))
        self.assertEqual(follow_up.resolve_trigger(when="2026-05-13 18:30"), ("time", "2026-05-13T18:30:00", None))
        # tz-aware → naive (local) form
        self.assertEqual(follow_up.resolve_trigger(when="2026-05-13T18:30:00-05:00"), ("time", "2026-05-13T18:30:00", None))

    def test_in_days_offset(self):
        kind, due, issue = follow_up.resolve_trigger(in_days=1)
        self.assertEqual(kind, "time")
        self.assertIsNone(issue)
        self.assertEqual(due, datetime.combine(date.today() + timedelta(days=1), datetime.min.time().replace(hour=18)).isoformat(timespec="seconds"))

    def test_at_issue(self):
        self.assertEqual(follow_up.resolve_trigger(at_issue=387), ("issue", None, 387))

    def test_exactly_one_trigger(self):
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.resolve_trigger()
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.resolve_trigger(when="2026-06-01", at_issue=387)

    def test_bad_when(self):
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.resolve_trigger(when="next tuesday")
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.resolve_trigger(in_days=-3)
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.resolve_trigger(at_issue=0)

    def test_normalize_persona(self):
        self.assertEqual(follow_up.normalize_persona("Eddy"), "eddy")
        self.assertEqual(follow_up.normalize_persona(None), "eddy")
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.normalize_persona("nobody")


# ---------- db helpers + create/list/cancel ----------


class DbHelperTests(_DBCase):
    def test_insert_open_due_fire_cancel(self):
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        future = (datetime.now() + timedelta(days=5)).isoformat(timespec="seconds")
        a = db.insert_follow_up(persona="eddy", trigger_kind="time", note="due now", due_at=past)
        b = db.insert_follow_up(persona="marky", trigger_kind="time", note="later", due_at=future)
        c = db.insert_follow_up(persona="eddy", trigger_kind="issue", note="at 387", trigger_issue=387)

        self.assertEqual({r["id"] for r in db.open_follow_ups()}, {a, b, c})
        self.assertEqual({r["id"] for r in db.open_follow_ups(persona="eddy")}, {a, c})

        now_iso = datetime.now().isoformat(timespec="seconds")
        # No active issue → only the past time-based one is due.
        due = db.due_follow_ups(now_iso=now_iso, active_issue=None)
        self.assertEqual([r["id"] for r in due], [a])
        # Active issue 390 ≥ 387 → the issue-based one is due too.
        due = db.due_follow_ups(now_iso=now_iso, active_issue=390)
        self.assertEqual({r["id"] for r in due}, {a, c})
        # Active issue 386 < 387 → not yet.
        due = db.due_follow_ups(now_iso=now_iso, active_issue=386)
        self.assertEqual([r["id"] for r in due], [a])

        self.assertTrue(db.mark_follow_up_fired(a))
        self.assertFalse(db.mark_follow_up_fired(a))  # already fired
        self.assertNotIn(a, {r["id"] for r in db.open_follow_ups()})

        # cancel respects persona ownership
        self.assertFalse(db.cancel_follow_up(c, persona="marky"))
        self.assertTrue(db.cancel_follow_up(c, persona="eddy"))
        self.assertEqual([r["id"] for r in db.open_follow_ups()], [b])

    def test_create_helper(self):
        row = follow_up.create(persona="eddy", note="check the issue", in_days=7, created_by="jamie")
        self.assertEqual(row["persona"], "eddy")
        self.assertEqual(row["trigger_kind"], "time")
        self.assertEqual(row["created_by"], "jamie")
        with self.assertRaises(follow_up.FollowUpError):
            follow_up.create(persona="eddy", note="   ", in_days=1)

    def test_add_list_cancel_jobs(self):
        r = asyncio.run(follow_up.add(_base.JobContext(), note="check WT350 framing", persona="eddy", at_issue=350, created_by="jamie"))
        self.assertTrue(r.ok, r.message)
        fid = r.data["id"]
        self.assertIn("WT350", r.message)

        lst = asyncio.run(follow_up.list_open(_base.JobContext()))
        self.assertIn(f"#{fid}", lst.message)
        self.assertIn("check WT350 framing", lst.message)

        bad = asyncio.run(follow_up.add(_base.JobContext(), note="x", when="not-a-date"))
        self.assertFalse(bad.ok)

        c = asyncio.run(follow_up.cancel(_base.JobContext(), followup_id=fid))
        self.assertTrue(c.ok)
        self.assertEqual(asyncio.run(follow_up.list_open(_base.JobContext())).message[:2], "No")
        # cancelling again is a no-op-ish
        self.assertTrue(asyncio.run(follow_up.cancel(_base.JobContext(), followup_id=fid)).ok)
        self.assertFalse(asyncio.run(follow_up.cancel(_base.JobContext(), followup_id=9999)).ok)


# ---------- the sweep ----------

class _FakeTeam:
    def __init__(self, persona="eddy", reply="Following up — here's where things stand."):
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.bot = MagicMock()
        self.bot.user = object()
        self.bot.get_channel = MagicMock(return_value=self.channel)
        self.bot.core = AsyncMock(return_value=(reply, {"iterations": 1}))
        self.persona = persona

    def ctx(self):
        team = MagicMock()
        team.bots = {self.persona: self.bot}
        d = MagicMock()
        d.team = team
        return _base.JobContext(deps=d, trigger="scheduled")


class SweepTests(_DBCase):
    def setUp(self):
        super().setUp()
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        # the sweep builds per-persona context (reads S3 / issue window); stub it
        self._p = patch.object(follow_up, "_persona_context_block", lambda persona: "_(test context)_")
        self._p.start()

    def tearDown(self):
        self._p.stop()
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def test_fires_due_posts_and_leaves_others(self):
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        future = (datetime.now() + timedelta(days=5)).isoformat(timespec="seconds")
        a = db.insert_follow_up(persona="eddy", trigger_kind="time", note="how WT348 is shaping up", due_at=past)
        b = db.insert_follow_up(persona="eddy", trigger_kind="time", note="not yet", due_at=future)
        ft = _FakeTeam(persona="eddy")
        res = asyncio.run(follow_up.sweep(ft.ctx()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(res.data, {"fired": 1, "posted": 1})
        ft.channel.send.assert_awaited()  # posted the check-in
        # a fired, b still open
        open_ids = {r["id"] for r in db.open_follow_ups()}
        self.assertEqual(open_ids, {b})
        self.assertIsNotNone(db.get_follow_up(a)["fired_at"])

    def test_issue_trigger_fires_when_window_reaches(self):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-07-04", 7)
        # set an in-flight window for issue 390
        db.set_issue_window(issue_number=390, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        fid = db.insert_follow_up(persona="eddy", trigger_kind="issue", note="revisit when we hit 387", trigger_issue=387)
        ft = _FakeTeam(persona="eddy")
        res = asyncio.run(follow_up.sweep(ft.ctx()))
        self.assertTrue(res.ok)
        self.assertEqual(res.data["fired"], 1)
        self.assertIsNotNone(db.get_follow_up(fid)["fired_at"])

    def test_nothing_due_passes(self):
        db.insert_follow_up(persona="eddy", trigger_kind="time", note="later",
                            due_at=(datetime.now() + timedelta(days=3)).isoformat(timespec="seconds"))
        res = asyncio.run(follow_up.sweep(_FakeTeam().ctx()))
        self.assertTrue(res.ok)
        self.assertIn("nothing due", res.message)

    def test_pass_response_fires_without_posting(self):
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        fid = db.insert_follow_up(persona="eddy", trigger_kind="time", note="x", due_at=past)
        ft = _FakeTeam(persona="eddy", reply="PASS")
        res = asyncio.run(follow_up.sweep(ft.ctx()))
        self.assertEqual(res.data, {"fired": 1, "posted": 0})
        ft.channel.send.assert_not_awaited()
        self.assertIsNotNone(db.get_follow_up(fid)["fired_at"])

    def test_agent_error_leaves_it_open(self):
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        fid = db.insert_follow_up(persona="eddy", trigger_kind="time", note="x", due_at=past)
        ft = _FakeTeam(persona="eddy")
        ft.bot.core = AsyncMock(side_effect=RuntimeError("boom"))
        res = asyncio.run(follow_up.sweep(ft.ctx()))
        self.assertTrue(res.ok)
        self.assertEqual(res.data, {"fired": 0, "posted": 0})
        self.assertIsNone(db.get_follow_up(fid)["fired_at"])  # still open → retried next sweep
        self.assertIn("left open", res.message)

    def test_persona_unavailable_leaves_it_open(self):
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        fid = db.insert_follow_up(persona="marky", trigger_kind="time", note="x", due_at=past)
        # ft only has an eddy bot → marky unresolvable
        res = asyncio.run(follow_up.sweep(_FakeTeam(persona="eddy").ctx()))
        self.assertTrue(res.ok)
        self.assertEqual(res.data["fired"], 0)
        self.assertIsNone(db.get_follow_up(fid)["fired_at"])


# ---------- the followup__* tools ----------

class FollowupToolTests(_DBCase):
    def _as(self, persona, fn, **kw):
        tok = agent_tools.active_persona.set(persona)
        try:
            return fn(None, **kw)
        finally:
            agent_tools.active_persona.reset(tok)

    def test_schedule_list_cancel(self):
        out = self._as("eddy", agent_tools.t_followup_schedule, note="check WT350 framing", at_issue=350)
        self.assertNotIn("error", out)
        self.assertEqual(out["persona"], "eddy")
        fid = out["id"]
        # The tool lists only Eddy's pending work in the one-agent system.
        eddy_list = self._as("eddy", agent_tools.t_followup_list)
        self.assertEqual([r["id"] for r in eddy_list], [fid])
        self.assertEqual(self._as("eddy", agent_tools.t_followup_cancel, followup_id=fid)["cancelled"], True)
        self.assertEqual(self._as("eddy", agent_tools.t_followup_list), [])

    def test_schedule_bad_args_returns_error(self):
        out = self._as("eddy", agent_tools.t_followup_schedule, note="x")  # no trigger
        self.assertIn("error", out)
        out = self._as("eddy", agent_tools.t_followup_schedule, note="x", when="someday")
        self.assertIn("error", out)

    def test_schedule_in_days(self):
        out = self._as("eddy", agent_tools.t_followup_schedule, note="issue check", in_days=14)
        self.assertNotIn("error", out)
        row = db.get_follow_up(out["id"])
        self.assertEqual(row["persona"], "eddy")
        self.assertEqual(row["created_by"], "eddy")
        self.assertTrue(row["due_at"].endswith("T18:00:00"))


# ---------- wiring ----------

class WiringTests(unittest.TestCase):
    def test_scheduler_has_follow_up_sweep(self):
        from apps.workshop_bot.scheduler.jobs import by_id
        spec = by_id("follow-up-sweep")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.cron, "23 * * * *")
        from apps.workshop_bot.scheduler import handlers
        self.assertIs(handlers._content_job_runner("follow-up-sweep"), follow_up.sweep)

    def test_followup_subgroup_wired(self):
        from apps.workshop_bot.personas import commands
        tree = commands.register_eddy_commands(MagicMock())
        top = next(g for g in tree.groups if getattr(g, "name", None) == "eddy")
        fu = next(c for c in top.commands if getattr(c, "name", None) == "followup")
        self.assertEqual({getattr(c, "_cmd_name", None) for c in fu.commands},
                         {"list", "add", "cancel"})

    def test_followup_tools_registered(self):
        for name in ("followup__schedule", "followup__list", "followup__cancel"):
            self.assertIn(name, agent_tools.FUNCS)
            self.assertIn(name, agent_tools.SPECS)


class FollowUpSweepLockTests(_DBCase):
    """The hourly sweep grabs a whole-job lock so a slow run can't
    overlap the next cron fire or a manual invocation."""

    def test_concurrent_sweep_is_blocked_by_job_lock(self):
        # Pre-acquire the lock so the actual sweep sees "already running."
        from apps.workshop_bot.jobs._base import job_lock
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        db.insert_follow_up(persona="eddy", trigger_kind="time",
                             note="x", due_at=past)
        ft = _FakeTeam(persona="eddy")
        with job_lock([f"job:{follow_up.NAME}"], follow_up.NAME):
            res = asyncio.run(follow_up.sweep(ft.ctx()))
        self.assertTrue(res.ok)
        self.assertIn("already running", res.message)
        ft.bot.core.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
