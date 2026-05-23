"""Step 8 — campaign ledger + daily-metrics."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, add_campaign, campaign_report, daily_metrics, ops  # noqa: E402
from apps.workshop_bot.tools import db # noqa: E402
from apps.workshop_bot.tools.content import context


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


class CampaignDbTests(_DBCase):
    def test_insert_get_active(self):
        self.assertTrue(db.insert_campaign(name="dd-may", ref="dd-2026-05-15",
                                           expected_signups=50, expected_traffic=800,
                                           started_at="2026-05-15"))
        # Duplicate name → False.
        self.assertFalse(db.insert_campaign(name="dd-may", ref="dd-2026-05-15"))
        c = db.get_campaign("dd-may")
        self.assertEqual(c["ref"], "dd-2026-05-15")
        self.assertEqual(c["status"], "live")
        self.assertEqual(c["expected_signups"], 50)
        self.assertEqual([x["name"] for x in db.active_campaigns()], ["dd-may"])
        db.set_campaign_status("dd-may", "sunset")
        self.assertEqual(db.active_campaigns(), [])

    def test_metrics_and_latest(self):
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15")
        db.insert_campaign_metric(campaign_name="dd-may", signups=2, traffic=40)
        db.insert_campaign_metric(campaign_name="dd-may", signups=5, traffic=120)
        m = db.latest_campaign_metric("dd-may")
        self.assertEqual(m["signups"], 5)
        self.assertEqual(m["traffic"], 120)
        self.assertIsNone(db.latest_campaign_metric("nope"))

    def test_active_campaigns_with_age(self):
        from datetime import date
        ten_days_ago = (date.today() - __import__("datetime").timedelta(days=10)).isoformat()
        db.insert_campaign(name="x", ref="x-ref", started_at=ten_days_ago)
        rows = db.active_campaigns_with_age()
        self.assertEqual(rows[0]["days_running"], 10)

    def test_campaign_copy_roundtrip(self):
        db.insert_campaign(name="dd388", ref="DenseDiscovery-388", copy="Try The Weekly Thing.")
        self.assertEqual(db.get_campaign("dd388")["copy"], "Try The Weekly Thing.")
        self.assertTrue(db.set_campaign_copy("dd388", "New headline + blurb."))
        self.assertEqual(db.get_campaign("dd388")["copy"], "New headline + blurb.")
        self.assertEqual(db.active_campaigns()[0]["copy"], "New headline + blurb.")
        self.assertTrue(db.set_campaign_copy("dd388", None))
        self.assertIsNone(db.get_campaign("dd388")["copy"])
        self.assertFalse(db.set_campaign_copy("nope", "x"))

    def test_update_campaign(self):
        db.insert_campaign(name="dd", ref="OldRef-1", expected_signups=10, started_at="2026-05-01")
        # No changes → returns the row unchanged.
        same = db.update_campaign("dd")
        self.assertEqual(same["ref"], "OldRef-1")
        # Whitelisted fields update; ints coerced; non-editable keys ignored.
        updated = db.update_campaign("dd", ref="NewRef-2", expected_signups="42",
                                     ends_at="2026-06-01", notes="ran in the footer", status="hacked")
        self.assertEqual(updated["ref"], "NewRef-2")
        self.assertEqual(updated["expected_signups"], 42)
        self.assertEqual(updated["ends_at"], "2026-06-01")
        self.assertEqual(updated["notes"], "ran in the footer")
        self.assertEqual(updated["name"], "dd")            # PK untouched
        self.assertEqual(updated["status"], "live")         # status not editable here
        self.assertEqual(updated["started_at"], "2026-05-01")  # not passed → kept
        # None values mean "leave alone".
        kept = db.update_campaign("dd", ref=None, notes=None)
        self.assertEqual(kept["ref"], "NewRef-2")
        # Unknown campaign → None.
        self.assertIsNone(db.update_campaign("nope", ref="x"))


class AddCampaignJobTests(_DBCase):
    def test_register(self):
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="dd-may", ref="dd-2026-05-15",
                                              expected_signups=50, expected_traffic=800))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(db.get_campaign("dd-may")["ref"], "dd-2026-05-15")

    def test_duplicate_name(self):
        asyncio.run(add_campaign.run(_base.JobContext(), name="dd-may", ref="dd-2026-05-15"))
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="dd-may", ref="other"))
        self.assertFalse(result.ok)
        self.assertIn("already exists", result.message)

    def test_bad_ref(self):
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="x", ref="Bad Ref!"))
        self.assertFalse(result.ok)

    def test_ref_case_is_preserved(self):
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="dd388", ref="DenseDiscovery-388"))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(db.get_campaign("dd388")["ref"], "DenseDiscovery-388")

    def test_register_with_copy(self):
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="dd388", ref="DenseDiscovery-388",
                                              copy="Headline\n\nBody blurb with a link."))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(db.get_campaign("dd388")["copy"], "Headline\n\nBody blurb with a link.")
        self.assertTrue(result.data["has_copy"])

    def test_register_with_ref_already_in_use_warns_but_succeeds(self):
        # Soft-warn — registration still goes through; the warning rides
        # in the ack so Jamie can decide to keep or rename.
        asyncio.run(add_campaign.run(_base.JobContext(), name="first", ref="DD-2026-05"))
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="second", ref="DD-2026-05"))
        self.assertTrue(result.ok, result.message)
        self.assertIn("already live on `first`", result.message)
        self.assertEqual(db.get_campaign("second")["ref"], "DD-2026-05")

    def test_register_with_sunset_ref_does_not_warn(self):
        # Re-using a ref from a sunset campaign is fine — the old one's
        # not being polled anymore, so no metric collision.
        asyncio.run(add_campaign.run(_base.JobContext(), name="old", ref="DD-2026-04"))
        db.set_campaign_status("old", "sunset")
        result = asyncio.run(add_campaign.run(_base.JobContext(), name="new", ref="DD-2026-04"))
        self.assertTrue(result.ok, result.message)
        self.assertNotIn("already live on", result.message)

    def test_register_with_none_name_returns_required_error(self):
        # Regression: previously `(str(name) or "").strip()` turned None into
        # the literal string "None" because str(None) == "None" — the `or ""`
        # fallback never fired. Should be rejected outright.
        result = asyncio.run(add_campaign.run(_base.JobContext(), name=None, ref="x-2026"))
        self.assertFalse(result.ok)
        self.assertIn("name is required", result.message)
        self.assertIsNone(db.get_campaign("None"))

    def test_campaign_copy_job_sets_and_clears(self):
        asyncio.run(add_campaign.run(_base.JobContext(), name="dd388", ref="DenseDiscovery-388"))
        r = asyncio.run(ops.campaign_copy(_base.JobContext(), name="dd388", copy="The actual ad."))
        self.assertTrue(r.ok, r.message)
        self.assertEqual(db.get_campaign("dd388")["copy"], "The actual ad.")
        r = asyncio.run(ops.campaign_copy(_base.JobContext(), name="dd388", copy=None))
        self.assertTrue(r.ok)
        self.assertIsNone(db.get_campaign("dd388")["copy"])
        r = asyncio.run(ops.campaign_copy(_base.JobContext(), name="nope", copy="x"))
        self.assertFalse(r.ok)


class CampaignEditJobTests(_DBCase):
    def test_edit_changes_only_passed_fields(self):
        asyncio.run(add_campaign.run(_base.JobContext(), name="dd", ref="OldRef-1",
                                     expected_signups=10, expected_traffic=200))
        r = asyncio.run(ops.campaign_edit(
            _base.JobContext(), name="dd", ref="NewRef-2", expected_signups=42,
            ends_at="2026-06-30", notes="ran in the footer slot",
        ))
        self.assertTrue(r.ok, r.message)
        c = db.get_campaign("dd")
        self.assertEqual(c["ref"], "NewRef-2")
        self.assertEqual(c["expected_signups"], 42)
        self.assertEqual(c["expected_traffic"], 200)        # not passed → kept
        self.assertEqual(c["ends_at"], "2026-06-30")
        self.assertEqual(c["notes"], "ran in the footer slot")
        self.assertEqual(c["status"], "live")
        # Message echoes the change list + the new state.
        self.assertIn("`ref`", r.message)
        self.assertIn("NewRef-2", r.message)

    def test_edit_with_no_fields_shows_current_state(self):
        asyncio.run(add_campaign.run(_base.JobContext(), name="dd", ref="R-1"))
        r = asyncio.run(ops.campaign_edit(_base.JobContext(), name="dd"))
        self.assertTrue(r.ok)
        self.assertIn("R-1", r.message)
        self.assertIn("no changes given", r.message)

    def test_edit_unknown_campaign(self):
        r = asyncio.run(ops.campaign_edit(_base.JobContext(), name="ghost", ref="x"))
        self.assertFalse(r.ok)
        self.assertIn("no campaign named", r.message)


class CampaignReportJobTests(_DBCase):
    def test_no_campaigns(self):
        result = asyncio.run(campaign_report.run(_base.JobContext()))
        self.assertTrue(result.ok)
        self.assertIn("No active campaigns", result.message)

    def test_report(self):
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15", expected_signups=50, expected_traffic=800,
                           copy="Discover something good every weekend.")
        db.insert_campaign_metric(campaign_name="dd-may", signups=10, traffic=200)
        result = asyncio.run(campaign_report.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        self.assertIn("dd-may", result.message)
        self.assertIn("10 / 50", result.message)
        self.assertIn("200 / 800", result.message)
        self.assertIn("Discover something good every weekend.", result.message)

    def test_report_flags_missing_copy(self):
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15")
        result = asyncio.run(campaign_report.run(_base.JobContext()))
        self.assertIn("none recorded", result.message)


class CampaignWindowDaysTests(unittest.TestCase):
    """Marky's `_campaign_window_days` picks a sensible attribution window
    for a campaign's age: ≤10 days → 7d, ≤45 days → 30d, else 60d. Falls
    back to 14d on missing / malformed dates."""

    def _at(self, days_ago: int) -> str:
        from datetime import date, timedelta
        return (date.today() - timedelta(days=days_ago)).isoformat()

    def test_none_fallback(self):
        self.assertEqual(daily_metrics._campaign_window_days(None), 14)
        self.assertEqual(daily_metrics._campaign_window_days(""), 14)

    def test_malformed_date_fallback(self):
        self.assertEqual(daily_metrics._campaign_window_days("not-a-date"), 14)
        self.assertEqual(daily_metrics._campaign_window_days("2026-13-99"), 14)

    def test_boundaries(self):
        # ≤10 days → 7d window
        self.assertEqual(daily_metrics._campaign_window_days(self._at(0)), 7)
        self.assertEqual(daily_metrics._campaign_window_days(self._at(10)), 7)
        # 11..45 days → 30d window
        self.assertEqual(daily_metrics._campaign_window_days(self._at(11)), 30)
        self.assertEqual(daily_metrics._campaign_window_days(self._at(45)), 30)
        # >45 days → 60d window
        self.assertEqual(daily_metrics._campaign_window_days(self._at(46)), 60)
        self.assertEqual(daily_metrics._campaign_window_days(self._at(180)), 60)


class DailyMetricsTests(_DBCase):
    def _patch_clients(self, *, growth, sources_by_source, attribution_by_ref, summary=None):
        from apps.workshop_bot.systems.buttondown import client as bd
        from apps.workshop_bot.systems.tinylytics import client as ty
        return [
            patch.object(bd, "subscriber_growth", lambda **kw: growth),
            patch.object(bd, "attribution_summary", lambda **kw: {"by_ref": attribution_by_ref}),
            patch.object(ty, "sources", lambda **kw: {"by_source": sources_by_source}),
            patch.object(ty, "summary", lambda **kw: summary or {"total_hits": 100}),
        ]

    def test_pass_when_nothing_moved(self):
        # No campaigns, flat subscriber growth → PASS, no post.
        patches = self._patch_clients(growth={"added": 1, "churned": 0, "net": 1, "by_source": {}},
                                      sources_by_source={}, attribution_by_ref={})
        for p in patches: p.start()
        try:
            result = asyncio.run(daily_metrics.run(_base.JobContext()))
        finally:
            for p in patches: p.stop()
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])
        self.assertIn("nothing material moved", result.message.lower())

    def test_first_campaign_poll_writes_metric_and_posts(self):
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15", expected_signups=50, expected_traffic=800,
                           copy="The placement copy that ran.")
        # Fake Marky bot.
        channel = MagicMock(); channel.send = AsyncMock()
        marky = MagicMock(); marky.user = object(); marky.get_channel = MagicMock(return_value=channel)
        marky.core = AsyncMock(return_value=("dd-may: first hits — 200 visits, 5 signups.", {"iterations": 1}))
        team = MagicMock(); team.bots = {"marky": marky}
        deps = MagicMock(); deps.team = team
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        patches = self._patch_clients(growth={"added": 2, "churned": 0, "net": 2, "by_source": {}},
                                      sources_by_source={"dd-2026-05-15": 200},
                                      attribution_by_ref={"dd-2026-05-15": 5})
        for p in patches: p.start()
        try:
            result = asyncio.run(daily_metrics.run(_base.JobContext(deps=deps)))
        finally:
            for p in patches: p.stop()
            os.environ.pop("DISCORD_CHANNEL_PROMOTION", None)
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["posted"])
        marky.core.assert_awaited()
        channel.send.assert_awaited()
        # A metrics row was written.
        m = db.latest_campaign_metric("dd-may")
        self.assertEqual(m["traffic"], 200)
        self.assertEqual(m["signups"], 5)
        # The campaign snapshot carries the copy so Marky can read perf vs creative.
        self.assertEqual(result.data["campaigns"][0]["copy"], "The placement copy that ran.")

    def test_subscriber_spike_triggers_report(self):
        channel = MagicMock(); channel.send = AsyncMock()
        marky = MagicMock(); marky.user = object(); marky.get_channel = MagicMock(return_value=channel)
        marky.core = AsyncMock(return_value=("Subscriber net +12 this week.", {}))
        team = MagicMock(); team.bots = {"marky": marky}
        deps = MagicMock(); deps.team = team
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        patches = self._patch_clients(growth={"added": 14, "churned": 2, "net": 12, "by_source": {"embed": 14}},
                                      sources_by_source={}, attribution_by_ref={})
        for p in patches: p.start()
        try:
            result = asyncio.run(daily_metrics.run(_base.JobContext(deps=deps)))
        finally:
            for p in patches: p.stop()
            os.environ.pop("DISCORD_CHANNEL_PROMOTION", None)
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["posted"])

    def test_concurrent_run_is_blocked_by_job_lock(self):
        # Two concurrent fires (cron + manual) would otherwise double-write
        # campaign_metrics rows. Pre-acquire the lock; run() should bail
        # with the "already running" message and never touch the API stubs.
        called = {"signups": 0, "traffic": 0}
        def _src(**kw):
            called["traffic"] += 1
            return {"by_source": {}}
        def _attr(**kw):
            called["signups"] += 1
            return {"by_ref": {}}
        from apps.workshop_bot.systems.buttondown import client as bd
        from apps.workshop_bot.systems.tinylytics import client as ty
        with _base.job_lock([f"job:{daily_metrics.NAME}"], daily_metrics.NAME):
            with patch.object(bd, "attribution_summary", _attr), \
                 patch.object(ty, "sources", _src), \
                 patch.object(bd, "subscriber_growth", lambda **kw: {"net": 99, "churned": 99}):
                result = asyncio.run(daily_metrics.run(_base.JobContext()))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        self.assertEqual(called, {"signups": 0, "traffic": 0})

    def test_moved_when_marky_pass_not_posted(self):
        channel = MagicMock(); channel.send = AsyncMock()
        marky = MagicMock(); marky.user = object(); marky.get_channel = MagicMock(return_value=channel)
        marky.core = AsyncMock(return_value=("PASS", {}))
        team = MagicMock(); team.bots = {"marky": marky}
        deps = MagicMock(); deps.team = team
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        patches = self._patch_clients(growth={"added": 5, "churned": 0, "net": 5, "by_source": {}},
                                      sources_by_source={}, attribution_by_ref={})
        for p in patches: p.start()
        try:
            result = asyncio.run(daily_metrics.run(_base.JobContext(deps=deps)))
        finally:
            for p in patches: p.stop()
            os.environ.pop("DISCORD_CHANNEL_PROMOTION", None)
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])
        channel.send.assert_not_awaited()


class MarkyContextWithCampaignsTests(_DBCase):
    def test_campaigns_in_context(self):
        from datetime import date, timedelta
        db.insert_campaign(name="dd-may", ref="dd-2026-05-15",
                           started_at=(date.today() - timedelta(days=3)).isoformat())
        # No issue filed in this temp DB → get_latest_issue() returns None,
        # so build_marky_context focuses on the campaign rows.
        ctx = context.build_marky_context(ref_date=date.today())
        self.assertEqual(len(ctx["active_campaigns"]), 1)
        self.assertEqual(ctx["active_campaigns"][0]["name"], "dd-may")
        self.assertEqual(ctx["active_campaigns"][0]["days_running"], 3)


class WiringTests(unittest.TestCase):
    def test_scheduler_has_daily_metrics_and_no_heartbeats(self):
        from apps.workshop_bot.scheduler import jobs as J
        ids = {j.id for j in J.JOBS}
        self.assertIn("marky-daily-metrics", ids)
        for hb in ("marky-heartbeat", "eddy-heartbeat", "patty-heartbeat", "linky-heartbeat"):
            self.assertNotIn(hb, ids)

    def test_campaign_commands_wired(self):
        from apps.workshop_bot.personas import commands
        tree = commands.register_marky_commands(MagicMock())
        marky = next(g for g in tree.groups if getattr(g, "name", None) == "marky")
        # /marky metrics is now a top-level verb (no /promo subgroup).
        self.assertIn("metrics", {getattr(c, "_cmd_name", None) for c in marky.commands})
        campaign = next(c for c in marky.commands if getattr(c, "name", None) == "campaign")
        self.assertEqual(
            {getattr(c, "_cmd_name", None) for c in campaign.commands},
            {"add", "edit", "report", "copy", "sunset"},
        )


if __name__ == "__main__":
    unittest.main()
