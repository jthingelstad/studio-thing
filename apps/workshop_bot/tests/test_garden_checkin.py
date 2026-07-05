"""garden-checkin — Eddy's tending pass over the idea garden.

Covers the reworked behavior: the job builds the garden context in code
(seed batch + open clusters + remaining-count line), runs Eddy's agent loop,
posts only on a non-PASS report, and is triggerable from the /seeds page.
"""

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

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from apps.workshop_bot.jobs import _base, garden_checkin  # noqa: E402
from apps.workshop_bot.scheduler import handlers, jobs as sched_jobs  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.llm import anthropic_client  # noqa: E402
from apps.workshop_bot.webapp import routes, server  # noqa: E402

LOGIN = "jthingelstad@github"
H = {server.IDENTITY_HEADER: LOGIN}


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


def _run_with(reply="PASS"):
    """Run the job with a stubbed bot; return (result, ctx, bot)."""
    ctx = _base.JobContext()
    ctx.post = AsyncMock(return_value=True)
    bot = _bot(reply)
    with patch.object(garden_checkin._llm_job, "resolve_bot_and_channel",
                      return_value=(bot, "chan", "")):
        res = asyncio.run(garden_checkin.run(ctx))
    return res, ctx, bot


class GardenTendTests(_DBCase):
    def test_empty_garden_passes(self):
        res = asyncio.run(garden_checkin.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("empty garden", res.message)

    def test_context_includes_seed_batch_and_clusters(self):
        db.seed_add("Owning your words on your own domain", title="Own your words",
                    tags="indieweb")
        db.seed_add("RSS is quietly the best social network")
        clustered = db.seed_add("POSSE as a publishing posture")
        db.seed_cluster_create("IndieWeb ownership", note="his oldest thread",
                               seed_ids=[clustered["id"]])
        _res, _ctx, bot = _run_with("PASS")
        latest = bot.core.await_args.kwargs["latest"]
        # The tending instruction is loaded from the prompt file…
        self.assertIn("CLUSTER", latest)
        # …and the context block is built in code: seeds with id/title/tags/body…
        self.assertIn("Owning your words on your own domain", latest)
        self.assertIn("Own your words", latest)
        self.assertIn("[tags: indieweb]", latest)
        self.assertIn("RSS is quietly the best social network", latest)
        # …plus existing open clusters with label, note, and seed count.
        self.assertIn('"IndieWeb ownership" (1 seeds)', latest)
        self.assertIn("his oldest thread", latest)
        # Already-clustered seeds don't appear in the ungrouped batch.
        self.assertNotIn("- seed #%d" % clustered["id"], latest)

    def test_pass_does_not_post(self):
        db.seed_add("an idea")
        res, ctx, _bot_ = _run_with("PASS")
        self.assertTrue(res.ok)
        self.assertFalse(res.data["posted"])
        ctx.post.assert_not_awaited()

    def test_report_posts(self):
        db.seed_add("an idea")
        res, ctx, _bot_ = _run_with(
            "Clustered 3 seeds into \"IndieWeb ownership\". That cluster is ready "
            "to become an article — he's circled it since WT287.")
        self.assertTrue(res.data["posted"])
        ctx.post.assert_awaited_once()

    def test_batch_cap_and_remaining_line(self):
        for i in range(garden_checkin.BATCH_CAP + 5):
            db.seed_add(f"idea number {i}")
        _res, _ctx, bot = _run_with("PASS")
        latest = bot.core.await_args.kwargs["latest"]
        self.assertEqual(latest.count("- seed #"), garden_checkin.BATCH_CAP)
        self.assertIn("(5 more ungrouped seeds remain beyond this batch", latest)
        # Oldest seeds come first — the long-waiting ones get tended.
        self.assertIn("idea number 0", latest)
        self.assertNotIn(f"idea number {garden_checkin.BATCH_CAP + 4}", latest)

    def test_no_remaining_line_when_batch_covers_all(self):
        db.seed_add("only idea")
        _res, _ctx, bot = _run_with("PASS")
        latest = bot.core.await_args.kwargs["latest"]
        # Match the dynamic count line's unique phrasing ("remain beyond
        # this batch") — the prompt's instruction text says "the batch", so
        # a looser check would false-positive on the boilerplate.
        self.assertNotIn("remain beyond this batch", latest)
        self.assertIn("nothing waiting beyond this batch", latest)

    def test_seed_bodies_truncated(self):
        db.seed_add("word " * 200)  # ~1000 chars
        _res, _ctx, bot = _run_with("PASS")
        latest = bot.core.await_args.kwargs["latest"]
        self.assertIn("…", latest)
        self.assertNotIn("word " * 100, latest)

    def test_zero_ungrouped_is_ripeness_review(self):
        s = db.seed_add("clustered idea")
        db.seed_cluster_create("A real theme", seed_ids=[s["id"]])
        res, _ctx, bot = _run_with("PASS")
        self.assertTrue(res.ok)
        latest = bot.core.await_args.kwargs["latest"]
        self.assertIn("ripeness review", latest)
        self.assertIn('"A real theme"', latest)

    def test_records_agent_run_with_garden_tend_trigger(self):
        db.seed_add("an idea")
        _run_with("PASS")
        runs = db.recent_agent_runs(limit=3)
        self.assertTrue(any(r["trigger"] == "garden-tend" and r["agent_name"] == "eddy"
                            for r in runs))


class GardenTendPromptTests(unittest.TestCase):
    def test_prompt_pins_the_constraints(self):
        # The one rule (Jamie's seed bodies are verbatim) and the
        # propose-don't-graduate boundary live in the prompt itself — pin them
        # so a future edit can't silently drop either.
        anthropic_client._prompt_cache.pop("eddy-garden-tend", None)
        prompt = anthropic_client.load_prompt("eddy-garden-tend")
        self.assertIn("NEVER rewrite a seed's body", prompt)
        self.assertIn("preserved verbatim", prompt)
        self.assertIn("never call `seeds__graduate` yourself", prompt)
        self.assertIn("AT MOST ONE ripe candidate", prompt)
        self.assertIn("`PASS`", prompt)
        # Evocative-not-generic cluster labels.
        self.assertIn('not "Technology"', prompt)


class SeedsTendWebTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        os.environ.setdefault("TAILSCALE_ALLOWED_LOGIN", LOGIN)
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmpdir.cleanup()

    async def _client(self):
        app = web.Application(middlewares=[server._identity_mw])
        app[server.DEPS] = None
        routes.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_tend_runs_job_and_redirects(self):
        c = await self._client()
        with patch.object(garden_checkin, "run",
                          AsyncMock(return_value=_base.JobResult(True, "ok"))) as run:
            r = await c.post("/seeds/tend", headers=H, allow_redirects=False)
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/seeds")
        run.assert_awaited_once()

    async def test_seeds_page_has_tend_button(self):
        c = await self._client()
        r = await c.get("/seeds", headers=H)
        body = await r.text()
        self.assertEqual(r.status, 200)
        self.assertIn('action="/seeds/tend"', body)
        self.assertIn("Tend garden", body)


class SchedulerWiringTests(unittest.TestCase):
    def test_garden_checkin_registered(self):
        self.assertIsNotNone(handlers._content_job_runner("garden-checkin"))
        self.assertIsNotNone(sched_jobs.by_id("garden-checkin"))


if __name__ == "__main__":
    unittest.main()
