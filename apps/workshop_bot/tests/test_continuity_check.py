"""continuity-check — the archive as collaborator while Jamie writes.

Covers the job (``run_for_text``): retrieval is mocked (never the live
Librarian), Eddy's call is stubbed (never the live LLM). Asserts Eddy sees the
retrieved passages, the note posts to #editorial on success, a retrieval error
posts the fallback without crashing, the prompt pins the never-rewrite rule,
and the seed / production web routes 302 and invoke the job.
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

from apps.workshop_bot.jobs import _base, _llm_job, continuity_check  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.llm import anthropic_client  # noqa: E402
from apps.workshop_bot.webapp import routes, server  # noqa: E402

LOGIN = "jthingelstad@github"
H = {server.IDENTITY_HEADER: LOGIN}

_PASSAGE = {
    "issue_number": 303, "subject": "The metering question",
    "publish_date": "2020-05-10", "section": "Notable",
    "text": "Jamie's earlier take on metering and usage-based pricing.",
}


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


def _run(*, text="Some new draft about metering.", label="seed: metering",
         exclude_issue=None, reply="You've circled this in WT303 — same lean?",
         passages=None, error=None):
    """Run the job with retrieval + Eddy stubbed. Returns (res, ctx, bot, fetch)."""
    ctx = _base.JobContext()
    ctx.post = AsyncMock(return_value=True)
    bot = MagicMock()
    bot.core = AsyncMock(return_value=(reply, {"iterations": 1}))
    resolved = _llm_job.ResolvedBot(bot, "chan", None)
    fetch = MagicMock(return_value=(passages if passages is not None else [_PASSAGE], error))
    with patch.object(continuity_check._llm_job, "resolve_bot_and_channel",
                      return_value=resolved), \
         patch.object(continuity_check.archive_context, "fetch_archive_context", fetch):
        res = asyncio.run(continuity_check.run_for_text(
            ctx, text=text, label=label, exclude_issue=exclude_issue))
    return res, ctx, bot, fetch


class ContinuityCheckJobTests(_DBCase):
    def test_happy_path_calls_eddy_with_passages_and_posts(self):
        res, ctx, bot, _fetch = _run()
        self.assertTrue(res.ok)
        self.assertTrue(res.data["posted"])
        # Eddy is called once, and the retrieved passage is in his prompt.
        bot.core.assert_awaited_once()
        latest = bot.core.await_args.kwargs["latest"]
        self.assertIn("WT303", latest)
        self.assertIn("metering and usage-based pricing", latest)
        self.assertIn("Some new draft about metering.", latest)
        # The note posts to #editorial, framed with the label + Eddy's reply.
        ctx.post.assert_awaited_once()
        posted = ctx.post.await_args.args[1]
        self.assertIn("seed: metering", posted)
        self.assertIn("You've circled this in WT303", posted)
        self.assertEqual(ctx.post.await_args.kwargs.get("persona"), "eddy")

    def test_retrieval_error_posts_fallback_and_does_not_crash(self):
        res, ctx, bot, _fetch = _run(error="Librarian 503")
        self.assertTrue(res.ok)  # fail-soft, not a crash
        self.assertTrue(res.data.get("retrieval_failed"))
        bot.core.assert_not_awaited()  # never reached the LLM
        ctx.post.assert_awaited_once()
        fallback = ctx.post.await_args.args[1]
        self.assertIn("couldn't reach the archive", fallback)

    def test_empty_text_is_noop(self):
        res, ctx, bot, fetch = _run(text="   ")
        self.assertTrue(res.ok)
        self.assertIn("nothing to check", res.message)
        fetch.assert_not_called()
        bot.core.assert_not_awaited()
        ctx.post.assert_not_awaited()

    def test_exclude_issue_forwarded_to_retrieval(self):
        _res, _ctx, _bot, fetch = _run(label="WT359 intro", exclude_issue=359)
        self.assertEqual(fetch.call_args.kwargs["exclude_issue"], 359)

    def test_records_agent_run(self):
        _run()
        runs = db.recent_agent_runs(limit=3)
        self.assertTrue(any(r["trigger"] == "continuity-check" and r["agent_name"] == "eddy"
                            for r in runs))

    def test_bot_unavailable_skips_cleanly(self):
        ctx = _base.JobContext()
        ctx.post = AsyncMock(return_value=True)
        resolved = _llm_job.ResolvedBot(None, None, "eddy unavailable")
        with patch.object(continuity_check._llm_job, "resolve_bot_and_channel",
                          return_value=resolved):
            res = asyncio.run(continuity_check.run_for_text(
                ctx, text="something", label="seed: x"))
        self.assertTrue(res.ok)
        self.assertIn("skipped", res.message)
        ctx.post.assert_not_awaited()

    def test_no_prior_coverage_still_posts(self):
        # Empty passage set is not an error — Eddy calls it fresh ground.
        res, _ctx, bot, _fetch = _run(passages=[], reply="Fresh ground — nothing prior.")
        self.assertTrue(res.ok)
        bot.core.assert_awaited_once()


class ContinuityCheckPromptTests(unittest.TestCase):
    def test_prompt_pins_the_never_rewrite_rule(self):
        anthropic_client._prompt_cache.pop("eddy-continuity-check", None)
        prompt = anthropic_client.load_prompt("eddy-continuity-check")
        # The one rule: Eddy never rewrites Jamie's words.
        self.assertIn("never rewrite", prompt.lower())
        # References issues as WT### and has an honest "nothing prior" path.
        self.assertIn("WT###", prompt)
        self.assertIn("Fresh ground", prompt)


class ContinuityCheckWebTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "test.db")
        os.environ.setdefault("TAILSCALE_ALLOWED_LOGIN", LOGIN)
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()

    async def _client(self):
        app = web.Application(middlewares=[server._identity_mw])
        app[server.DEPS] = None
        routes.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_seed_continuity_route_runs_job_and_redirects(self):
        c = await self._client()
        seed = db.seed_add("Owning your words on your own domain", title="Own your words")
        with patch.object(continuity_check, "run_for_text",
                          AsyncMock(return_value=_base.JobResult(True, "ok"))) as job:
            r = await c.post(f"/seeds/{seed['id']}/continuity", headers=H,
                             allow_redirects=False)
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/seeds")
        job.assert_awaited_once()
        self.assertEqual(job.await_args.kwargs["text"], "Owning your words on your own domain")
        self.assertIn("Own your words", job.await_args.kwargs["label"])

    async def test_seed_continuity_unknown_seed_is_404(self):
        c = await self._client()
        r = await c.post("/seeds/9999/continuity", headers=H, allow_redirects=False)
        self.assertEqual(r.status, 404)

    async def test_seeds_page_has_continuity_button(self):
        c = await self._client()
        seed = db.seed_add("an idea worth checking")
        body = await (await c.get("/seeds", headers=H)).text()
        self.assertIn(f'action="/seeds/{seed["id"]}/continuity"', body)
        self.assertIn("Check continuity", body)

    async def test_production_continuity_route_runs_job_for_intro(self):
        c = await self._client()
        db.plan_issue_window(issue_number=360, pub_date="2026-06-27",
                             end_date="2026-06-26", start_date="2026-06-19", day_count=7)
        db.set_issue_phase(360, "build")
        with patch.object(routes.content_store, "read_issue",
                          return_value="This week's intro about metering."), \
             patch.object(continuity_check, "run_for_text",
                          AsyncMock(return_value=_base.JobResult(True, "ok"))) as job:
            r = await c.post("/productions/WT360/continuity", headers=H,
                             allow_redirects=False)
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/productions/WT360")
        job.assert_awaited_once()
        self.assertEqual(job.await_args.kwargs["text"], "This week's intro about metering.")
        self.assertEqual(job.await_args.kwargs["label"], "WT360 intro")
        self.assertEqual(job.await_args.kwargs["exclude_issue"], 360)

    async def test_production_continuity_foreign_origin_is_403(self):
        c = await self._client()
        db.plan_issue_window(issue_number=360, pub_date="2026-06-27",
                             end_date="2026-06-26", start_date="2026-06-19", day_count=7)
        r = await c.post("/productions/WT360/continuity",
                         headers={**H, "Origin": "https://evil.example"},
                         allow_redirects=False)
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
