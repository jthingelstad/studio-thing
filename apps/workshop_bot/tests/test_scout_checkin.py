"""scout-checkin — the agentic state-of-the-slate note + build_scout_context."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, scout_checkin  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.content import context  # noqa: E402


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


class BuildScoutContextTests(_DBCase):
    def test_empty_slate(self):
        ctx = context.build_scout_context()
        self.assertIn("today", ctx)
        self.assertEqual(ctx["active_newsletters"], [])

    def test_with_active_newsletter(self):
        db.plan_issue_window(issue_number=360, pub_date="2026-06-27",
                             end_date="2026-06-26", start_date="2026-06-19", day_count=7)
        ctx = context.build_scout_context()
        self.assertEqual([w["issue"] for w in ctx["active_newsletters"]], [360])


class ScoutCheckinTests(_DBCase):
    def test_empty_slate_passes_without_agent_call(self):
        res = asyncio.run(scout_checkin.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("empty slate", res.message)

    def test_posts_when_agent_has_something_to_say(self):
        db.plan_issue_window(issue_number=360, pub_date="2026-06-27",
                             end_date="2026-06-26", start_date="2026-06-19", day_count=7)
        ctx = _base.JobContext()
        ctx.post = AsyncMock(return_value=True)
        fake_bot = unittest_mock_bot("Heads up — WT360 ships Saturday and has no cover yet.")
        with patch.object(scout_checkin._llm_job, "resolve_bot_and_channel",
                          return_value=(fake_bot, "chan", "")):
            res = asyncio.run(scout_checkin.run(ctx))
        self.assertTrue(res.ok)
        self.assertTrue(res.data["posted"])
        ctx.post.assert_awaited_once()

    def test_pass_reply_does_not_post(self):
        db.plan_issue_window(issue_number=360, pub_date="2026-06-27",
                             end_date="2026-06-26", start_date="2026-06-19", day_count=7)
        ctx = _base.JobContext()
        ctx.post = AsyncMock(return_value=True)
        fake_bot = unittest_mock_bot("PASS")
        with patch.object(scout_checkin._llm_job, "resolve_bot_and_channel",
                          return_value=(fake_bot, "chan", "")):
            res = asyncio.run(scout_checkin.run(ctx))
        self.assertTrue(res.ok)
        self.assertFalse(res.data["posted"])
        ctx.post.assert_not_awaited()


def unittest_mock_bot(reply: str):
    from unittest.mock import MagicMock
    bot = MagicMock()
    bot.core = AsyncMock(return_value=(reply, {"iterations": 1}))
    return bot


if __name__ == "__main__":
    unittest.main()
