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
        self.ws.write_issue_file(458, "draft.md", "x")
        self.ws.write_issue_file(458, "intro.md", "x")
        self.ws.write_issue_file(458, "cta-1.md", "x")
        result = asyncio.run(issue_status.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        self.assertIn("WT458", result.message)
        self.assertIn("`intro.md`", result.message)
        # final.md / haiku.md / metadata.json / cover.jpg missing → ❌ markers.
        self.assertIn("❌ `final.md`", result.message)
        self.assertIn("cta-1.md", result.message)
        self.assertEqual(set(result.data["files"]), {"draft.md", "intro.md", "cta-1.md"})


if __name__ == "__main__":
    unittest.main()
