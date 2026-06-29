"""garden-checkin — Eddy's proactive idea-garden nudge."""

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

from apps.workshop_bot.jobs import _base, garden_checkin  # noqa: E402
from apps.workshop_bot.scheduler import handlers, jobs as sched_jobs  # noqa: E402
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


def _bot(reply):
    b = MagicMock()
    b.core = AsyncMock(return_value=(reply, {"iterations": 1}))
    return b


class GardenCheckinTests(_DBCase):
    def test_empty_garden_passes(self):
        res = asyncio.run(garden_checkin.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("empty garden", res.message)

    def test_posts_when_something_ripe(self):
        db.seed_add("an idea")
        ctx = _base.JobContext()
        ctx.post = AsyncMock(return_value=True)
        with patch.object(garden_checkin._llm_job, "resolve_bot_and_channel",
                          return_value=(_bot("That cluster is ready for an article."), "chan", "")):
            res = asyncio.run(garden_checkin.run(ctx))
        self.assertTrue(res.data["posted"])
        ctx.post.assert_awaited_once()

    def test_pass_does_not_post(self):
        db.seed_add("an idea")
        ctx = _base.JobContext()
        ctx.post = AsyncMock(return_value=True)
        with patch.object(garden_checkin._llm_job, "resolve_bot_and_channel",
                          return_value=(_bot("PASS"), "chan", "")):
            res = asyncio.run(garden_checkin.run(ctx))
        self.assertFalse(res.data["posted"])
        ctx.post.assert_not_awaited()


class SchedulerWiringTests(unittest.TestCase):
    def test_garden_checkin_registered(self):
        self.assertIsNotNone(handlers._content_job_runner("garden-checkin"))
        self.assertIsNotNone(sched_jobs.by_id("garden-checkin"))


if __name__ == "__main__":
    unittest.main()
