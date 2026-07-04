"""``reset-issue`` job — drop the gate artifacts for final / publish."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, reset_issue  # noqa: E402
from apps.workshop_bot.tools import content_store, db, issue_items  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
)


class _Case(_DBTestCase):
    def _window(self, n=349):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-23", 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )

    def _ctx(self):
        fc = _FakeBotChannel(persona="eddy")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()


class ResetFinalTests(_Case):

    def test_deletes_thesis(self):
        self._window()
        content_store.write_issue(349, "thesis.md", "thesis line")
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="final"))
        self.assertTrue(result.ok, result.message)
        self.assertIsNone(content_store.read_issue(349, "thesis.md"))
        # Confirmation posted to #editorial.
        fc.channel.send.assert_awaited()
        # Message reads naturally.
        self.assertIn("reset-final", result.message)
        self.assertIn("WT349", result.message)

    def test_clears_promotions(self):
        self._window()
        rid = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        issue_items.promote(rid, promoted_position="after_notable", promoted_heading="Feature")
        content_store.write_issue(349, "thesis.md", "thesis line")
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="final"))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["promotions_cleared"], 1)
        self.assertEqual(issue_items.promoted_items(349), [])

    def test_idempotent_when_artifacts_absent(self):
        self._window()
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="final"))
        self.assertTrue(result.ok)
        self.assertIn("nothing to reset", result.message)
        self.assertEqual(result.data["deleted"], [])

    def test_does_not_touch_publish_artifacts(self):
        self._window()
        content_store.write_issue(349, "thesis.md", "t")
        self.ws.write_issue_file(349, "buttondown.md", "p")  # generated S3 artifact
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="final"))
        self.assertTrue(result.ok)
        self.assertIsNone(content_store.read_issue(349, "thesis.md"))
        self.assertIn((349, "buttondown.md"), self.ws.files)


class ResetPublishTests(_Case):

    def test_deletes_buttondown_md(self):
        self._window()
        self.ws.write_issue_file(349, "buttondown.md", "p")  # generated S3 artifact
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="publish"))
        self.assertTrue(result.ok)
        self.assertNotIn((349, "buttondown.md"), self.ws.files)

    def test_does_not_touch_thesis(self):
        self._window()
        content_store.write_issue(349, "thesis.md", "t")
        self.ws.write_issue_file(349, "buttondown.md", "p")  # generated S3 artifact
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="publish"))
        self.assertTrue(result.ok)
        self.assertIsNotNone(content_store.read_issue(349, "thesis.md"))
        self.assertNotIn((349, "buttondown.md"), self.ws.files)

    def test_does_not_touch_buttondown_id(self):
        # metadata.json must survive — re-publishing should PATCH the
        # same Buttondown draft via the stored buttondown_id, not POST
        # a fresh one.
        self._window()
        content_store.write_issue(
            349, "metadata.json",
            '{"subject":"x","buttondown_id":"em_abc123"}',
        )
        self.ws.write_issue_file(349, "buttondown.md", "p")  # generated S3 artifact
        ctx, fc = self._ctx()
        asyncio.run(reset_issue.run(ctx, step="publish"))
        meta = content_store.read_issue(349, "metadata.json")
        self.assertIsNotNone(meta)
        self.assertIn("em_abc123", meta)

    def test_does_not_clear_promotions(self):
        # Promotions belong to the editorial pass, not the publish pass.
        self._window()
        rid = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        issue_items.promote(rid, promoted_position="after_notable", promoted_heading="F")
        self.ws.write_issue_file(349, "buttondown.md", "p")  # generated S3 artifact
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="publish"))
        self.assertTrue(result.ok)
        # publish-step doesn't touch promotions.
        self.assertEqual(result.data.get("promotions_cleared", 0), 0)
        self.assertEqual(len(issue_items.promoted_items(349)), 1)


class ResetValidationTests(_Case):

    def test_rejects_unknown_step(self):
        self._window()
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="haiku"))
        self.assertFalse(result.ok)
        self.assertIn("unknown reset step", result.message)

    def test_rejects_when_no_active_window(self):
        ctx, fc = self._ctx()
        result = asyncio.run(reset_issue.run(ctx, step="final"))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)


if __name__ == "__main__":
    unittest.main()
