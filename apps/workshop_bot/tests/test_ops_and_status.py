"""Tests for the ``/eddy status`` snapshot and agent-run accounting."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base  # noqa: E402
from apps.workshop_bot.jobs import status as status_job
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


class RecentAgentRunsTests(_DBCase):
    def test_orders_newest_first(self):
        with db.AgentRun("eddy", trigger="manual"):
            pass
        with db.AgentRun("eddy", trigger="compose-meta"):
            pass
        rows = db.recent_agent_runs(limit=5)
        self.assertEqual([r["trigger"] for r in rows], ["compose-meta", "manual"])
        self.assertEqual(rows[0]["status"], "success")


class AgentRunRecordMetaTests(_DBCase):
    """``AgentRun.record_meta(meta)`` captures the model + token usage
    out of agent_loop's return so cost analysis can be reconstructed
    from the agent_runs table."""

    def test_single_meta_populates_columns(self):
        meta = {
            "model": "claude-sonnet-5",
            "usage": {"input": 1500, "output": 700, "cache_read": 200, "cache_create": 50},
            "iterations": 1,
        }
        with db.AgentRun("eddy", trigger="compose-meta:subject") as run:
            run.record_meta(meta)
        rows = db.recent_agent_runs(limit=1)
        r = rows[0]
        self.assertEqual(r["model"], "claude-sonnet-5")
        self.assertEqual(r["input_tokens"], 1500)
        self.assertEqual(r["output_tokens"], 700)
        self.assertEqual(r["cache_read_tokens"], 200)
        self.assertEqual(r["cache_create_tokens"], 50)

    def test_multiple_metas_accumulate(self):
        """A job can call record_meta many times under one outer AgentRun.
        Tokens should sum, not overwrite."""
        with db.AgentRun("eddy", trigger="multi-step-job") as run:
            run.record_meta(
                {
                    "model": "claude-sonnet-5",
                    "usage": {"input": 1000, "output": 200, "cache_read": 0, "cache_create": 0},
                }
            )
            run.record_meta(
                {
                    "model": "claude-sonnet-5",
                    "usage": {"input": 800, "output": 150, "cache_read": 100, "cache_create": 0},
                }
            )
            run.record_meta(
                {
                    "model": "claude-sonnet-5",
                    "usage": {"input": 1200, "output": 300, "cache_read": 0, "cache_create": 25},
                }
            )
        r = db.recent_agent_runs(limit=1)[0]
        self.assertEqual(r["input_tokens"], 3000)
        self.assertEqual(r["output_tokens"], 650)
        self.assertEqual(r["cache_read_tokens"], 100)
        self.assertEqual(r["cache_create_tokens"], 25)

    def test_no_record_meta_leaves_columns_null(self):
        """Runs that didn't make an LLM call (e.g., the scheduler's
        outer wrapper) leave token columns NULL so SUM() queries
        ignore them."""
        with db.AgentRun("scheduler", trigger="scheduled:thingy-watch"):
            pass
        r = db.recent_agent_runs(limit=1)[0]
        self.assertIsNone(r["model"])
        self.assertIsNone(r["input_tokens"])
        self.assertIsNone(r["output_tokens"])
        self.assertIsNone(r["cache_read_tokens"])
        self.assertIsNone(r["cache_create_tokens"])

    def test_record_meta_tolerates_empty_or_missing_keys(self):
        with db.AgentRun("eddy", trigger="manual") as run:
            run.record_meta(None)
            run.record_meta({})
            run.record_meta({"model": "claude-opus-4-7"})  # no usage
            run.record_meta({"usage": {"input": 100}})  # partial usage
        r = db.recent_agent_runs(limit=1)[0]
        self.assertEqual(r["model"], "claude-opus-4-7")
        self.assertEqual(r["input_tokens"], 100)
        self.assertEqual(r["output_tokens"], 0)
        self.assertEqual(r["cache_read_tokens"], 0)
        self.assertEqual(r["cache_create_tokens"], 0)


class StatusJobTests(_DBCase):
    def test_empty_ish_snapshot(self):
        res = _run(status_job.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("workshop_bot status", res.message)
        self.assertIn("issue window: *(none", res.message)
        self.assertNotIn("members → 50", res.message)
        self.assertNotIn("campaigns", res.message)
        self.assertIn("none held", res.message)
        self.assertIn("none recorded yet", res.message)

    def test_populated_snapshot(self):
        db.set_issue_window(
            issue_number=460,
            pub_date="2026-05-30",
            end_date="2026-05-29",
            start_date="2026-05-22",
            day_count=7,
        )
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
        self.assertIn("460/draft.md", res.message)
        self.assertIn("update-draft", res.message)
        self.assertIn("eddy", res.message)
        self.assertEqual(res.data["issue_window"]["issue_number"], 460)


class WiringTests(unittest.TestCase):
    def test_status_command_wired(self):
        from apps.workshop_bot.personas import commands

        # /eddy status is a top-level subcommand on Eddy's tree.
        eddy_tree = commands.register_eddy_commands(MagicMock())
        eddy = next(g for g in eddy_tree.groups if getattr(g, "name", None) == "eddy")
        top_names = {getattr(c, "_cmd_name", None) for c in eddy.commands}
        self.assertIn("status", top_names)


if __name__ == "__main__":
    unittest.main()
