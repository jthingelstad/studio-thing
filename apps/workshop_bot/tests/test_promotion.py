"""Marky's promotion-prep job (phase-driven sharing — no RSS poll)."""

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

from apps.workshop_bot.jobs import _base, promotion_prep  # noqa: E402
from apps.workshop_bot.tools import db, s3  # noqa: E402
from apps.workshop_bot.tools.content import context


class _FakeWorkspace:
    def __init__(self):
        self.files: dict[tuple[int, str], str] = {}

    def read_issue_file(self, n, fn, *, max_bytes=None):
        key = (int(n), fn)
        if key in self.files:
            return {"found": True, "text": self.files[key]}
        return {"found": False}


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        db.run_migrations()
        self.ws = _FakeWorkspace()
        self._p = patch.object(s3, "read_issue_file", self.ws.read_issue_file)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()


def _marky_deps(reply="🪧 Promotion drafts — WT458\n\n## LinkedIn\n1. ..."):
    channel = MagicMock(); channel.send = AsyncMock()
    marky = MagicMock(); marky.user = object(); marky.get_channel = MagicMock(return_value=channel)
    marky.core = AsyncMock(return_value=(reply, {"iterations": 1}))
    team = MagicMock(); team.bots = {"marky": marky}
    deps = MagicMock(); deps.team = team
    return deps, marky, channel


class PromotionPrepJobTests(_DBCase):
    def setUp(self):
        super().setUp()
        # Patch the semantic retrieval at the archive_context boundary
        # so tests are deterministic regardless of whether
        # LIBRARIAN_BRIDGE_SECRET happens to be set in the dev env. The
        # default canned response is empty (fresh territory); individual
        # tests can override via self._retrieve_mock.return_value if
        # they want to assert thread-context inclusion.
        from apps.workshop_bot.tools import archive_context, thingy_retrieve
        patcher = patch.object(
            archive_context.thingy_retrieve, "retrieve",
            return_value=[],
        )
        self._retrieve_mock = patcher.start()
        self.addCleanup(patcher.stop)
        # Surface the error class on the test for failure-path tests.
        self._ThingyRetrieveError = thingy_retrieve.ThingyRetrieveError

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_PROMOTION", None)
        super().tearDown()

    def test_no_draft_md_errors(self):
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        with patch.object(db, "get_latest_issue", lambda: {"number": 458, "publish_date": "2026-05-16"}):
            result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps)))
        self.assertFalse(result.ok)
        self.assertIn("no `draft.md`", result.message)
        marky.core.assert_not_awaited()

    def test_drafts_and_posts(self):
        self.ws.files[(458, "draft.md")] = "## Notable\n\n### [Thing](http://x)\n\nblurb\n"
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["posted"])
        marky.core.assert_awaited()
        channel.send.assert_awaited()
        # The publish body was fed to Marky.
        sent = marky.core.call_args.kwargs["latest"]
        self.assertIn("### [Thing](http://x)", sent)
        self.assertIn("## Today", sent)

    def test_skips_when_no_team(self):
        self.ws.files[(458, "draft.md")] = "## Notable\n\nx"
        result = asyncio.run(promotion_prep.run(_base.JobContext(), issue_number=458))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])

    def test_body_is_truncated_to_promotion_body_cap(self):
        # An oversized draft.md must be capped at PROMOTION_BODY_CAP before
        # being fed to Marky, otherwise a runaway issue body could blow up
        # the user-message size.
        from apps.workshop_bot.jobs import _llm_job
        cap = _llm_job.PROMOTION_BODY_CAP
        huge = "## Notable\n\n" + ("x" * (cap + 5_000))
        self.ws.files[(458, "draft.md")] = huge
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertTrue(result.ok, result.message)
        sent = marky.core.call_args.kwargs["latest"]
        # The fenced markdown block carries at most `cap` body chars.
        body = sent.split("```markdown\n", 1)[1].rsplit("\n```", 1)[0]
        self.assertEqual(len(body), cap)
        # And the cap is the constant, not a magic number elsewhere.
        self.assertEqual(_llm_job.PROMOTION_BODY_CAP, _llm_job.ISSUE_BODY_CAP + 8_000)

    def test_thread_context_block_injected_when_retrieval_returns_data(self):
        """When Thingy /retrieve returns hits, the Recurring thread
        context block lands in the prompt so Marky can write multi-issue
        arc framings."""
        self.ws.files[(458, "draft.md")] = "## Notable\n\n### [Thing](http://x)\n\nblurb on agents and tooling\n"
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        self._retrieve_mock.return_value = [
            {"issue_number": 309, "subject": "Programming, Silence, Drones",
             "publish_date": "2025-02-16", "section": "Notable",
             "text": "Earlier take on the same thread — O'Reilly's piece on the end of programming."},
            {"issue_number": 341, "subject": "Minions, MAX, ReMemory",
             "publish_date": "2026-02-15", "section": "Notable",
             "text": "Adoption-phase framing for AI tooling."},
        ]
        result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertTrue(result.ok, result.message)
        sent = marky.core.call_args.kwargs["latest"]
        self.assertIn("## Recurring thread context", sent)
        self.assertIn("**WT309**", sent)
        self.assertIn("**WT341**", sent)
        # Retrieval was called with the issue body, capped to the query cap.
        call_args = self._retrieve_mock.call_args
        query = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
        self.assertIn("agents and tooling", query)
        self.assertEqual(call_args.kwargs.get("k"), promotion_prep._THREAD_CONTEXT_K)

    def test_thread_context_block_renders_outage_when_retrieval_fails(self):
        """A Lambda outage doesn't block the job — the block surfaces
        the error and Marky proceeds as a one-off."""
        self.ws.files[(458, "draft.md")] = "## Notable\n\nbody"
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        self._retrieve_mock.side_effect = self._ThingyRetrieveError("timeout")
        result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertTrue(result.ok, result.message)
        sent = marky.core.call_args.kwargs["latest"]
        self.assertIn("## Recurring thread context", sent)
        self.assertIn("retrieval unavailable", sent)

    def test_concurrent_run_is_blocked_by_job_lock(self):
        # Pre-acquire the whole-job lock so the next run bails before doing
        # any work — proves a re-fire (manual + the put-to-bed auto-fire, say)
        # doesn't produce duplicate #promotion posts.
        self.ws.files[(458, "draft.md")] = "## Notable\n\nx"
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        with _base.job_lock([f"job:{promotion_prep.NAME}"], promotion_prep.NAME):
            result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        marky.core.assert_not_awaited()


