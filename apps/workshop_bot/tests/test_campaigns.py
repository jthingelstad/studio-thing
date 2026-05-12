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
from apps.workshop_bot.tools import context, db  # noqa: E402


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
        from apps.workshop_bot.tools import rss
        with patch.object(rss, "latest_published_issue", lambda: None):
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
        tree = commands.register_workshop_commands(MagicMock())
        workshop = tree.groups[0]
        promo = next(c for c in workshop.commands if getattr(c, "name", None) == "promo")
        self.assertIn("metrics", {getattr(c, "_cmd_name", None) for c in promo.commands})
        campaign = next(c for c in workshop.commands if getattr(c, "name", None) == "campaign")
        self.assertEqual(
            {getattr(c, "_cmd_name", None) for c in campaign.commands},
            {"add", "report", "copy", "sunset"},
        )


if __name__ == "__main__":
    unittest.main()
