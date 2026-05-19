"""Step 7 — RSS detection + Marky's promotion-prep job."""

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
from apps.workshop_bot.scheduler import handlers  # noqa: E402
from apps.workshop_bot.tools import db, rss, s3 # noqa: E402
from apps.workshop_bot.tools.content import context


_ATOM_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>The Weekly Thing</title>
  <entry>
    <title>Weekly Thing 458 / One, Two, Three</title>
    <id>https://weekly.thingelstad.com/archive/458/</id>
    <link href="https://weekly.thingelstad.com/archive/458/"/>
    <updated>2026-05-16T12:00:00Z</updated>
  </entry>
  <entry>
    <title>Weekly Thing 457 / A, B, C</title>
    <id>https://weekly.thingelstad.com/archive/457/</id>
    <link href="https://weekly.thingelstad.com/archive/457/"/>
    <updated>2026-05-09T12:00:00Z</updated>
  </entry>
  <entry>
    <title>About - not an issue</title>
    <id>https://weekly.thingelstad.com/about/</id>
    <link href="https://weekly.thingelstad.com/about/"/>
    <updated>2026-01-01T00:00:00Z</updated>
  </entry>
</feed>
"""


def _fake_feed_response(content=_ATOM_FEED):
    r = MagicMock()
    r.content = content
    r.raise_for_status = MagicMock()
    return r


class RssParseTests(unittest.TestCase):
    def test_latest_published_issue(self):
        with patch.object(rss.requests, "get", return_value=_fake_feed_response()):
            out = rss.latest_published_issue()
        self.assertIsNotNone(out)
        self.assertEqual(out["number"], 458)
        self.assertEqual(out["ship_date"], "2026-05-16")
        self.assertIn("/archive/458/", out["url"])

    def test_empty_feed(self):
        empty = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>x</title></feed>'
        with patch.object(rss.requests, "get", return_value=_fake_feed_response(empty)):
            self.assertIsNone(rss.latest_published_issue())


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
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_PROMOTION", None)
        super().tearDown()

    def test_no_buttondown_md_errors(self):
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        with patch.object(rss, "latest_published_issue", lambda: {"number": 458, "ship_date": "2026-05-16"}):
            result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps)))
        self.assertFalse(result.ok)
        self.assertIn("no `buttondown.md`", result.message)
        marky.core.assert_not_awaited()

    def test_drafts_and_posts(self):
        self.ws.files[(458, "buttondown.md")] = "## Notable\n\n### [Thing](http://x)\n\nblurb\n"
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        with patch.object(rss, "latest_published_issue", lambda: {"number": 458, "ship_date": "2026-05-16"}):
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
        self.ws.files[(458, "buttondown.md")] = "## Notable\n\nx"
        with patch.object(rss, "latest_published_issue", lambda: {"number": 458}):
            result = asyncio.run(promotion_prep.run(_base.JobContext(), issue_number=458))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])

    def test_body_is_truncated_to_promotion_body_cap(self):
        # An oversized buttondown.md must be capped at PROMOTION_BODY_CAP before
        # being fed to Marky, otherwise a runaway issue body could blow up
        # the user-message size.
        from apps.workshop_bot.jobs import _llm_job
        cap = _llm_job.PROMOTION_BODY_CAP
        huge = "## Notable\n\n" + ("x" * (cap + 5_000))
        self.ws.files[(458, "buttondown.md")] = huge
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        with patch.object(rss, "latest_published_issue", lambda: {"number": 458, "ship_date": "2026-05-16"}):
            result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertTrue(result.ok, result.message)
        sent = marky.core.call_args.kwargs["latest"]
        # The fenced markdown block carries at most `cap` body chars.
        body = sent.split("```markdown\n", 1)[1].rsplit("\n```", 1)[0]
        self.assertEqual(len(body), cap)
        # And the cap is the constant, not a magic number elsewhere.
        self.assertEqual(_llm_job.PROMOTION_BODY_CAP, _llm_job.ISSUE_BODY_CAP + 8_000)

    def test_concurrent_run_is_blocked_by_job_lock(self):
        # Pre-acquire the whole-job lock so the next run bails before doing
        # any work — proves a re-fire (manual + RSS-triggered, say) doesn't
        # produce duplicate #promotion posts.
        self.ws.files[(458, "buttondown.md")] = "## Notable\n\nx"
        deps, marky, channel = _marky_deps()
        os.environ["DISCORD_CHANNEL_PROMOTION"] = "1"
        with _base.job_lock([f"job:{promotion_prep.NAME}"], promotion_prep.NAME):
            with patch.object(rss, "latest_published_issue", lambda: {"number": 458, "ship_date": "2026-05-16"}):
                result = asyncio.run(promotion_prep.run(_base.JobContext(deps=deps), issue_number=458))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        marky.core.assert_not_awaited()


class RssCheckHandlerTests(_DBCase):
    def test_fires_promotion_prep_once_then_dedupes(self):
        deps = MagicMock(); deps.team = None  # promotion-prep will skip-post
        ctx = MagicMock(); ctx.deps = deps
        with patch.object(rss, "latest_published_issue", lambda: {"number": 458, "ship_date": "2026-05-16"}), \
             patch("apps.workshop_bot.jobs.promotion_prep.run", new=AsyncMock(return_value=_base.JobResult(True, "drafted"))) as pp:
            out1 = asyncio.run(handlers.rss_check(ctx))
            out2 = asyncio.run(handlers.rss_check(ctx))
        self.assertEqual(out1, "fired")
        self.assertEqual(out2, "noop")  # already detected #458
        self.assertEqual(pp.await_count, 1)
        # The note was recorded.
        notes = db.query_agent_notes(agent_name="marky", kind="context", query="marky:last-detected-issue", limit=1)
        self.assertTrue(notes)
        self.assertEqual(notes[0]["content"], "458")

    def test_noop_when_feed_unparseable(self):
        ctx = MagicMock(); ctx.deps = MagicMock()
        with patch.object(rss, "latest_published_issue", side_effect=RuntimeError("boom")):
            out = asyncio.run(handlers.rss_check(ctx))
        self.assertEqual(out, "noop")

    def test_higher_number_fires_again(self):
        ctx = MagicMock(); ctx.deps = MagicMock(); ctx.deps.team = None
        seq = iter([{"number": 458}, {"number": 459}])
        with patch.object(rss, "latest_published_issue", lambda: next(seq)), \
             patch("apps.workshop_bot.jobs.promotion_prep.run", new=AsyncMock(return_value=_base.JobResult(True, "ok"))) as pp:
            asyncio.run(handlers.rss_check(ctx))
            asyncio.run(handlers.rss_check(ctx))
        self.assertEqual(pp.await_count, 2)


class MarkyContextTests(_DBCase):
    def test_build_marky_context(self):
        from datetime import date
        with patch.object(rss, "latest_published_issue", lambda: {"number": 458, "ship_date": "2026-05-16"}):
            ctx = context.build_marky_context(ref_date=date(2026, 5, 20))
        self.assertEqual(ctx["latest_published_issue"], 458)
        self.assertEqual(ctx["ship_date"], "2026-05-16")
        self.assertEqual(ctx["days_since_ship"], 4)
        self.assertEqual(ctx["active_campaigns"], [])  # campaigns table lands in Step 8

    def test_build_marky_context_explicit(self):
        from datetime import date
        # Explicit args → no RSS fetch.
        with patch.object(rss, "latest_published_issue", side_effect=AssertionError("should not fetch")):
            ctx = context.build_marky_context(ref_date=date(2026, 5, 20), latest_issue=460, ship_date="2026-05-23")
        self.assertEqual(ctx["latest_published_issue"], 460)


class SchedulerWiringTests(unittest.TestCase):
    def test_rss_check_job_registered(self):
        from apps.workshop_bot.scheduler import jobs as J
        ids = {j.id for j in J.JOBS}
        self.assertIn("marky-rss-check", ids)
        spec = next(j for j in J.JOBS if j.id == "marky-rss-check")
        self.assertIs(spec.func, handlers.rss_check)

    def test_promotion_prep_command_wired(self):
        from apps.workshop_bot.personas import commands
        # /marky prep is a top-level verb on Marky's tree.
        tree = commands.register_marky_commands(MagicMock())
        marky = next(g for g in tree.groups if getattr(g, "name", None) == "marky")
        self.assertIn("prep", {getattr(c, "_cmd_name", None) for c in marky.commands})


if __name__ == "__main__":
    unittest.main()
