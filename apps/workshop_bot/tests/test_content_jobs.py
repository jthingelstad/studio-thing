"""Content-loop jobs runtime tests — Step 3.

Covers the job runtime in ``jobs/_base.py`` (draft-block helpers,
single-asset locking) and the first three jobs (``start-issue``,
``update-draft``, ``issue-status``) against a temp DB and an in-memory
fake S3 workspace.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, issue_status, start_issue, update_draft  # noqa: E402
from apps.workshop_bot.tools import db, s3  # noqa: E402


# ---------- in-memory fake S3 workspace ----------

class FakeWorkspace:
    """Replaces tools.s3's read/write/list with a dict keyed by
    (issue_number, filename)."""

    def __init__(self) -> None:
        self.files: dict[tuple[int, str], str] = {}

    def read_issue_file(self, issue_number, filename, *, max_bytes=None):
        key = (int(issue_number), filename)
        if key in self.files:
            return {"key": f"weekly-thing/{issue_number}/{filename}", "found": True,
                    "text": self.files[key], "size": len(self.files[key])}
        return {"key": f"weekly-thing/{issue_number}/{filename}", "found": False}

    def write_issue_file(self, issue_number, filename, content, *, content_type=None, cache_control=None):
        self.files[(int(issue_number), filename)] = content
        return {"key": f"weekly-thing/{issue_number}/{filename}", "written": True,
                "size": len(content), "url": f"https://files.thingelstad.com/weekly-thing/{issue_number}/{filename}"}

    def write_issue_html(self, issue_number, filename, html_text):
        # No CloudFront invalidation in tests.
        return self.write_issue_file(issue_number, filename, html_text)

    def list_issue(self, issue_number):
        n = int(issue_number)
        objs = [{"filename": fn, "key": f"weekly-thing/{n}/{fn}", "size": len(txt)}
                for (i, fn), txt in self.files.items() if i == n]
        return {"bucket": "files.thingelstad.com", "issue_number": n,
                "prefix": f"weekly-thing/{n}/", "objects": objs}


def _patch_s3(ws: FakeWorkspace):
    return [
        patch.object(s3, "read_issue_file", ws.read_issue_file),
        patch.object(s3, "write_issue_file", ws.write_issue_file),
        patch.object(s3, "write_issue_html", ws.write_issue_html),
        patch.object(s3, "list_issue", ws.list_issue),
    ]


class _DBTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()
        self.ws = FakeWorkspace()
        self._patches = _patch_s3(self.ws)
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        if self._orig_db is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_db
        self._tmpdir.cleanup()


# ---------- draft-block helpers ----------

class BlockHelperTests(unittest.TestCase):
    def test_replace_and_get_roundtrip(self):
        tpl = _base.starter_template()
        # All six blocks are present in the starter template.
        for name in ("intro", "notable", "brief", "journal", "currently", "haiku"):
            self.assertIsNotNone(_base.get_block(tpl, name), f"missing block {name}")
        out = _base.replace_block(tpl, "notable", "  - one\n  - two  ")
        self.assertEqual(_base.get_block(out, "notable"), "- one\n  - two")
        # Other blocks untouched.
        self.assertEqual(_base.get_block(out, "intro"), "")

    def test_empty_content_leaves_block_empty(self):
        tpl = _base.starter_template()
        out = _base.replace_block(tpl, "intro", "")
        self.assertEqual(_base.get_block(out, "intro"), "")
        self.assertIn("<!-- block:intro -->\n<!-- /block:intro -->", out)

    def test_missing_block_is_noop(self):
        text = "no markers here"
        self.assertEqual(_base.replace_block(text, "intro", "x"), text)
        self.assertIsNone(_base.get_block(text, "intro"))

    def test_replace_does_not_disturb_neighbours(self):
        tpl = _base.starter_template()
        out = _base.replace_block(tpl, "brief", "B content")
        out = _base.replace_block(out, "journal", "J content")
        self.assertEqual(_base.get_block(out, "brief"), "B content")
        self.assertEqual(_base.get_block(out, "journal"), "J content")
        self.assertIn("## Briefly", out)
        self.assertIn("## Journal", out)


# ---------- locking ----------

class JobLockTests(_DBTestCase):
    def test_acquire_then_second_acquire_blocked(self):
        first = db.acquire_job_lock(asset="458/draft.md", job="update-draft", pid=os.getpid())
        self.assertIsNone(first)
        # A *different* pid (simulate another running job) is blocked.
        second = db.acquire_job_lock(asset="458/draft.md", job="update-draft", pid=os.getpid() + 1)
        # Our own pid is alive, so the holder row comes back.
        # (db._pid_alive(os.getpid()) is True.)
        self.assertIsNotNone(second)
        self.assertEqual(second["job"], "update-draft")
        # Release frees it.
        self.assertTrue(db.release_job_lock("458/draft.md"))
        third = db.acquire_job_lock(asset="458/draft.md", job="update-draft", pid=os.getpid() + 1)
        self.assertIsNone(third)
        db.release_job_lock("458/draft.md")

    def test_stale_lock_from_dead_pid_is_stolen(self):
        # Inject a lock held by an almost-certainly-dead pid.
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO job_locks (asset, job, started_at, pid) VALUES (?, ?, datetime('now'), ?)",
                ("458/draft.md", "old-job", 999999),
            )
        out = db.acquire_job_lock(asset="458/draft.md", job="update-draft", pid=os.getpid())
        self.assertIsNone(out, "a lock held by a dead pid should be stolen")
        locks = db.list_job_locks()
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]["job"], "update-draft")
        db.release_job_lock("458/draft.md")

    def test_job_lock_context_manager_raises_when_held(self):
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO job_locks (asset, job, started_at, pid) VALUES (?, ?, datetime('now'), ?)",
                ("458/draft.md", "update-draft", os.getpid()),
            )
        with self.assertRaises(_base.JobLocked) as cm:
            with _base.job_lock(["458/draft.md"], "update-draft"):
                self.fail("should not enter the body when the lock is held")
        self.assertIn("458/draft.md", str(cm.exception))
        # The pre-existing lock is still there (we didn't acquire/release it).
        self.assertEqual(len(db.list_job_locks()), 1)
        db.release_job_lock("458/draft.md")

    def test_job_lock_releases_on_exception(self):
        with self.assertRaises(RuntimeError):
            with _base.job_lock(["458/draft.md"], "update-draft"):
                raise RuntimeError("boom")
        self.assertEqual(db.list_job_locks(), [])


# ---------- start-issue ----------

class StartIssueTests(_DBTestCase):
    def test_start_issue_records_window_seeds_draft_fires_update(self):
        ctx = _base.JobContext(trigger="manual")
        # 2026-05-16 is a Saturday.
        result = asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-16", day_count=7))
        self.assertTrue(result.ok, result.message)
        win = db.get_active_issue_window()
        self.assertIsNotNone(win)
        self.assertEqual(win["issue_number"], 458)
        self.assertEqual(win["pub_date"], "2026-05-16")
        self.assertEqual(win["end_date"], "2026-05-15")
        # draft.md was seeded and then filled by the chained update-draft.
        self.assertIn((458, "draft.md"), self.ws.files)
        draft = self.ws.files[(458, "draft.md")]
        for name in ("intro", "notable", "brief", "journal", "currently", "haiku"):
            self.assertIsNotNone(_base.get_block(draft, name))
        # Source-driven blocks carry placeholder text; asset-backed blocks empty.
        self.assertNotEqual(_base.get_block(draft, "notable"), "")
        self.assertNotEqual(_base.get_block(draft, "brief"), "")
        self.assertNotEqual(_base.get_block(draft, "journal"), "")
        self.assertEqual(_base.get_block(draft, "intro"), "")
        self.assertEqual(_base.get_block(draft, "currently"), "")
        self.assertEqual(_base.get_block(draft, "haiku"), "")

    def test_start_issue_rejects_non_saturday(self):
        ctx = _base.JobContext()
        result = asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-17", day_count=7))
        self.assertFalse(result.ok)
        self.assertIn("Sunday", result.message)

    def test_start_issue_rejects_bad_number(self):
        ctx = _base.JobContext()
        result = asyncio.run(start_issue.run(ctx, number=0, pub_date="2026-05-16", day_count=7))
        self.assertFalse(result.ok)

    def test_start_issue_replaces_active_window(self):
        ctx = _base.JobContext()
        asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-16", day_count=7))
        asyncio.run(start_issue.run(ctx, number=459, pub_date="2026-05-23", day_count=7))
        win = db.get_active_issue_window()
        self.assertEqual(win["issue_number"], 459)


# ---------- update-draft ----------

class UpdateDraftTests(_DBTestCase):
    def _set_window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def test_no_window_errors(self):
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message.lower())

    def test_update_draft_fills_blocks_and_reads_assets(self):
        self._set_window()
        self.ws.write_issue_file(458, "intro.md", "Hello from the intro file.")
        self.ws.write_issue_file(458, "haiku.md", "five seven five\nthe haiku file is read in\nby update draft")
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        draft = self.ws.files[(458, "draft.md")]
        self.assertEqual(_base.get_block(draft, "intro"), "Hello from the intro file.")
        self.assertIn("the haiku file is read in", _base.get_block(draft, "haiku"))
        self.assertEqual(_base.get_block(draft, "currently"), "")  # no currently.md
        self.assertNotEqual(_base.get_block(draft, "notable"), "")  # placeholder

    def test_update_draft_is_idempotent(self):
        self._set_window()
        asyncio.run(update_draft.run(_base.JobContext()))
        first = self.ws.files[(458, "draft.md")]
        asyncio.run(update_draft.run(_base.JobContext()))
        second = self.ws.files[(458, "draft.md")]
        self.assertEqual(first, second)

    def test_update_draft_blocked_when_lock_held(self):
        self._set_window()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO job_locks (asset, job, started_at, pid) VALUES (?, ?, datetime('now'), ?)",
                ("458/draft.md", "update-draft", os.getpid()),
            )
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message.lower())
        db.release_job_lock("458/draft.md")


# ---------- issue-status ----------

class IssueStatusTests(_DBTestCase):
    def test_no_window(self):
        result = asyncio.run(issue_status.run(_base.JobContext()))
        self.assertFalse(result.ok)
        self.assertIn("No active issue window", result.message)

    def test_reports_presence(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        self.ws.write_issue_file(458, "intro.md", "x")
        self.ws.write_issue_file(458, "cta-1.md", "x")
        result = asyncio.run(issue_status.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        self.assertIn("WT458", result.message)
        self.assertIn("`intro.md`", result.message)
        # final.md / haiku.md / metadata.json / cover.jpg missing → ❌ markers.
        self.assertIn("❌ `final.md`", result.message)
        self.assertIn("cta-1.md", result.message)
        st = result.data["section_status"]
        self.assertEqual(st["issue_number"], 458)
        self.assertEqual(st["cta_files"], ["cta-1.md"])
        self.assertFalse(st["ship_ready"])


# ---------- Step 4: real fills + section_status + context + Eddy review ----------

from datetime import date, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from apps.workshop_bot.tools import context, draft as draft_mod, microblog  # noqa: E402
from apps.workshop_bot.systems.pinboard import client as pinboard_client  # noqa: E402


_FAKE_CANDIDATES = {
    "notable": [
        {"url": "https://a.example/one", "title": "Thing One", "description": "Why it matters."},
        {"url": "https://b.example/two", "title": "Thing Two", "description": ""},
    ],
    "brief": [
        {"url": "https://c.example/three", "title": "Thing Three", "description": "A one-liner."},
    ],
}

_FAKE_MICROBLOG = [
    {"url": "https://www.thingelstad.com/2026/05/12/post-a.html", "title": "",
     "published": "2026-05-12T15:02:00-05:00", "content_md": "First post in the window."},
    {"url": "https://www.thingelstad.com/2026/05/13/post-b.html", "title": "",
     "published": "2026-05-13T09:00:00-05:00", "content_md": "Second post.\n\n![](https://cdn.uploads.micro.blog/x.jpg)"},
]


class DraftSectionStatusTests(unittest.TestCase):
    def test_counts_and_placeholder_detection(self):
        tpl = _base.starter_template()
        d = _base.replace_block(tpl, "notable",
                                "### [A](http://a)\n\nblurb\n\n### [B](http://b)\n\nblurb")
        d = _base.replace_block(d, "brief", "**[C](http://c)** — x\n\n**[D](http://d)** — y")
        d = _base.replace_block(d, "journal",
                                "[May 12, 2026 at 3:02 PM](https://www.thingelstad.com/x.html)\n\ntext")
        st = draft_mod.section_status(458, draft_text=d, list_objects=set())
        self.assertEqual(st["sections"]["notable"]["item_count"], 2)
        self.assertTrue(st["sections"]["notable"]["present"])
        self.assertEqual(st["sections"]["brief"]["item_count"], 2)
        self.assertEqual(st["sections"]["journal"]["item_count"], 1)
        # All three sections have content, so the "sections" gap is gone;
        # only the standalone assets are still missing.
        self.assertNotIn("sections (notable/brief/journal)", st["required_missing"])
        self.assertIn("haiku.md", st["required_missing"])
        self.assertIn("metadata.json", st["required_missing"])

    def test_placeholder_block_is_not_present(self):
        tpl = _base.replace_block(_base.starter_template(), "notable",
                                  "_Notable — couldn't pull from Pinboard (RequestException)._")
        st = draft_mod.section_status(458, draft_text=tpl, list_objects=set())
        self.assertTrue(st["sections"]["notable"]["placeholder"])
        self.assertFalse(st["sections"]["notable"]["present"])

    def test_ship_ready_when_everything_present(self):
        d = _base.replace_block(_base.starter_template(), "notable", "### [A](http://a)")
        d = _base.replace_block(d, "brief", "**[B](http://b)** — x")
        d = _base.replace_block(d, "journal", "[May 12, 2026 at 3:02 PM](https://x.example/y)\n\nt")
        files = {"final.md", "haiku.md", "metadata.json", "intro.md", "cover.jpg", "draft.md"}
        st = draft_mod.section_status(458, draft_text=d, list_objects=files)
        self.assertTrue(st["ship_ready"], st["required_missing"])


class UpdateDraftRealFillsTests(_DBTestCase):
    def _set_window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        return db.get_active_issue_window()

    def setUp(self):
        super().setUp()
        self._extra = [
            patch.object(pinboard_client, "issue_window_candidates", lambda s, e: _FAKE_CANDIDATES),
            patch.object(microblog, "posts_in_window", lambda s, e: list(_FAKE_MICROBLOG)),
        ]
        for p in self._extra:
            p.start()

    def tearDown(self):
        for p in self._extra:
            p.stop()
        super().tearDown()

    def test_fills_render_real_content(self):
        self._set_window()
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        d = self.ws.files[(458, "draft.md")]
        self.assertIn("### [Thing One](https://a.example/one)", d)
        self.assertIn("Why it matters.", d)
        self.assertIn("**[Thing Three](https://c.example/three)** — A one-liner.", d)
        self.assertIn("[May 12, 2026 at 3:02 PM](https://www.thingelstad.com/2026/05/12/post-a.html)", d)
        self.assertIn("First post in the window.", d)
        # A digest row was written.
        dig = db.latest_draft_digest(458)
        self.assertIsNotNone(dig)
        self.assertEqual(dig["notable_count"], 2)
        self.assertEqual(dig["brief_count"], 1)
        self.assertEqual(dig["journal_count"], 2)
        # An HTML preview was written too, and its URL surfaced in the result.
        html = self.ws.files[(458, "draft.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("Why it matters.", html)               # markdown rendered
        self.assertIn("DRAFT · WT458", html)                 # work-in-progress banner
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/draft.html")

    def test_idempotent_with_stable_sources(self):
        self._set_window()
        asyncio.run(update_draft.run(_base.JobContext()))
        first = self.ws.files[(458, "draft.md")]
        asyncio.run(update_draft.run(_base.JobContext()))
        second = self.ws.files[(458, "draft.md")]
        self.assertEqual(first, second)
        # Two runs → two digest rows.
        with db.connect() as conn:
            n = conn.execute("SELECT COUNT(*) c FROM draft_digests WHERE issue=458").fetchone()["c"]
        self.assertEqual(n, 2)

    def test_refuses_when_final_exists(self):
        self._set_window()
        self.ws.write_issue_file(458, "final.md", "locked")
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertFalse(result.ok)
        self.assertIn("locked", result.message.lower())

    def test_source_failure_degrades_to_placeholder(self):
        self._set_window()
        def _boom(s, e):
            raise RuntimeError("pinboard down")
        with patch.object(pinboard_client, "issue_window_candidates", _boom):
            result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        d = self.ws.files[(458, "draft.md")]
        self.assertIn("couldn't pull from Pinboard", d)
        # Journal still pulled fine.
        self.assertIn("First post in the window.", d)


class EddyReviewTests(_DBTestCase):
    def _window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        return db.get_active_issue_window()

    def _fake_team_with_eddy(self, reply="📋 WT458 — draft refreshed\n\nLooks good."):
        fake_channel = MagicMock()
        fake_channel.send = AsyncMock()
        fake_eddy = MagicMock()
        fake_eddy.user = object()
        fake_eddy.get_channel = MagicMock(return_value=fake_channel)
        fake_eddy.core = AsyncMock(return_value=(reply, {"iterations": 1}))
        team = MagicMock()
        team.bots = {"eddy": fake_eddy}
        deps = MagicMock()
        deps.team = team
        return deps, fake_eddy, fake_channel

    def test_review_silent_on_non_review_day(self):
        window = self._window()
        deps, fake_eddy, _ = self._fake_team_with_eddy()
        ctx = _base.JobContext(deps=deps)
        st = draft_mod.section_status(458, draft_text=_base.starter_template(), list_objects=set())
        # Monday — Eddy stays silent.
        out = asyncio.run(update_draft._maybe_eddy_review(ctx, window, st, None, date(2026, 5, 11)))
        self.assertIn("silent", out.lower())
        fake_eddy.core.assert_not_awaited()

    def test_review_posts_on_review_day(self):
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "12345"
        try:
            window = self._window()
            deps, fake_eddy, fake_channel = self._fake_team_with_eddy()
            ctx = _base.JobContext(deps=deps)
            st = draft_mod.section_status(458, draft_text=_base.starter_template(), list_objects=set())
            out = asyncio.run(update_draft._maybe_eddy_review(ctx, window, st, None, date(2026, 5, 12)))  # Tuesday
            self.assertIn("posted a review", out.lower())
            fake_eddy.core.assert_awaited()
            fake_channel.send.assert_awaited()
            # The dynamic context block was prepended to the user message.
            sent_user_msg = fake_eddy.core.call_args.kwargs["latest"]
            self.assertIn("## Today", sent_user_msg)
            self.assertIn("active_issue", sent_user_msg)
        finally:
            os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)

    def test_review_swallows_pass(self):
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "12345"
        try:
            window = self._window()
            deps, fake_eddy, fake_channel = self._fake_team_with_eddy(reply="PASS")
            ctx = _base.JobContext(deps=deps)
            st = draft_mod.section_status(458, draft_text=_base.starter_template(), list_objects=set())
            out = asyncio.run(update_draft._maybe_eddy_review(ctx, window, st, None, date(2026, 5, 12)))
            self.assertIn("pass", out.lower())
            fake_channel.send.assert_not_awaited()
        finally:
            os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)

    def test_review_model_scales(self):
        self.assertEqual(update_draft._review_model(1), "haiku")   # Tue
        self.assertEqual(update_draft._review_model(2), "haiku")   # Wed
        self.assertEqual(update_draft._review_model(3), "sonnet")  # Thu
        self.assertEqual(update_draft._review_model(4), "sonnet")  # Fri
        os.environ["WORKSHOP_EDDY_REVIEW_MODEL"] = "opus"
        try:
            self.assertEqual(update_draft._review_model(1), "opus")
        finally:
            os.environ.pop("WORKSHOP_EDDY_REVIEW_MODEL", None)


class EddyContextTests(_DBTestCase):
    def test_delta_against_prior_digest(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        # Prior run: 2 Notable, 0 intro.
        db.insert_draft_digest(issue=458, word_count=1200, notable_count=2, brief_count=1,
                               journal_count=0, intro_present=False, currently_present=False,
                               haiku_present=False, cover_present=False, source_hash="aaa")
        d = _base.replace_block(_base.starter_template(), "notable",
                                "### [A](http://a)\n\nx\n\n### [B](http://b)\n\ny\n\n### [C](http://c)\n\nz")
        d = _base.replace_block(d, "intro", "Now there's an intro.")
        self.ws.write_issue_file(458, "draft.md", d)
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 12))
        self.assertEqual(ctx["active_issue"], 458)
        self.assertEqual(ctx["sections"]["notable"]["item_count"], 3)
        delta = ctx["delta_since_last_run"]
        self.assertIsNotNone(delta)
        self.assertEqual(delta["notable"], 1)  # 3 - 2
        self.assertTrue(delta["intro_now_present"])

    def test_no_digest_means_no_delta(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 12))
        self.assertIsNone(ctx["delta_since_last_run"])

    def test_no_window(self):
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 12))
        self.assertIsNone(ctx["active_issue"])


class MicroblogTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("MICROBLOG_API_KEY", None)

    def test_html_to_markdownish(self):
        h = '<p>Hello <a href="https://x.example/y">there</a>.</p><p>Pic:</p><p><img src="https://cdn.uploads.micro.blog/z.jpg"></p>'
        md = microblog.html_to_markdownish(h)
        self.assertIn("[there](https://x.example/y)", md)
        self.assertIn("![](https://cdn.uploads.micro.blog/z.jpg)", md)
        self.assertNotIn("<p>", md)

    def test_content_to_markdown_variants(self):
        self.assertEqual(microblog._content_to_markdown("raw **markdown**"), "raw **markdown**")
        self.assertEqual(microblog._content_to_markdown(["raw md from list"]), "raw md from list")
        self.assertEqual(microblog._content_to_markdown({"markdown": "explicit md"}), "explicit md")
        self.assertIn("[x](http://y)", microblog._content_to_markdown({"html": '<a href="http://y">x</a>'}))
        self.assertEqual(microblog._content_to_markdown(None), "")

    def test_requires_api_key(self):
        os.environ.pop("MICROBLOG_API_KEY", None)
        with self.assertRaises(RuntimeError):
            microblog.posts_in_window("2026-05-08", "2026-05-15")

    def test_source_query_returns_native_markdown_in_window(self):
        os.environ["MICROBLOG_API_KEY"] = "tok"
        # Shape mirrors a real micro.blog q=source response: content is the
        # raw markdown string, with photo uploads embedded as <img> tags.
        mf2 = {
            "items": [
                {"type": "h-entry", "properties": {
                    "uid": [5863257], "name": [""],
                    "url": ["https://www.thingelstad.com/2026/05/12/a.html"],
                    "published": ["2026-05-12T15:02:00+00:00"],
                    "post-status": ["published"],
                    "content": ['Got a card. ([cert](https://psacard.com/cert/x))\n\n<img src="https://www.thingelstad.com/uploads/2026/428e3db12e.jpg" width="363" height="600" alt="">'],
                }},
                {"type": "h-entry", "properties": {
                    "url": ["https://www.thingelstad.com/2026/05/01/old.html"],
                    "published": ["2026-05-01T09:00:00+00:00"],
                    "post-status": ["published"],
                    "content": ["out of window"],
                }},
                {"type": "h-entry", "properties": {
                    "url": ["https://www.thingelstad.com/2026/05/13/draft.html"],
                    "published": ["2026-05-13T09:00:00+00:00"],
                    "post-status": ["draft"],
                    "content": ["a draft, should be skipped"],
                }},
            ]
        }
        fake_resp = MagicMock()
        fake_resp.json.return_value = mf2
        fake_resp.raise_for_status = MagicMock()
        with patch.object(microblog.requests, "get", return_value=fake_resp) as g:
            out = microblog.posts_in_window("2026-05-08", "2026-05-15")
        self.assertEqual([p["url"] for p in out], ["https://www.thingelstad.com/2026/05/12/a.html"])
        # Native markdown — including the embedded <img> tag (rehosted later).
        self.assertIn("Got a card.", out[0]["content_md"])
        self.assertIn('<img src="https://www.thingelstad.com/uploads/2026/428e3db12e.jpg"', out[0]["content_md"])
        # Hit the Micropub endpoint with the source query + bearer auth.
        kwargs = g.call_args.kwargs
        self.assertEqual(kwargs["params"], {"q": "source"})
        self.assertTrue(kwargs["headers"]["Authorization"].startswith("Bearer "))


class DraftSectionStatusToolTests(_DBTestCase):
    def test_tool_returns_status_for_active_issue(self):
        from apps.workshop_bot.tools import agent_tools, issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _base.replace_block(_base.starter_template(), "notable", "### [A](http://a)"))
        registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(registry)
        out = registry.dispatch("draft__section_status", deps=None, args={}, persona="eddy")
        self.assertEqual(out["issue_number"], 458)
        self.assertEqual(out["sections"]["notable"]["item_count"], 1)

    def test_tool_errors_without_window(self):
        from apps.workshop_bot.tools import agent_tools
        registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(registry)
        out = registry.dispatch("draft__section_status", deps=None, args={}, persona="eddy")
        self.assertIn("error", out)


# ---------- Step 5: Linky pinboard-scan + new Pinboard verbs ----------

from apps.workshop_bot.jobs import pinboard_scan  # noqa: E402


class _FakeLinkyTeam:
    def __init__(self, reply="- [thing](http://x) — looks good — [pin](http://pin)"):
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.linky = MagicMock()
        self.linky.user = object()
        self.linky.get_channel = MagicMock(return_value=self.channel)
        self.linky.core = AsyncMock(return_value=(reply, {"iterations": 1}))
        self.bots = {"linky": self.linky}


def _deps_with_linky_team(team):
    deps = MagicMock()
    deps.team = team
    return deps


class PinboardScanJobTests(_DBTestCase):
    def _window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        return db.get_active_issue_window()

    def test_pass_no_window(self):
        result = asyncio.run(pinboard_scan.run(_base.JobContext()))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])
        self.assertIn("no active issue window", result.message.lower())

    def test_pass_outside_window(self):
        # Window 2026-05-08..2026-05-15; pick a 'today' well outside it by
        # patching the job module's datetime.
        self._window(pub="2026-05-16")  # window: 2026-05-08 .. 2026-05-15

        class _FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 6, 1, 12, 0, 0)

        with patch.object(pinboard_scan, "datetime", _FakeDT):
            result = asyncio.run(pinboard_scan.run(_base.JobContext()))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])
        self.assertIn("outside the issue window", result.message.lower())

    def test_skips_when_no_team(self):
        self._window()

        class _FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 5, 12, 9, 0, 0)  # in window

        with patch.object(pinboard_scan, "datetime", _FakeDT):
            result = asyncio.run(pinboard_scan.run(_base.JobContext()))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])

    def test_runs_linky_and_posts_when_active(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        try:
            self._window()
            team = _FakeLinkyTeam()
            ctx = _base.JobContext(deps=_deps_with_linky_team(team))

            class _FakeDT(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 5, 12, 9, 0, 0)  # Tuesday, in window

            # build_linky_context calls pinboard posts_all; stub it.
            from apps.workshop_bot.systems.pinboard import client as pbc
            with patch.object(pinboard_scan, "datetime", _FakeDT), \
                 patch.object(pbc, "posts_all", lambda **kw: []):
                result = asyncio.run(pinboard_scan.run(ctx))
            self.assertTrue(result.ok, result.message)
            self.assertTrue(result.data["posted"])
            team.linky.core.assert_awaited()
            team.channel.send.assert_awaited()
            sent_user_msg = team.linky.core.call_args.kwargs["latest"]
            self.assertIn("## Today", sent_user_msg)
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)

    def test_linky_pass_not_posted(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        try:
            self._window()
            team = _FakeLinkyTeam(reply="PASS")
            ctx = _base.JobContext(deps=_deps_with_linky_team(team))

            class _FakeDT(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 5, 12, 9, 0, 0)

            from apps.workshop_bot.systems.pinboard import client as pbc
            with patch.object(pinboard_scan, "datetime", _FakeDT), \
                 patch.object(pbc, "posts_all", lambda **kw: []):
                result = asyncio.run(pinboard_scan.run(ctx))
            self.assertTrue(result.ok)
            self.assertFalse(result.data["posted"])
            team.channel.send.assert_not_awaited()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)


class PinboardClientNewVerbsTests(unittest.TestCase):
    def test_capture_blurb_merges_tags_and_clears_toread(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        captured = {}

        def fake_get(url):
            return {"posts": [{
                "href": url, "description": "Some Title", "extended": "old body",
                "tags": "ai toread", "shared": "yes",
            }]}

        def fake_add(*, url, title, description, tags, toread, shared, replace):
            captured.update(dict(url=url, title=title, description=description, tags=tags,
                                 toread=toread, shared=shared, replace=replace))
            return {"result_code": "done", "pinboard_url": f"https://pinboard.in/b/{url}"}

        with patch.object(pbc, "posts_get", fake_get), patch.object(pbc, "posts_add", fake_add):
            out = pbc.capture_blurb("https://example.com/x", "Jamie's verbatim one-liner.")
        self.assertEqual(out["result_code"], "done")
        self.assertEqual(captured["description"], "Jamie's verbatim one-liner.")
        self.assertFalse(captured["toread"])
        self.assertTrue(captured["replace"])
        self.assertIn("_brief", captured["tags"].split())
        self.assertNotIn("toread", captured["tags"].split())
        self.assertIn("ai", captured["tags"].split())  # preserved
        self.assertEqual(captured["title"], "Some Title")  # preserved

    def test_capture_blurb_errors_when_not_bookmarked(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        with patch.object(pbc, "posts_get", lambda url: {"posts": []}):
            out = pbc.capture_blurb("https://example.com/missing", "blurb")
        self.assertIn("error", out)

    def test_archive_search_substring_match(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        feed = [
            {"href": "https://a/1", "description": "Elixir Phoenix", "extended": "", "tags": "elixir web", "time": "2026-05-01T00:00:00Z"},
            {"href": "https://a/2", "description": "Rust async", "extended": "tokio runtime", "tags": "rust", "time": "2026-05-02T00:00:00Z"},
            {"href": "https://a/3", "description": "Nothing", "extended": "", "tags": "misc", "time": "2026-05-03T00:00:00Z"},
        ]
        with patch.object(pbc, "posts_all", lambda **kw: feed):
            hits = pbc.archive_search("tokio", k=8)
        self.assertEqual([h["url"] for h in hits], ["https://a/2"])

    def test_issue_window_candidates_partitions_on_brief_tag(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        feed = [
            {"href": "https://n/1", "description": "Notable one", "extended": "blurb", "tags": "ai", "time": "2026-05-10T12:00:00Z"},
            {"href": "https://b/1", "description": "Brief one", "extended": "tiny", "tags": "ai _brief", "time": "2026-05-11T12:00:00Z"},
            {"href": "https://x/1", "description": "Out of window", "extended": "", "tags": "ai", "time": "2026-05-08T12:00:00Z"},
        ]
        with patch.object(pbc, "posts_all", lambda **kw: feed):
            out = pbc.issue_window_candidates("2026-05-08", "2026-05-15")
        self.assertEqual([n["url"] for n in out["notable"]], ["https://n/1"])
        self.assertEqual([b["url"] for b in out["brief"]], ["https://b/1"])


class PinboardServerNewToolsTests(unittest.TestCase):
    def _server(self):
        from apps.workshop_bot.systems.pinboard.server import PinboardServer
        return {t.name: t for t in PinboardServer().list_tools()}

    def test_new_verbs_registered(self):
        tools = self._server()
        for name in ("issue_candidates", "capture_blurb", "popular_unseen", "mark_seen",
                     "estimate_read_length", "queue_depth_vs_deadline", "archive_recall"):
            self.assertIn(name, tools, f"missing pinboard verb {name}")
        # Thin mirrors still present.
        for name in ("recent", "unread", "popular", "save", "lookup_url"):
            self.assertIn(name, tools)

    def test_issue_candidates_section_enum(self):
        tools = self._server()
        schema = tools["issue_candidates"].input_schema
        self.assertEqual(schema["properties"]["section"]["enum"], ["notable", "brief"])

    def test_estimate_read_length_buckets(self):
        from apps.workshop_bot.systems.pinboard import server as srv
        with patch.object(srv.web, "fetch_text", lambda url, max_chars=0: {"text": "word " * 100}):
            out = srv._estimate_read_length("http://x")
        self.assertEqual(out["bucket"], "short")
        with patch.object(srv.web, "fetch_text", lambda url, max_chars=0: {"text": "word " * 5000}):
            out = srv._estimate_read_length("http://x")
        self.assertEqual(out["bucket"], "long")
        with patch.object(srv.web, "fetch_text", lambda url, max_chars=0: {"error": "paywall"}):
            out = srv._estimate_read_length("http://x")
        self.assertEqual(out["bucket"], "unknown")


class LinkyContextTests(_DBTestCase):
    def test_build_linky_context(self):
        from apps.workshop_bot.tools import issue as issue_mod, context
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        from apps.workshop_bot.systems.pinboard import client as pbc
        feed = [
            {"href": "https://a/1", "tags": "ai", "toread": "yes", "time": "2026-05-10T00:00:00Z"},
            {"href": "https://a/2", "tags": "ai _brief", "toread": "no", "time": "2026-05-11T00:00:00Z"},
            {"href": "https://a/3", "tags": "rust", "toread": "no", "time": "2026-05-03T00:00:00Z"},
        ]
        with patch.object(pbc, "posts_all", lambda **kw: feed):
            ctx = context.build_linky_context(ref_date=date(2026, 5, 12))
        self.assertEqual(ctx["active_issue"], 458)
        self.assertEqual(ctx["toread_count"], 1)
        self.assertEqual(ctx["brief_captured_this_week"], 1)
        self.assertEqual(ctx["days_into_window"], (date(2026, 5, 12) - date(2026, 5, 8)).days)


# ---------- Step 6: create-final + compose chain + build-publish ----------

from apps.workshop_bot.jobs import (  # noqa: E402
    build_publish, compose_cta, compose_haiku, compose_meta, create_final,
)
from apps.workshop_bot.tools import interaction  # noqa: E402


def _filled_final(*, notable="### [A](http://a)\n\nx", brief="**[B](http://b)** — y",
                  journal="[May 12, 2026 at 3:02 PM](https://x.example/p)\n\nt") -> str:
    d = _base.starter_template()
    d = _base.replace_block(d, "notable", notable)
    d = _base.replace_block(d, "brief", brief)
    d = _base.replace_block(d, "journal", journal)
    return d


class _FakeBotChannel:
    """A persona bot + a channel, enough for the compose/build jobs."""

    def __init__(self, persona="eddy", reply='{"options": []}'):
        self.persona = persona
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.bot = MagicMock()
        self.bot.user = object()
        self.bot.get_channel = MagicMock(return_value=self.channel)
        self.bot.core = AsyncMock(return_value=(reply, {"iterations": 1}))

    def deps(self):
        team = MagicMock()
        team.bots = {self.persona: self.bot}
        d = MagicMock()
        d.team = team
        return d


def _ctx_for(persona, reply, channel_env_value="123"):
    fc = _FakeBotChannel(persona=persona, reply=reply)
    os.environ[channel_env_value if channel_env_value.startswith("DISCORD") else "DISCORD_CHANNEL_EDITORIAL"] = "123"
    return fc


class InteractionPrimitiveTests(unittest.TestCase):
    def _bot_channel(self):
        channel = MagicMock()
        msg = MagicMock()
        msg.id = 4242
        msg.add_reaction = AsyncMock()
        channel.send = AsyncMock(return_value=msg)
        bot = MagicMock()
        return bot, channel, msg

    def test_await_choice_returns_index(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            bot, channel, msg = self._bot_channel()
            payload = MagicMock(); payload.message_id = 4242; payload.user_id = 777
            payload.emoji = MagicMock(); payload.emoji.name = interaction.DIGIT_EMOJI[1]  # picks "2"
            bot.wait_for = AsyncMock(return_value=payload)
            out = asyncio.run(interaction.await_choice(bot, channel, ["a", "b", "c"], prompt="pick"))
            self.assertEqual(out, 1)
            self.assertTrue(msg.add_reaction.await_count >= 3)
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_choice_refresh(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            bot, channel, msg = self._bot_channel()
            payload = MagicMock(); payload.message_id = 4242; payload.user_id = 777
            payload.emoji = MagicMock(); payload.emoji.name = interaction.REFRESH_EMOJI
            bot.wait_for = AsyncMock(return_value=payload)
            out = asyncio.run(interaction.await_choice(bot, channel, ["a", "b"], prompt="pick"))
            self.assertEqual(out, "refresh")
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_choice_timeout(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            bot, channel, msg = self._bot_channel()
            bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())
            out = asyncio.run(interaction.await_choice(bot, channel, ["a"], prompt="pick"))
            self.assertIsNone(out)
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_choice_no_owner(self):
        # No DISCORD_OWNER_USER_ID → can't wait → None immediately.
        os.environ.pop("DISCORD_OWNER_USER_ID", None)
        bot, channel, msg = self._bot_channel()
        bot.wait_for = AsyncMock()
        out = asyncio.run(interaction.await_choice(bot, channel, ["a"], prompt="pick"))
        self.assertIsNone(out)
        bot.wait_for.assert_not_awaited()

    def test_await_approval(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            bot, channel, msg = self._bot_channel()
            payload = MagicMock(); payload.message_id = 4242; payload.user_id = 777
            payload.emoji = MagicMock(); payload.emoji.name = interaction.YES_EMOJI
            bot.wait_for = AsyncMock(return_value=payload)
            self.assertIs(asyncio.run(interaction.await_approval(bot, channel, prompt="ok?")), True)
            payload.emoji.name = interaction.NO_EMOJI
            self.assertIs(asyncio.run(interaction.await_approval(bot, channel, prompt="ok?")), False)
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)


class BuildPublishTests(_DBTestCase):
    def _window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def _ctx(self, persona="eddy"):
        fc = _FakeBotChannel(persona=persona)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def test_refuses_with_missing_list(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        # Missing haiku.md, metadata.json, intro.md, cover.jpg.
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertFalse(result.ok)
        for r in ("haiku.md", "metadata.json", "intro.md", "cover.jpg"):
            self.assertIn(r, result.message)
        fc.channel.send.assert_awaited()  # posted the missing list

    def test_assembles_publish_md(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Welcome to the issue.")
        self.ws.write_issue_file(458, "haiku.md", "line one\nline two\nline three")
        self.ws.write_issue_file(458, "currently.md", "Reading: a book.")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")  # presence only
        self.ws.write_issue_file(458, "cta-1.md", "---\nplacement: after_brief\n---\n\nSupport the EFF.")
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertIn("Welcome to the issue.", pub)
        self.assertIn("line two", pub)
        self.assertIn("Reading: a book.", pub)
        self.assertIn("Support the EFF.", pub)
        self.assertNotIn("<!-- block:", pub)            # markers stripped
        self.assertIn("## Notable", pub)
        # CTA placed after the Briefly section, before Journal.
        self.assertLess(pub.index("Support the EFF."), pub.index("## Journal"))
        self.assertGreater(pub.index("Support the EFF."), pub.index("## Briefly"))
        # publish.html written too (no draft banner — it's the ship body).
        html = self.ws.files[(458, "publish.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Weekly Thing 458</title>", html)
        self.assertNotIn('class="banner"', html)
        self.assertIn("Support the EFF.", html)
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/publish.html")

    def test_no_currently_means_no_currently_heading(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        # No currently.md.
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertNotIn("## Currently", pub)   # empty optional section dropped
        self.assertIn("## Notable", pub)
        self.assertIn("## Haiku", pub)
        self.assertTrue(pub.startswith("Intro."))


class ComposeHaikuTests(_DBTestCase):
    def _window(self, n=458):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _ctx(self, reply='{"options": ["one\\ntwo\\nthree", "a\\nb\\nc"]}'):
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_writes_haiku_on_pick(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=1)):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.ws.files[(458, "haiku.md")].strip(), "a\nb\nc")

    def test_refresh_then_pick(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=["refresh", 0])):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.ws.files[(458, "haiku.md")].strip(), "one\ntwo\nthree")
        self.assertEqual(fc.bot.core.await_count, 2)  # initial + refresh

    def test_no_pick_no_write(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertFalse(result.ok)
        self.assertNotIn((458, "haiku.md"), self.ws.files)


class ComposeMetaTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def test_writes_metadata_json(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = '{"options": [{"subject": "Weekly Thing 458 / One, Two, Three", "description": "A week."}]}'
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)), \
             patch.object(compose_meta, "_recent_subjects", lambda limit=10: []):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j
        meta = _j.loads(self.ws.files[(458, "metadata.json")])
        self.assertEqual(meta["number"], 458)
        self.assertEqual(meta["subject"], "Weekly Thing 458 / One, Two, Three")
        self.assertEqual(meta["slug"], "458")
        self.assertTrue(meta["image"].endswith("/458/cover.jpg"))
        self.assertTrue(meta["publish_date"].startswith("2026-05-16"))


class ComposeCtaTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_SUPPORTERS", None)
        super().tearDown()

    def _window(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def test_zero_ctas(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        fc = _FakeBotChannel(persona="patty", reply='{"ctas": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["ctas_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_one_cta_written_with_frontmatter(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = '{"ctas": [{"placement": "after_brief", "framings": ["Thingy here. Your support funds the EFF."]}]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["ctas_written"], 1)
        cta = self.ws.files[(458, "cta-1.md")]
        self.assertIn("placement: after_brief", cta)
        self.assertIn("Thingy here.", cta)


class CreateFinalTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _setup(self, reply):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_refuses_if_final_exists(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        self.ws.write_issue_file(458, "final.md", "already there")
        ctx, fc = self._setup("ignored")
        self.ws.files[(458, "final.md")] = "already there"  # _setup overwrote draft only
        result = asyncio.run(create_final.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already has", result.message)

    def test_accept_uses_eddy_body(self):
        proposed = _filled_final(notable="### [Z reordered](http://z)\n\nlead")
        reply = f"Reordered Notable to lead with Z.\n\n```markdown\n{proposed}\n```"
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertIn("Z reordered", self.ws.files[(458, "final.md")])
        # No auto-chain: the result points Jamie at the compose jobs.
        self.assertIn("compose-haiku", result.message)
        # ...and Eddy never touched any other job.
        self.assertFalse(hasattr(create_final, "compose_haiku"))
        # final.html preview written, banner says FINAL.
        html = self.ws.files[(458, "final.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("FINAL (post-Eddy ordering) · WT458", html)
        self.assertIn("Z reordered", html)
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/final.html")

    def test_reject_uses_draft_body(self):
        proposed = _filled_final(notable="### [Z reordered](http://z)\n\nlead")
        reply = f"here's a take\n\n```markdown\n{proposed}\n```"
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=False)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Draft body used, not the proposed reorder.
        self.assertIn("### [A](http://a)", self.ws.files[(458, "final.md")])
        self.assertNotIn("Z reordered", self.ws.files[(458, "final.md")])

    def test_timeout_writes_draft_and_returns(self):
        ctx, fc = self._setup("here's a take\n\n```markdown\n" + _filled_final(notable="### [Z](http://z)") + "\n```")
        with patch.object(interaction, "await_approval", AsyncMock(return_value=None)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # On timeout the draft body is written as-is (don't block forever).
        self.assertIn("### [A](http://a)", self.ws.files[(458, "final.md")])


class GoalsAndPattyContextTests(_DBTestCase):
    def test_goal_seeded(self):
        g = db.get_active_goal()
        self.assertIsNotNone(g)
        self.assertEqual(g["target_kind"], "members")
        self.assertEqual(g["target_value"], 50)

    def test_goal_lifecycle(self):
        g = db.get_active_goal()
        self.assertTrue(db.mark_goal_achieved(g["id"], achieved_at="2026-08-01"))
        self.assertIsNone(db.get_active_goal())
        nid = db.insert_goal(target_kind="dollars", target_value=10000, started_at="2026-08-02")
        active = db.get_active_goal()
        self.assertEqual(active["id"], nid)
        recent = db.recent_achieved_goals(3)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["target_kind"], "members")

    def test_patty_context_anniversary_math(self):
        from apps.workshop_bot.tools import context
        # 2026-05-11 (Mon) -> next May 13 is 2026-05-13, 2 days out, 0 issues before.
        ctx = context.build_patty_context(ref_date=date(2026, 5, 11))
        self.assertEqual(ctx["days_to_anniversary"], 2)
        self.assertEqual(ctx["next_anniversary"], "2026-05-13")
        self.assertEqual(ctx["expected_issues_before_anniversary"], 0)
        # From 2026-05-20: next anniversary is 2027-05-13. Saturdays in
        # range minus July/August/Dec15-Jan15 Saturdays.
        ctx2 = context.build_patty_context(ref_date=date(2026, 5, 20))
        self.assertEqual(ctx2["next_anniversary"], "2027-05-13")
        self.assertGreater(ctx2["expected_issues_before_anniversary"], 30)  # ~52 weeks - ~13 no-publish

    def test_no_publish_saturday(self):
        from apps.workshop_bot.tools import context
        self.assertTrue(context._is_no_publish_saturday(date(2026, 7, 4)))
        self.assertTrue(context._is_no_publish_saturday(date(2026, 8, 15)))
        self.assertTrue(context._is_no_publish_saturday(date(2026, 12, 20)))
        self.assertTrue(context._is_no_publish_saturday(date(2027, 1, 10)))
        self.assertFalse(context._is_no_publish_saturday(date(2026, 5, 16)))
        self.assertFalse(context._is_no_publish_saturday(date(2026, 12, 13)))


class PublishToButtondownTests(unittest.TestCase):
    def setUp(self):
        # Importing pipeline/content/content.py runs load_dotenv() at module
        # load, which would pour the developer's .env into os.environ for the
        # rest of the test run (PINBOARD_API_TOKEN etc.). Snapshot + restore.
        self._env_snapshot = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_snapshot)

    def _content_module(self):
        import sys as _sys
        from pathlib import Path as _P
        cd = str(_P(__file__).resolve().parents[3] / "pipeline" / "content")
        if cd not in _sys.path:
            _sys.path.insert(0, cd)
        import content  # noqa: F401
        return content

    def test_refuses_without_publish_md(self):
        content = self._content_module()
        import types
        with patch.object(content, "_workspace_get_text", lambda n, f: None):
            with self.assertRaises(SystemExit):
                content.publish_to_buttondown(types.SimpleNamespace(issue="458", dry_run=True))

    def test_dry_run_with_assets(self):
        content = self._content_module()
        import types

        def fake_get(n, f):
            return "## Notable\n\nbody" if f == "publish.md" else '{"subject":"Weekly Thing 458 / A, B, C","description":"d","slug":"458"}'

        with patch.object(content, "_workspace_get_text", fake_get):
            # dry-run: no HTTP, no exception.
            content.publish_to_buttondown(types.SimpleNamespace(issue="458", dry_run=True))


if __name__ == "__main__":
    unittest.main()