class MarkyContextTests(_DBCase):
    def test_build_marky_context(self):
        from datetime import date
        with patch.object(db, "get_latest_issue", lambda: {"number": 458, "publish_date": "2026-05-16"}):
            ctx = context.build_marky_context(ref_date=date(2026, 5, 20))
        self.assertEqual(ctx["latest_published_issue"], 458)
        self.assertEqual(ctx["ship_date"], "2026-05-16")
        self.assertEqual(ctx["days_since_ship"], 4)
        self.assertEqual(ctx["active_campaigns"], [])

    def test_build_marky_context_explicit(self):
        from datetime import date
        # Explicit args → no DB lookup.
        with patch.object(db, "get_latest_issue", side_effect=AssertionError("should not look up")):
            ctx = context.build_marky_context(ref_date=date(2026, 5, 20), latest_issue=460, ship_date="2026-05-23")
        self.assertEqual(ctx["latest_published_issue"], 460)


class SchedulerWiringTests(unittest.TestCase):
    def test_no_rss_check_job(self):
        # Sharing is phase-driven (put-to-bed auto-fires promotion-prep); there
        # is no RSS-poll job anymore.
        from apps.workshop_bot.scheduler import jobs as J
        ids = {j.id for j in J.JOBS}
        self.assertNotIn("marky-rss-check", ids)

    def test_promotion_prep_command_wired(self):
        from apps.workshop_bot.personas import commands
        # /marky prep is a top-level verb on Marky's tree.
        tree = commands.register_marky_commands(MagicMock())
        marky = next(g for g in tree.groups if getattr(g, "name", None) == "marky")
        self.assertIn("prep", {getattr(c, "_cmd_name", None) for c in marky.commands})


if __name__ == "__main__":
    unittest.main()
