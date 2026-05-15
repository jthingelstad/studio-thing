"""Tests for the ``send-to-buttondown`` workshop_bot job.

The job is a thin async wrapper around
``pipeline.content.content.buttondown_publish_idempotent`` — its own logic
is the publish.md presence check, the Discord card formatting, and the
typed-exception catch. Tests stub the pipeline module so no real HTTP
hits Buttondown.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, send_to_buttondown  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
)


class _FakeButtondownErr(RuntimeError):
    """Stand-in for ``ButtondownPublishError`` in the fake pipeline module."""


def _fake_pipeline(result=None, *, raise_with=None):
    """Build a stub pipeline module with the two attributes the job
    references: ``buttondown_publish_idempotent`` and
    ``ButtondownPublishError``. Pass ``result`` to set the return value
    of the publisher call, or ``raise_with`` (a string) to make it raise
    ``ButtondownPublishError``."""
    mod = MagicMock()
    mod.ButtondownPublishError = _FakeButtondownErr
    if raise_with is not None:
        mod.buttondown_publish_idempotent = MagicMock(
            side_effect=_FakeButtondownErr(raise_with)
        )
    else:
        mod.buttondown_publish_idempotent = MagicMock(return_value=result or {})
    return mod


class SendToButtondownTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )

    def _ctx(self):
        fc = _FakeBotChannel(persona="eddy")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_refuses_if_no_active_window(self):
        ctx, fc = self._ctx()
        result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)

    def test_refuses_if_publish_md_missing(self):
        self._window()
        # No publish.md in the workspace.
        ctx, fc = self._ctx()
        result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no `publish.md`", result.message)
        self.assertIn("/eddy issue publish", result.message)
        fc.channel.send.assert_awaited()  # error surfaced to #editorial

    def test_refuses_if_publish_md_empty(self):
        self._window()
        self.ws.write_issue_file(458, "publish.md", "   \n   ")
        ctx, fc = self._ctx()
        result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no `publish.md`", result.message)

    def test_created_action_posts_success_card(self):
        self._window()
        self.ws.write_issue_file(458, "publish.md", "## Notable\n\nbody")
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(result={
            "action": "created",
            "id": "new-uuid-001",
            "subject": "Weekly Thing 458 / A, B, C",
            "slug": "458",
            "body_chars": 16,
            "description_chars": 1,
        })
        with patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["action"], "created")
        self.assertEqual(result.data["buttondown_id"], "new-uuid-001")
        # The card surfaces the Buttondown draft URL.
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("Created Buttondown draft", sent)
        self.assertIn("https://buttondown.com/emails/new-uuid-001", sent)
        self.assertIn("Weekly Thing 458", sent)
        self.assertIn("Re-run `/eddy issue send`", sent)

    def test_updated_action_says_updated(self):
        self._window()
        self.ws.write_issue_file(458, "publish.md", "## Notable\n\nbody")
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(result={
            "action": "updated",
            "id": "existing-uuid",
            "subject": "Weekly Thing 458 / A, B, C",
            "slug": "458",
            "body_chars": 16,
            "description_chars": 1,
        })
        with patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["action"], "updated")
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("Updated Buttondown draft", sent)
        self.assertIn("https://buttondown.com/emails/existing-uuid", sent)

    def test_pipeline_error_surfaces_to_channel(self):
        self._window()
        self.ws.write_issue_file(458, "publish.md", "## Notable\n\nbody")
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(raise_with="Buttondown POST failed (422): validation error")
        with patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("422", result.message)
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("422", sent)

    def test_concurrent_run_blocked_by_job_lock(self):
        self._window()
        self.ws.write_issue_file(458, "publish.md", "## Notable\n\nbody")
        ctx, fc = self._ctx()
        # Pre-acquire the same asset lock the job opens (metadata.json).
        with _base.job_lock([f"{458}/metadata.json"], send_to_buttondown.NAME):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)


if __name__ == "__main__":
    unittest.main()
