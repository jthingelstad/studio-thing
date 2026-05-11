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

    def write_issue_file(self, issue_number, filename, content, *, content_type=None):
        self.files[(int(issue_number), filename)] = content
        return {"key": f"weekly-thing/{issue_number}/{filename}", "written": True,
                "size": len(content)}

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

from datetime import date  # noqa: E402
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


class MicroblogParseTests(unittest.TestCase):
    def test_html_to_markdownish(self):
        h = '<p>Hello <a href="https://x.example/y">there</a>.</p><p>Pic:</p><p><img src="https://cdn.uploads.micro.blog/z.jpg"></p>'
        md = microblog.html_to_markdownish(h)
        self.assertIn("[there](https://x.example/y)", md)
        self.assertIn("![](https://cdn.uploads.micro.blog/z.jpg)", md)
        self.assertNotIn("<p>", md)

    def test_posts_in_window_filters_by_date(self):
        feed = {
            "version": "https://jsonfeed.org/version/1.1",
            "items": [
                {"url": "https://x/1", "date_published": "2026-05-08T10:00:00-05:00", "content_html": "<p>before window</p>"},
                {"url": "https://x/2", "date_published": "2026-05-09T10:00:00-05:00", "content_html": "<p>in window early</p>"},
                {"url": "https://x/3", "date_published": "2026-05-15T23:00:00-05:00", "content_html": "<p>in window late</p>"},
                {"url": "https://x/4", "date_published": "2026-05-16T01:00:00-05:00", "content_html": "<p>after window</p>"},
            ],
        }
        with patch.object(microblog, "_fetch_feed", lambda: feed):
            out = microblog.posts_in_window("2026-05-08", "2026-05-15")
        self.assertEqual([p["url"] for p in out], ["https://x/2", "https://x/3"])
        self.assertEqual(out[0]["content_md"], "in window early")


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


if __name__ == "__main__":
    unittest.main()
