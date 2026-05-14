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
    (issue_number, filename), plus the standalone workshop.json pointer."""

    def __init__(self) -> None:
        self.files: dict[tuple[int, str], str] = {}
        self.workshop_pointer: dict | None = None

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

    def write_workshop_pointer(self, data):
        self.workshop_pointer = data
        return {"key": "weekly-thing/workshop.json", "bucket": "files.thingelstad.com",
                "url": "https://files.thingelstad.com/weekly-thing/workshop.json",
                "size": len(str(data)), "written": True}

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
        patch.object(s3, "write_workshop_pointer", ws.write_workshop_pointer),
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

    def test_starter_template_section_order(self):
        # Layout: intro → ## Currently → cover image → Notable → Journal →
        # Briefly → the "A haiku to leave you with…" close.
        tpl = _base.starter_template()
        markers = (
            "<!-- block:intro -->", "## Currently", "<!-- block:cover -->",
            "## Notable", "## Journal", "## Briefly",
            "A haiku to leave you with", "<!-- block:haiku -->",
        )
        order = [tpl.index(m) for m in markers]
        self.assertEqual(order, sorted(order), tpl)
        # `---` rules fence the blocks; the closing "discuss on Reddit" line is present.
        self.assertIn("\n---\n", tpl)
        self.assertIn("Check out the [Weekly Thing on Reddit]", tpl)


# ---------- section renderers (the repeated list loops) ----------

class SectionRendererTests(unittest.TestCase):
    def test_render_notable_reddit_line_headings_and_spacing(self):
        out = update_draft._render_notable(
            [
                {"title": "Thing One", "url": "https://a.example/1", "description": "Why it's good.\n\nMore."},
                {"title": "Thing Two", "url": "https://b.example/2", "description": ""},
            ],
            347,
        )
        # Reddit line first, with the issue number in the link text and URL.
        self.assertTrue(out.startswith("_You can discuss any of these links at the "
                                       "[Weekly Thing 347 tag in r/WeeklyThing]"))
        self.assertIn("flair_name%3A%22Weekly%20Thing%20347%22", out)
        # H3-link headings; the bare one (no commentary) is just the heading.
        self.assertIn("### [Thing One](https://a.example/1)\n\nWhy it's good.\n\nMore.", out)
        self.assertIn("### [Thing Two](https://b.example/2)", out)
        # Two blank lines between items.
        self.assertIn("More.\n\n\n### [Thing Two]", out)
        # No items → empty block (no orphan Reddit line).
        self.assertEqual(update_draft._render_notable([], 347), "")

    def test_render_brief_commentary_arrow_link(self):
        out = update_draft._render_brief([
            {"title": "Skeleton Key", "url": "https://x.example/sk", "description": "Cool app."},
            {"title": "Bare One", "url": "https://x.example/b", "description": ""},
        ])
        self.assertIn("Cool app. → **[Skeleton Key](https://x.example/sk)**", out)
        self.assertIn("**[Bare One](https://x.example/b)**", out)
        # One blank line between items.
        self.assertIn("**\n\n**[Bare One]", out)

    def test_render_journal_standard_and_elevated(self):
        out = update_draft._render_journal([
            {"url": "https://www.thingelstad.com/2026/05/12/a.html",
             "title": "", "published": "2026-05-12T15:02:00-05:00",
             "content_md": "A status update.\n\n![](https://files.thingelstad.com/weekly-thing/9/journal/x.jpg)"},
            {"url": "https://www.thingelstad.com/2026/05/13/software-is-liquid.html",
             "title": "Software Is Liquid", "published": "2026-05-13T07:52:00-05:00",
             "content_md": "A talk turned post."},
        ])
        # Standard entry: weekday + time as a link, then content (with the image in-content).
        self.assertIn("[Tuesday @ 3:02 PM](https://www.thingelstad.com/2026/05/12/a.html)\n\n"
                      "A status update.\n\n![](https://files.thingelstad.com/weekly-thing/9/journal/x.jpg)", out)
        # Elevated (titled) entry: H3 link with a hard break, label plain on the next line.
        self.assertIn("### [Software Is Liquid](https://www.thingelstad.com/2026/05/13/software-is-liquid.html)  \n"
                      "Wednesday @ 7:52 AM\n\nA talk turned post.", out)
        # Two blank lines between entries.
        self.assertIn("/journal/x.jpg)\n\n\n### [Software Is Liquid]", out)

    def test_render_journal_converts_utc_published_to_local(self):
        # micro.blog emits `published` in UTC; the label must be Central.
        # 2026-05-12T02:21Z → 2026-05-11 21:21 CDT.
        out = update_draft._render_journal([
            {"url": "https://www.thingelstad.com/2026/05/11/late.html",
             "title": "", "published": "2026-05-12T02:21:00Z", "content_md": "Posted late."},
        ])
        self.assertIn("[Monday @ 9:21 PM](https://www.thingelstad.com/2026/05/11/late.html)", out)
        self.assertNotIn("2:21 AM", out)

    def test_format_haiku(self):
        self.assertEqual(_base.format_haiku("line one\nline two\nline three"),
                         "**line one  \nline two  \nline three**")
        # Idempotent — peels an existing wrapper / re-runs cleanly.
        self.assertEqual(_base.format_haiku("**line one  \nline two  \nline three**"),
                         "**line one  \nline two  \nline three**")
        self.assertEqual(_base.format_haiku("**a\nb**"), "**a  \nb**")
        self.assertEqual(_base.format_haiku("   "), "")
        self.assertEqual(_base.format_haiku(""), "")


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

    def test_start_issue_writes_workshop_pointer(self):
        ctx = _base.JobContext(trigger="manual")
        result = asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-16", day_count=7, set_by="jamie"))
        self.assertTrue(result.ok, result.message)
        ptr = self.ws.workshop_pointer
        self.assertIsNotNone(ptr)
        self.assertEqual(ptr["issue_number"], 458)
        self.assertEqual(ptr["pub_date"], "2026-05-16")
        self.assertEqual(ptr["end_date"], "2026-05-15")
        self.assertEqual(ptr["start_date"], "2026-05-08")
        self.assertEqual(ptr["day_count"], 7)
        self.assertEqual(ptr["workspace_url"], "https://files.thingelstad.com/weekly-thing/458/")
        self.assertEqual(ptr["workspace_prefix"], "weekly-thing/458/")
        self.assertEqual(ptr["archive_url"], "https://weekly.thingelstad.com/archive/458/")
        self.assertIn("Weekly%20Thing%20458", ptr["reddit_tag_url"])
        # Predictable file URLs for what Shortcuts uploads + what the bot writes.
        for key in ("cover_jpg", "cover_json", "intro_md", "currently_json",
                    "haiku_md", "metadata_json", "draft_md", "draft_html",
                    "final_md", "publish_md", "publish_html"):
            self.assertTrue(ptr["files"][key].startswith("https://files.thingelstad.com/weekly-thing/458/"), key)
        self.assertEqual(ptr["set_by"], "jamie")
        # And the success message points at the pointer URL.
        self.assertIn("workshop.json", result.message)
        self.assertEqual(result.data["workshop_pointer_url"], "https://files.thingelstad.com/weekly-thing/workshop.json")

    def test_start_issue_pointer_failure_warns_but_succeeds(self):
        # Force the pointer write to blow up; the job should still succeed.
        from apps.workshop_bot.tools import s3 as s3_mod
        with patch.object(s3_mod, "write_workshop_pointer", lambda data: (_ for _ in ()).throw(RuntimeError("s3 down"))):
            result = asyncio.run(start_issue.run(_base.JobContext(), number=458, pub_date="2026-05-16"))
        self.assertTrue(result.ok, result.message)
        self.assertIn("couldn't refresh `workshop.json`", result.message)
        self.assertIsNone(self.ws.workshop_pointer)
        # Window still recorded, draft still seeded.
        self.assertEqual(db.get_active_issue_window()["issue_number"], 458)
        self.assertIn((458, "draft.md"), self.ws.files)


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
                                "[Tuesday @ 3:02 PM](https://www.thingelstad.com/x.html)\n\ntext")
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
        d = _base.replace_block(d, "journal", "[Tuesday @ 3:02 PM](https://x.example/y)\n\nt")
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
        # Notable carries the "discuss on Reddit" line with the issue number.
        self.assertIn("[Weekly Thing 458 tag in r/WeeklyThing]", d)
        # Briefly items are "<commentary> → **[Title](url)**".
        self.assertIn("A one-liner. → **[Thing Three](https://c.example/three)**", d)
        self.assertIn("[Tuesday @ 3:02 PM](https://www.thingelstad.com/2026/05/12/post-a.html)", d)
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

    def test_currently_json_renders_into_the_draft(self):
        self._set_window()
        self.ws.write_issue_file(
            458, "currently.json",
            '{"Listening":" Noah Kahan.","Watching":" Shrinking on Apple TV."}',
        )
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        d = self.ws.files[(458, "draft.md")]
        self.assertIn("**Listening:** Noah Kahan.\n\n**Watching:** Shrinking on Apple TV.", d)
        self.assertIn("## Currently", d)

    def test_currently_md_fallback_when_no_json(self):
        self._set_window()
        self.ws.write_issue_file(458, "currently.md", "**Reading:** a verbatim section.")
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        self.assertIn("**Reading:** a verbatim section.", self.ws.files[(458, "draft.md")])

    def test_cover_json_renders_image_caption_date_location(self):
        self._set_window()
        self.ws.write_issue_file(
            458, "cover.json",
            '{"caption":"Minnehaha Creek after the Falls.","location":"Minneapolis, MN","timestamp":"May 10, 2026"}',
        )
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        d = self.ws.files[(458, "draft.md")]
        # Cover image is emitted as a native <img> tag (with an alt attribute
        # slot the vision LLM fills on first sight). Test stubs leave alt
        # empty; the hygiene review surfaces empty alts.
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/cover.jpg" '
            'alt="" />\n\n'
            "Minnehaha Creek after the Falls.\n\nMay 10, 2026  \nMinneapolis, MN",
            d,
        )

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
    """Linky stub for the per-link scan runtime. ``replies`` is a list (or
    AsyncMock side_effect) — each consecutive ``linky.core`` call returns
    the next reply. ``channel.send`` returns a mock Discord message with
    an incrementing ``id`` so the test can assert recording behaviour."""

    def __init__(self, replies=None):
        self.channel = MagicMock()
        self._next_msg_id = 1000
        async def _fake_send(text, **_kw):
            self._next_msg_id += 1
            m = MagicMock()
            m.id = self._next_msg_id
            m.content = text
            return m
        self.channel.send = AsyncMock(side_effect=_fake_send)
        self.linky = MagicMock()
        self.linky.user = object()
        self.linky.get_channel = MagicMock(return_value=self.channel)
        if replies is None:
            replies = ["**[X](http://x)** — looks good"]
        self.linky.core = AsyncMock(
            side_effect=[(r, {"iterations": 1}) for r in replies]
        )
        self.bots = {"linky": self.linky}


def _deps_with_linky_team(team):
    deps = MagicMock()
    deps.team = team
    return deps


class PinboardScanJobTests(_DBTestCase):
    def _ctx_and_team(self, replies=None):
        team = _FakeLinkyTeam(replies=replies)
        return _base.JobContext(deps=_deps_with_linky_team(team)), team

    def _stub_sources(
        self, *, popular=None, toread=None, lobs=None, hn=None,
        tildes_items=None, indieweb_items=None,
    ):
        from apps.workshop_bot.systems.pinboard import client as pbc
        from apps.workshop_bot.tools import hackernews as hn_mod
        from apps.workshop_bot.tools import indieweb_news as iwn_mod
        from apps.workshop_bot.tools import lobsters as lob
        from apps.workshop_bot.tools import tildes as tldes_mod
        return [
            patch.object(pbc, "popular", lambda limit=30: list(popular or [])),
            patch.object(pbc, "toread_public_unresearched",
                         lambda limit=25: list(toread or [])),
            patch.object(lob, "hottest", lambda limit=25: list(lobs or [])),
            patch.object(hn_mod, "top", lambda limit=25: list(hn or [])),
            patch.object(tldes_mod, "top",
                         lambda limit=25: list(tildes_items or [])),
            patch.object(iwn_mod, "top",
                         lambda limit=20: list(indieweb_items or [])),
            # build_linky_context hits posts_all for queue depth — stub it cheap.
            patch.object(pbc, "posts_all", lambda **kw: []),
        ]

    def test_pass_when_both_sources_empty(self):
        ctx, team = self._ctx_and_team()
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        patches = self._stub_sources()
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["posted"], 0)
        team.linky.core.assert_not_awaited()
        team.channel.send.assert_not_awaited()

    def test_posts_card_for_toread_item(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=[
            "**[The Piece](https://example.com/x)** · [pin](https://pinboard.in/b/abc)\n\n"
            "A solid argument about X.\n\nFresh territory, likely Notable.\n\n📖 medium · `toread`"
        ])
        toread = [{
            "url": "https://example.com/x", "title": "The Piece",
            "description": "", "pinboard_url": "https://pinboard.in/b/abc",
        }]
        patches = self._stub_sources(toread=toread)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["posted"], 1)
        team.channel.send.assert_awaited_once()
        # Recorded the message id for reply lookup.
        sent_msg_id = team.channel.send.return_value or team.channel.send.await_args
        # The fake_send AsyncMock side_effect assigned msg ids starting at 1001.
        row = db.lookup_research_message("1001")
        self.assertIsNotNone(row, "linky_research_messages row missing")
        self.assertEqual(row["url"], "https://example.com/x")
        self.assertEqual(row["source"], "toread")

    def test_skip_signal_marks_popular_seen_no_post(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=["SKIP: not Jamie's lane"])
        popular = [{
            "url": "https://example.com/skip", "title": "Some Popular Item",
            "description": "", "posted_by": "user1",
        }]
        patches = self._stub_sources(popular=popular)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["posted"], 0)
        self.assertEqual(result.data["skip"], 1)
        team.channel.send.assert_not_awaited()
        # popular_seen has the row with judged_interesting = 0.
        import sqlite3 as _sql
        with db.connect() as conn:
            row = conn.execute(
                "SELECT judged_interesting, judgment_note FROM pinboard_popular_seen "
                "WHERE url = ?", ("https://example.com/skip",),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["judged_interesting"], 0)
        self.assertIn("not Jamie's lane", row["judgment_note"] or "")

    def test_fetch_failed_signal_does_not_mark_seen(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=["FETCH_FAILED: 404"])
        popular = [{
            "url": "https://example.com/stale", "title": "Stale",
            "description": "", "posted_by": "user1",
        }]
        patches = self._stub_sources(popular=popular)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["posted"], 0)
        self.assertEqual(result.data["fail"], 1)
        team.channel.send.assert_not_awaited()
        # Not in pinboard_popular_seen — URL can come back next scan.
        with db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM pinboard_popular_seen WHERE url = ?",
                ("https://example.com/stale",),
            ).fetchone()
        self.assertIsNone(row)

    def test_posts_card_for_lobsters_item(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=[
            "**[KDE Funding](https://kde.org/news)** · [lobste.rs](https://lobste.rs/s/yyfjd1)\n\n"
            "Sovereign Tech Fund invests in KDE.\n\nFresh territory, possible Notable.\n\n"
            "📖 short · `lobsters`"
        ])
        lobs = [{
            "url": "https://kde.org/news", "title": "KDE Funding",
            "discussion_url": "https://lobste.rs/s/yyfjd1",
            "tags": ["linux"], "score": 110, "comment_count": 15, "submitter": "zanlib",
        }]
        patches = self._stub_sources(lobs=lobs)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["posted"], 1)
        # Recorded with source='lobsters' for the reply / reaction lookup.
        row = db.lookup_research_message("1001")
        self.assertIsNotNone(row)
        self.assertEqual(row["source"], "lobsters")
        self.assertEqual(row["url"], "https://kde.org/news")
        self.assertEqual(row["title"], "KDE Funding")
        # The LLM saw the lobsters-specific signal in its user message.
        sent_user_msg = team.linky.core.call_args.kwargs["latest"]
        self.assertIn("Lobsters discussion", sent_user_msg)
        self.assertIn("110 points", sent_user_msg)

    def test_posts_card_for_hackernews_item(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=[
            "**[Linux gaming](https://www.xda-developers.com/linux-gaming/)** · "
            "[HN](https://news.ycombinator.com/item?id=48087887)\n\n"
            "Article on Windows-compat shims landing in the Linux kernel.\n\n"
            "Echoes #341's coverage of compat layers. Possible Notable.\n\n"
            "📖 medium · `hackernews`"
        ])
        hn = [{
            "url": "https://www.xda-developers.com/linux-gaming/",
            "title": "Linux gaming is faster",
            "discussion_url": "https://news.ycombinator.com/item?id=48087887",
            "score": 412, "comment_count": 187, "submitter": "haunter",
        }]
        patches = self._stub_sources(hn=hn)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["posted"], 1)
        row = db.lookup_research_message("1001")
        self.assertIsNotNone(row)
        self.assertEqual(row["source"], "hackernews")
        self.assertEqual(row["url"], "https://www.xda-developers.com/linux-gaming/")
        # The per-link block (the last `## The link` section) used the
        # HN-specific labels, not the lobsters ones. (The prompt body
        # legitimately enumerates every source type, so we only check
        # the per-link data that follows it.)
        sent_user_msg = team.linky.core.call_args.kwargs["latest"]
        link_block = sent_user_msg.rsplit("## The link", 1)[-1]
        self.assertIn("Hacker News discussion", link_block)
        self.assertIn("412 points", link_block)
        self.assertNotIn("Lobsters discussion", link_block)

    def test_lobsters_skip_marks_popular_seen(self):
        # SKIP from a lobsters source lands in the same shared
        # pinboard_popular_seen dedup as popular SKIPs.
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=["SKIP: too niche"])
        lobs = [{"url": "https://x/niche", "title": "Niche thing",
                 "discussion_url": "https://lobste.rs/s/abc", "tags": [],
                 "score": 5, "comment_count": 0, "submitter": "u"}]
        patches = self._stub_sources(lobs=lobs)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["posted"], 0)
        self.assertEqual(result.data["skip"], 1)
        with db.connect() as conn:
            row = conn.execute(
                "SELECT judged_interesting FROM pinboard_popular_seen WHERE url = ?",
                ("https://x/niche",),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["judged_interesting"], 0)

    def test_toread_first_then_popular_ordering(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        # Replies fire in toread → popular order; reply ids will confirm order.
        ctx, team = self._ctx_and_team(replies=[
            "**[T](https://t/1)** · [pin](https://pinboard.in/b/t)\n\nT.\n\nT.\n\n📖 short · `toread`",
            "**[P](https://p/1)**\n\nP.\n\nP.\n\n📖 short · `popular`",
        ])
        toread = [{"url": "https://t/1", "title": "T", "description": "",
                   "pinboard_url": "https://pinboard.in/b/t"}]
        popular = [{"url": "https://p/1", "title": "P", "description": "", "posted_by": "u"}]
        patches = self._stub_sources(popular=popular, toread=toread)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["posted"], 2)
        # The first recorded message id was the toread one.
        row_t = db.lookup_research_message("1001")
        row_p = db.lookup_research_message("1002")
        self.assertEqual(row_t["source"], "toread")
        self.assertEqual(row_p["source"], "popular")

    def test_skips_when_no_team(self):
        result = asyncio.run(pinboard_scan.run(_base.JobContext()))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["posted"], 0)

    def test_toread_public_unresearched_filters_three_ways(self):
        """The new ``toread_public_unresearched`` helper trims by toread-on,
        shared=yes, and the ``pinboard_research_done`` table. Lives in the
        DB-aware test class because the third filter is a DB read."""
        from apps.workshop_bot.systems.pinboard import client as pbc
        feed = [
            {"href": "https://ok/1", "description": "Public + new",
             "extended": "", "tags": "ai", "time": "2026-05-12T12:00:00Z",
             "toread": "yes", "shared": "yes"},
            {"href": "https://private/1", "description": "Private",
             "extended": "", "tags": "ai", "time": "2026-05-12T13:00:00Z",
             "toread": "yes", "shared": "no"},
            {"href": "https://ok/2", "description": "Already researched",
             "extended": "", "tags": "ai", "time": "2026-05-12T14:00:00Z",
             "toread": "yes", "shared": "yes"},
        ]
        db.mark_url_researched(url="https://ok/2", title="t", summary="s")
        with patch.object(pbc, "all_unread", lambda **kw: feed):
            out = pbc.toread_public_unresearched(limit=10)
        urls = [r["url"] for r in out]
        self.assertIn("https://ok/1", urls)
        self.assertNotIn("https://private/1", urls)
        self.assertNotIn("https://ok/2", urls)

    # ---------- cross-source signal ----------

    def test_cross_source_in_scan_merge_collapses_duplicates(self):
        """Same URL on lobsters AND hackernews in the same scan, both
        fresh — one card posted, both discussion URLs in the input
        block, primary chosen by registry priority (lobsters > hn)."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=[
            "**[Shared](https://x.example/y)** · [lobste.rs](https://lobste.rs/s/abc) "
            "· [HN](https://news.ycombinator.com/item?id=1)\n\n"
            "Cross-source story.\n\nFresh territory.\n\n📖 short · `lobsters`"
        ])
        same_url = "https://x.example/y"
        lobs = [{
            "url": same_url, "title": "Shared (Lobsters title)",
            "discussion_url": "https://lobste.rs/s/abc",
            "score": 50, "comment_count": 10, "submitter": "u_lob",
        }]
        hn = [{
            "url": same_url, "title": "Shared (HN title)",
            "discussion_url": "https://news.ycombinator.com/item?id=1",
            "score": 200, "comment_count": 80, "submitter": "u_hn",
        }]
        patches = self._stub_sources(lobs=lobs, hn=hn)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["posted"], 1)
        # Exactly one LLM call — the in-scan dupe was merged, not double-LLM'd.
        self.assertEqual(team.linky.core.await_count, 1)
        # Primary went to lobsters (higher priority_priority than hackernews).
        row = db.lookup_research_message("1001")
        self.assertEqual(row["source"], "lobsters")
        # User_msg shows both discussion URLs + "Also trending on" line.
        sent = team.linky.core.call_args.kwargs["latest"]
        self.assertIn("https://lobste.rs/s/abc", sent)
        self.assertIn("https://news.ycombinator.com/item?id=1", sent)
        self.assertIn("Also trending on (this scan):", sent)
        # Sightings recorded for BOTH feeds (the primary and the merged-in
        # co-source) so a future scan won't re-uplift either.
        self.assertTrue(db.feed_has_seen(url=same_url, source="lobsters"))
        self.assertTrue(db.feed_has_seen(url=same_url, source="hackernews"))

    def test_cross_source_normalises_utm_params(self):
        """The dedup key strips utm_* params, so the same article on
        two feeds with different tracking suffixes collapses."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=[
            "**[Shared](https://x.example/article)**\n\nA.\n\nB.\n\n📖 short · `lobsters`"
        ])
        lobs = [{
            "url": "https://x.example/article?utm_source=lobsters",
            "title": "Shared",
        }]
        hn = [{
            "url": "https://x.example/article?utm_source=hn",
            "title": "Shared",
        }]
        patches = self._stub_sources(lobs=lobs, hn=hn)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        # One card despite different surface URLs — same dedup key.
        self.assertEqual(result.data["posted"], 1)
        self.assertEqual(team.linky.core.await_count, 1)

    def test_cross_source_uplift_when_url_seen_on_different_feed_previously(self):
        """A URL first seen on HN three days ago, judged interesting,
        appears today on Tildes. The Tildes appearance becomes an
        uplift candidate: the user_msg includes ## Cross-source uplift
        with the HN history + verdict, the card lands on #research with
        source='tildes', and the sighting is recorded so the next scan
        won't re-uplift the same Tildes appearance."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        # Seed: URL is in pinboard_popular_seen (card was posted) and
        # popular_seen_sightings has one row from HN.
        url = "https://x.example/article"
        db.mark_popular_seen(
            [{"url": url, "title": "Original Title"}],
            judged={url: (True, "card posted")},
        )
        db.record_sighting(url=url, source="hackernews")

        ctx, team = self._ctx_and_team(replies=[
            "**[New angle](https://x.example/article)** · [tildes](https://tildes.net/~tech/x)\n\n"
            "Picked up by Tildes.\n\nFresh angle.\n\n📖 short · `tildes`"
        ])
        tildes_items = [{
            "url": url, "title": "Tildes title",
            "discussion_url": "https://tildes.net/~tech/x",
        }]
        patches = self._stub_sources(tildes_items=tildes_items)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["posted"], 1)
        self.assertEqual(result.data["uplift"], 1)
        # Card recorded under the new feed's source.
        row = db.lookup_research_message("1001")
        self.assertEqual(row["source"], "tildes")
        # User_msg includes the uplift block.
        sent = team.linky.core.call_args.kwargs["latest"]
        self.assertIn("## Cross-source uplift", sent)
        self.assertIn("Hacker News", sent)
        self.assertIn("Previous verdict:", sent)
        # New sighting was recorded — so a future scan won't reuplift
        # the same Tildes-already-seen URL.
        self.assertTrue(db.feed_has_seen(url=url, source="tildes"))

    def test_cross_source_uplift_carries_skip_history_when_previous_verdict_was_skip(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/skipped"
        db.mark_popular_seen(
            [{"url": url, "title": "Skipped Earlier"}],
            judged={url: (False, "thin reaction post")},
        )
        db.record_sighting(url=url, source="hackernews")

        ctx, team = self._ctx_and_team(replies=["SKIP: still thin"])
        lobs = [{
            "url": url, "title": "lobsters title",
            "discussion_url": "https://lobste.rs/s/qq",
        }]
        patches = self._stub_sources(lobs=lobs)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["posted"], 0)
        self.assertEqual(result.data["skip"], 1)
        sent = team.linky.core.call_args.kwargs["latest"]
        self.assertIn("## Cross-source uplift", sent)
        self.assertIn("SKIP'd from", sent)
        self.assertIn("thin reaction post", sent)
        # Original verdict in pinboard_popular_seen is preserved (still SKIP'd).
        with db.connect() as conn:
            row = conn.execute(
                "SELECT judged_interesting, judgment_note FROM pinboard_popular_seen "
                "WHERE url = ?", (url,),
            ).fetchone()
        self.assertEqual(row["judged_interesting"], 0)
        self.assertEqual(row["judgment_note"], "thin reaction post")
        # The new Lobsters sighting was recorded.
        self.assertTrue(db.feed_has_seen(url=url, source="lobsters"))

    def test_cross_source_same_feed_repeat_silently_dropped(self):
        """URL on HN today, already sighted from HN before. Today's
        silent-dedup applies: no LLM call, no card, no new sighting."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/repeat"
        db.mark_popular_seen([{"url": url, "title": "Repeat"}],
                              judged={url: (True, "card posted")})
        db.record_sighting(url=url, source="hackernews")

        ctx, team = self._ctx_and_team(replies=[])
        hn = [{"url": url, "title": "Repeat", "discussion_url": "https://news.ycombinator.com/item?id=2"}]
        patches = self._stub_sources(hn=hn)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["posted"], 0)
        team.linky.core.assert_not_awaited()

    # ---------- archive resonance pre-step ----------

    def _ctx_with_corpus_search(self, *, hits, replies):
        """Build a ctx whose `deps.corpus.search(query, k)` returns a
        canned list of chunks. Captures the query string so tests can
        assert the per-source query strategy."""
        ctx, team = self._ctx_and_team(replies=replies)
        # The default deps MagicMock auto-creates `corpus.search` —
        # configure it to return our canned hits and remember the call.
        ctx.deps.corpus.search.return_value = list(hits)
        return ctx, team

    def test_archive_resonance_block_renders_when_hits_present(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_with_corpus_search(
            hits=[
                {"issue_number": 341, "publish_date": "2025-09-13",
                 "section": "Notable", "subject": "Vibe coding & AI",
                 "text": "A solid argument about maintenance cost..."},
                {"issue_number": 287, "publish_date": "2024-08-15",
                 "section": "Briefly", "subject": "Old take", "text": "Earlier mention."},
            ],
            replies=[
                "**[A](https://x/y)**\n\nB.\n\nFresh.\n\n📖 short · `lobsters`"
            ],
        )
        lobs = [{"url": "https://x/y", "title": "Vibe coding article",
                 "discussion_url": "https://lobste.rs/s/abc"}]
        patches = self._stub_sources(lobs=lobs)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok, result.message)
        sent = team.linky.core.call_args.kwargs["latest"]
        self.assertIn("## Archive resonance", sent)
        self.assertIn("#341 (2025-09-13) · Notable — \"Vibe coding & AI\"", sent)
        self.assertIn("#287 (2024-08-15) · Briefly — \"Old take\"", sent)
        # Snippets should appear under each hit (the `>` blockquote line).
        self.assertIn("> A solid argument about maintenance cost...", sent)

    def test_archive_resonance_block_no_resonance_when_empty(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_with_corpus_search(
            hits=[],
            replies=["**[A](https://x/y)**\n\nB.\n\nFresh.\n\n📖 short · `lobsters`"],
        )
        lobs = [{"url": "https://x/y", "title": "Title"}]
        patches = self._stub_sources(lobs=lobs)
        try:
            for p in patches:
                p.start()
            try:
                asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        sent = team.linky.core.call_args.kwargs["latest"]
        self.assertIn("## Archive resonance", sent)
        self.assertIn("_(no resonance — fresh territory)_", sent)

    def test_archive_resonance_truncates_long_snippets(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        long_text = "word " * 500  # 2500 chars, will be aggressively truncated
        ctx, team = self._ctx_with_corpus_search(
            hits=[{"issue_number": 1, "publish_date": "2025-01-01",
                   "section": "Notable", "subject": "Long", "text": long_text}],
            replies=["**[A](https://x/y)**\n\nB.\n\nB.\n\n📖 short · `lobsters`"],
        )
        lobs = [{"url": "https://x/y", "title": "T"}]
        patches = self._stub_sources(lobs=lobs)
        try:
            for p in patches:
                p.start()
            try:
                asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        sent = team.linky.core.call_args.kwargs["latest"]
        # Find the snippet line and check its length.
        snippet_lines = [l for l in sent.splitlines() if l.startswith("  > ")]
        self.assertEqual(len(snippet_lines), 1)
        body = snippet_lines[0][4:]  # strip "  > "
        # Cap is 180 chars + ellipsis (so up to ~181). Definitely much
        # less than the 2500-char raw.
        self.assertLess(len(body), 200)
        self.assertTrue(body.endswith("…"))

    def test_archive_resonance_uses_title_plus_description_for_toread(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_with_corpus_search(
            hits=[],
            replies=["**[A](https://x/y)** · [pin](https://pinboard.in/b/abc)\n\nA.\n\nB.\n\n📖 short · `toread`"],
        )
        toread = [{
            "url": "https://x/y", "title": "Bare title",
            "description": "Jamie's existing notes — meta-topic stuff",
            "pinboard_url": "https://pinboard.in/b/abc",
        }]
        patches = self._stub_sources(toread=toread)
        try:
            for p in patches:
                p.start()
            try:
                asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        # corpus.search was called with title + description (toread path).
        call_args = ctx.deps.corpus.search.call_args
        # Could be positional or keyword — pull the first positional arg.
        query = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
        self.assertIn("Bare title", query)
        self.assertIn("Jamie's existing notes", query)

    def test_archive_resonance_uses_title_only_for_discovery_sources(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_with_corpus_search(
            hits=[],
            replies=["**[A](https://x/y)**\n\nA.\n\nB.\n\n📖 short · `hackernews`"],
        )
        hn = [{
            "url": "https://x/y", "title": "Title only",
            # Even if `description` shows up on an HN dict, it's not
            # part of the query for discovery sources.
            "description": "should not be in the query",
        }]
        patches = self._stub_sources(hn=hn)
        try:
            for p in patches:
                p.start()
            try:
                asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        call_args = ctx.deps.corpus.search.call_args
        query = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
        self.assertIn("Title only", query)
        self.assertNotIn("should not be in the query", query)

    def test_cross_source_uplift_per_scan_cap_enforced(self):
        """Six uplift candidates in one scan: only the cap (5) are
        processed; the sixth's sighting is NOT recorded so it stays
        uplift-eligible on the next scan."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        # Seed six distinct URLs, each first-seen on HN with a card-posted
        # verdict, with one HN sighting each.
        urls = [f"https://x.example/u{i}" for i in range(6)]
        for u in urls:
            db.mark_popular_seen([{"url": u, "title": u}],
                                  judged={u: (True, "card posted")})
            db.record_sighting(url=u, source="hackernews")
        # Today's Tildes feed has all six.
        tildes_items = [{"url": u, "title": f"t-{u}",
                         "discussion_url": f"https://tildes.net/~tech/{i}"}
                        for i, u in enumerate(urls)]
        ctx, team = self._ctx_and_team(replies=[
            f"**[T{i}](https://x.example/u{i})**\n\nA.\n\nB.\n\n📖 short · `tildes`"
            for i in range(5)
        ])
        patches = self._stub_sources(tildes_items=tildes_items)
        try:
            for p in patches:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        # Only the cap (5) processed; the 6th left for next time.
        self.assertEqual(result.data["uplift"], 5)
        self.assertEqual(team.linky.core.await_count, 5)
        # 5 URLs had a Tildes sighting recorded. The 6th — whichever
        # was beyond the cap — does NOT have one yet.
        recorded = [u for u in urls if db.feed_has_seen(url=u, source="tildes")]
        self.assertEqual(len(recorded), 5)


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

    def test_set_description_replaces_in_place(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        captured = {}

        def fake_get(url):
            return {"posts": [{
                "href": url, "description": "Existing Title",
                "extended": "old commentary",
                "tags": "ai web", "shared": "yes", "toread": "yes",
            }]}

        def fake_add(*, url, title, description, tags, toread, shared, replace):
            captured.update(dict(url=url, title=title, description=description,
                                 tags=tags, toread=toread, shared=shared, replace=replace))
            return {"result_code": "done", "pinboard_url": f"https://pinboard.in/b/{url}"}

        with patch.object(pbc, "posts_get", fake_get), patch.object(pbc, "posts_add", fake_add):
            out = pbc.set_description("https://example.com/x", "Jamie's new commentary")
        self.assertEqual(out["result_code"], "done")
        self.assertFalse(out["created"])
        self.assertTrue(out["replaced"])
        # Description replaced; everything else preserved.
        self.assertEqual(captured["description"], "Jamie's new commentary")
        self.assertEqual(captured["title"], "Existing Title")
        self.assertEqual(set(captured["tags"].split()), {"ai", "web"})  # no _brief added
        self.assertTrue(captured["toread"])  # toread preserved
        self.assertTrue(captured["shared"])
        self.assertTrue(captured["replace"])

    def test_set_description_creates_when_not_bookmarked(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        captured = {}

        def fake_add(*, url, title, description, tags, toread, shared, replace):
            captured.update(dict(url=url, title=title, description=description,
                                 tags=tags, toread=toread, shared=shared, replace=replace))
            return {"result_code": "done", "pinboard_url": f"https://pinboard.in/b/{url}"}

        with patch.object(pbc, "posts_get", lambda u: {"posts": []}), \
             patch.object(pbc, "posts_add", fake_add):
            out = pbc.set_description(
                "https://example.com/new", "first take",
                fallback_title="Some Popular Title",
            )
        self.assertTrue(out["created"])
        self.assertFalse(out["replaced"])
        # New bookmark gets toread=yes shared=yes, no replace, fallback title used.
        self.assertEqual(captured["title"], "Some Popular Title")
        self.assertEqual(captured["description"], "first take")
        self.assertTrue(captured["toread"])
        self.assertTrue(captured["shared"])
        self.assertFalse(captured["replace"])


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

    def test_issue_window_candidates_skips_toread_and_private(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        feed = [
            {"href": "https://ok/1", "description": "Ready", "extended": "x", "tags": "ai", "time": "2026-05-10T12:00:00Z", "toread": "no", "shared": "yes"},
            {"href": "https://unread/1", "description": "Still toread", "extended": "x", "tags": "ai", "time": "2026-05-10T13:00:00Z", "toread": "yes", "shared": "yes"},
            {"href": "https://private/1", "description": "Private", "extended": "x", "tags": "ai", "time": "2026-05-10T14:00:00Z", "toread": "no", "shared": "no"},
            {"href": "https://unread/2", "description": "Brief but toread", "extended": "x", "tags": "ai _brief", "time": "2026-05-11T12:00:00Z", "toread": "yes", "shared": "yes"},
            {"href": "https://ok/2", "description": "Brief ready", "extended": "x", "tags": "ai _brief", "time": "2026-05-11T13:00:00Z", "toread": "no", "shared": "yes"},
        ]
        with patch.object(pbc, "posts_all", lambda **kw: feed):
            out = pbc.issue_window_candidates("2026-05-08", "2026-05-15")
        self.assertEqual([n["url"] for n in out["notable"]], ["https://ok/1"])
        self.assertEqual([b["url"] for b in out["brief"]], ["https://ok/2"])

    def test_issue_window_candidates_uses_local_date_for_boundaries(self):
        """Pinboard timestamps are UTC; the window is local (America/Chicago).
        A bookmark saved at 22:30 CDT (= 03:30 UTC next day) belongs to the
        local day, not the UTC one. This pins the day-boundary so a future
        refactor can't silently regress."""
        from apps.workshop_bot.systems.pinboard import client as pbc
        # Window: 2026-05-08 (exclusive) .. 2026-05-15 (inclusive), local CT.
        feed = [
            # 22:30 CDT on end_date (2026-05-15) → 03:30 UTC on 2026-05-16.
            # Old UTC-date code would have excluded this. Local-date code
            # includes it.
            {"href": "https://late-end/1", "description": "Late on end day",
             "extended": "x", "tags": "ai", "time": "2026-05-16T03:30:00Z",
             "toread": "no", "shared": "yes"},
            # 04:00 UTC on 2026-05-09 = 23:00 CDT on 2026-05-08 (start_date).
            # Old UTC-date code would have included it as 2026-05-09; local-date
            # code excludes it (it's still on the prior issue's last local day).
            {"href": "https://early-start/1", "description": "Early past start",
             "extended": "x", "tags": "ai", "time": "2026-05-09T04:00:00Z",
             "toread": "no", "shared": "yes"},
            # 05:30 UTC on 2026-05-09 = 00:30 CDT on 2026-05-09 — first local
            # day strictly after start_date. Included.
            {"href": "https://just-in/1", "description": "Just past midnight",
             "extended": "x", "tags": "ai", "time": "2026-05-09T05:30:00Z",
             "toread": "no", "shared": "yes"},
        ]
        with patch.object(pbc, "posts_all", lambda **kw: feed):
            out = pbc.issue_window_candidates("2026-05-08", "2026-05-15")
        urls = [n["url"] for n in out["notable"]]
        self.assertIn("https://late-end/1", urls)
        self.assertIn("https://just-in/1", urls)
        self.assertNotIn("https://early-start/1", urls)
        # added_date is also recorded as the local date, not the UTC one.
        added = {n["url"]: n["added_date"] for n in out["notable"]}
        self.assertEqual(added["https://late-end/1"], "2026-05-15")
        self.assertEqual(added["https://just-in/1"], "2026-05-09")


class PinboardServerNewToolsTests(unittest.TestCase):
    def _server(self):
        from apps.workshop_bot.systems.pinboard.server import PinboardServer
        return {t.name: t for t in PinboardServer().list_tools()}

    def test_new_verbs_registered(self):
        tools = self._server()
        for name in ("issue_candidates", "capture_blurb", "popular_unseen", "mark_seen",
                     "queue_depth_vs_deadline", "archive_recall"):
            self.assertIn(name, tools, f"missing pinboard verb {name}")
        # Thin mirrors still present.
        for name in ("recent", "unread", "save", "lookup_url", "tags"):
            self.assertIn(name, tools)
        # Trimmed away.
        for name in ("popular", "stored_recent", "tag_summary", "archive_tags",
                     "bookmark_dates", "update_check", "suggest_tags", "estimate_read_length"):
            self.assertNotIn(name, tools)

    def test_issue_candidates_section_enum(self):
        tools = self._server()
        schema = tools["issue_candidates"].input_schema
        self.assertEqual(schema["properties"]["section"]["enum"], ["notable", "brief"])

    def test_read_length_buckets(self):
        from apps.workshop_bot.tools import web
        with patch.object(web, "fetch_text", lambda url, max_chars=0: {"text": "word " * 100}):
            self.assertEqual(web.read_length("http://x")["bucket"], "short")
        with patch.object(web, "fetch_text", lambda url, max_chars=0: {"text": "word " * 5000}):
            self.assertEqual(web.read_length("http://x")["bucket"], "long")
        with patch.object(web, "fetch_text", lambda url, max_chars=0: {"error": "paywall"}):
            self.assertEqual(web.read_length("http://x")["bucket"], "unknown")


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


def _filled_final(*, notable="### [A](http://a)\n\nx", brief="A blurb. → **[B](http://b)**",
                  journal="[Tuesday @ 3:02 PM](https://x.example/p)\n\nt") -> str:
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


class BuildPublishHelperTests(unittest.TestCase):
    def test_membership_block_slots_the_cta(self):
        out = build_publish._membership_block("  Become a member of the EFF crew.  ")
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", out)
        self.assertIn("{% elif subscriber.subscriber_type == 'regular' %}", out)
        self.assertIn("{% else %}", out)
        self.assertIn("{% endif %}", out)
        # CTA copy appears in the premium + regular branches (trimmed).
        self.assertEqual(out.count("Become a member of the EFF crew."), 2)
        self.assertIn("buy.stripe.com/3cs7w5eX6aXBbhm144", out)
        self.assertIn("{{ subscribe_form }}", out)

    def test_pixel_block_is_liquid_gated_and_issue_scoped(self):
        out = build_publish._pixel_block(347)
        self.assertTrue(out.startswith("{% if medium == 'email' %}"))
        self.assertIn("https://tinylytics.app/pixel/a2YQr3ZMqkySNYSwz4uF.gif?path=/email/347/", out)
        self.assertTrue(out.endswith("{% endif %}"))

    def test_for_preview_strips_liquid_and_keeps_regular_branch(self):
        raw = (
            "<!-- buttondown-editor-mode: plaintext -->Hi there.\n\n---\n\n"
            + build_publish._membership_block("Support the cause.")
            + "\n\n---\n\nA haiku to leave you with…\n\n**a  \nb  \nc**\n\n"
            + build_publish._CLOSING + "\n\n" + build_publish._pixel_block(347)
        )
        p = build_publish._for_preview(raw)
        self.assertNotIn("buttondown-editor-mode", p)
        self.assertNotIn("{%", p)
        self.assertNotIn("{{", p)
        self.assertNotIn("tinylytics.app/pixel", p)   # email-only block removed wholesale
        self.assertIn("Support the cause.", p)        # regular branch kept
        self.assertIn("$4 monthly", p)                # the buttons' text survives
        self.assertIn("Hi there.", p)
        self.assertIn("A haiku to leave you with", p)


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
        self.ws.write_issue_file(458, "cover.md", "Docks on the lake.\n\nApril 26, 2026  \nExcelsior, MN")
        self.ws.write_issue_file(458, "haiku.md", "line one\nline two\nline three")
        self.ws.write_issue_file(458, "currently.md", "Reading: a book.")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")  # presence only
        self.ws.write_issue_file(458, "cta-1.md", "---\nplacement: after_notable\n---\n\nSupport the EFF.")
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        # Editor-mode comment glommed onto the intro, the way the raw bodies are.
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Welcome to the issue."), pub[:80])
        self.assertIn("line two", pub)
        self.assertIn("Reading: a book.", pub)
        self.assertNotIn("<!-- block:", pub)            # markers stripped
        # Cover block — image (derived URL, native <img> tag) then the
        # caption/date/location below.
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/cover.jpg"',
            pub,
        )
        self.assertIn("Docks on the lake.", pub)
        # `---`-fenced, the way a real issue is.
        self.assertIn("\n\n---\n\n", pub)
        # Section order: intro → Currently → cover → Notable → Journal → Briefly → haiku.
        order = [pub.index(h) for h in (
            "## Currently", "/cover.jpg", "## Notable", "## Journal", "## Briefly",
            "A haiku to leave you with",
        )]
        self.assertEqual(order, sorted(order), pub)
        self.assertLess(pub.index("Reading: a book."), pub.index("/cover.jpg"), pub)
        # CTA with placement after_notable lands between Notable and Journal,
        # wrapped in the membership-block Liquid (premium/regular+Stripe/else+form).
        self.assertGreater(pub.index("Support the EFF."), pub.index("## Notable"))
        self.assertLess(pub.index("Support the EFF."), pub.index("## Journal"))
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", pub)
        self.assertIn("https://buy.stripe.com/3cs7w5eX6aXBbhm144?prefilled_email={{ subscriber.email | urlencode }}", pub)
        self.assertIn("{{ subscribe_form }}", pub)
        # Closing boilerplate, then the email-only Tinylytics pixel.
        self.assertIn("Check out the [Weekly Thing on Reddit]", pub)
        self.assertIn("{% if medium == 'email' %}", pub)
        self.assertIn("https://tinylytics.app/pixel/a2YQr3ZMqkySNYSwz4uF.gif?path=/email/458/", pub)
        # publish.html written too — no draft banner (it's the ship body), and
        # Liquid-stripped (a regular-subscriber rendering of the email).
        html = self.ws.files[(458, "publish.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Weekly Thing 458</title>", html)
        self.assertNotIn('class="banner"', html)
        self.assertNotIn("{% if", html)
        self.assertNotIn("{{ subscribe_form }}", html)
        self.assertNotIn("tinylytics.app/pixel", html)
        self.assertIn("Support the EFF.", html)
        self.assertIn("$4 monthly", html)
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/publish.html")

    def test_currently_json_renders_into_publish_md(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        self.ws.write_issue_file(458, "currently.json", '{"Listening":" Noah Kahan.","Watching":" Shrinking."}')
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertIn("## Currently\n\n**Listening:** Noah Kahan.\n\n**Watching:** Shrinking.", pub)

    def test_cta_default_placement_is_after_notable(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        # No `placement:` frontmatter → defaults to after_notable.
        self.ws.write_issue_file(458, "cta-1.md", "Become a member.")
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertGreater(pub.index("Become a member."), pub.index("## Notable"))
        self.assertLess(pub.index("Become a member."), pub.index("## Journal"))

    def test_no_currently_means_no_currently_heading(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        # No currently.md, no cover.md.
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertNotIn("## Currently", pub)            # empty optional section dropped
        self.assertNotIn("/cover.jpg)", pub)             # no cover.md → no cover block
        self.assertIn("## Notable", pub)
        self.assertIn("A haiku to leave you with", pub)
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Intro."), pub[:60])


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

    def _window(self, n=458):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def test_writes_metadata_json(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        subj_reply = ("Here are the options:\n\n"
                      "1. WT458 — The Death of Scrum\n2. WT458 — Value Over Token Consumption\n"
                      "3. WT458 — How Companies Learn With AI\n4. WT458 — Agentic Coding Is a Trap\n"
                      "5. WT458 — Scrum, FilamentHound, DO_NOT_TRACK")
        # The description prompt now returns a single comma-separated line
        # (no numbered list, no picker) — the job takes it verbatim.
        desc_reply = ("Claude personal guidance, Redis array type, watchOS maps, "
                      "AI company learning, agentic coding, Death of Scrum.")
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(side_effect=[(subj_reply, {"iterations": 1}), (desc_reply, {"iterations": 1})])
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j
        meta = _j.loads(self.ws.files[(458, "metadata.json")])
        self.assertEqual(meta["number"], 458)
        self.assertEqual(meta["subject"], "WT458 — The Death of Scrum")
        self.assertEqual(meta["description"], desc_reply)
        self.assertEqual(meta["slug"], "458")
        self.assertTrue(meta["image"].endswith("/458/cover.jpg"))
        self.assertTrue(meta["publish_date"].startswith("2026-05-16"))
        # The success post in #editorial surfaces both subject and description.
        sent = fc.channel.send.await_args_list[-1].args[0]
        self.assertIn("**Subject:** WT458 — The Death of Scrum", sent)
        self.assertIn("**Description:** Claude personal guidance,", sent)

    def test_empty_description_reply_writes_empty_description(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        # Model returns an empty description (whitespace only) — metadata.json
        # still written with the picked subject and an empty description.
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(side_effect=[
            ("1. WT458 — Picked Subject\n2. WT458 — B", {}),
            ("   \n  \n", {}),
        ])
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j
        meta = _j.loads(self.ws.files[(458, "metadata.json")])
        self.assertEqual(meta["subject"], "WT458 — Picked Subject")
        self.assertEqual(meta["description"], "")

    def test_first_nonempty_line(self):
        # The description prompt is "Output: a single line"; the helper
        # strips leading/trailing blank lines + per-line whitespace.
        self.assertEqual(
            compose_meta._first_nonempty_line("   \n\nA single concrete description.\n  "),
            "A single concrete description.",
        )
        self.assertEqual(
            compose_meta._first_nonempty_line(
                "Claude personal guidance, Redis arrays, FilamentHound, Death of Scrum."
            ),
            "Claude personal guidance, Redis arrays, FilamentHound, Death of Scrum.",
        )
        self.assertEqual(compose_meta._first_nonempty_line(""), "")
        self.assertEqual(compose_meta._first_nonempty_line("   \n\n"), "")

    def test_no_subject_pick_fails_cleanly(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        fc = _FakeBotChannel(persona="eddy", reply="1. WT458 — A\n2. WT458 — B")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertFalse(result.ok)
        self.assertNotIn((458, "metadata.json"), self.ws.files)

    def test_parse_numbered_list_tolerates_wrappers(self):
        text = ("Sure — here you go:\n\n"
                "1.  **WT458 — One**  \n"
                "2. `WT458 — Two`\n"
                "3. WT458 — Three\n\n"
                "Hope that helps.")
        self.assertEqual(
            compose_meta._parse_numbered_list(text, 8),
            ["WT458 — One", "WT458 — Two", "WT458 — Three"],
        )


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
        self.assertIn("issue haiku", result.message)
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


class DraftReviewTests(_DBTestCase):
    """update_draft._draft_review — the editorial pass embedded in draft.html."""

    def _args(self):
        from datetime import date
        st = draft_mod.section_status(458, draft_text=_base.starter_template(), list_objects=set())
        return {"issue_number": 458}, st, None, date.today(), "## Notable\n\n### [A](http://a)\n\nblurb."

    def test_returns_review_markdown_when_eddy_replies(self):
        window, st, prev, today, draft_text = self._args()
        fc = _FakeBotChannel(persona="eddy", reply="## Notable\n\n- Tighten the wuphf blurb.")
        ctx = _base.JobContext(deps=fc.deps())
        out = asyncio.run(update_draft._draft_review(ctx, window, st, prev, today, draft_text))
        self.assertEqual(out, "## Notable\n\n- Tighten the wuphf blurb.")
        fc.bot.core.assert_awaited()

    def test_pass_reply_yields_empty_review(self):
        window, st, prev, today, draft_text = self._args()
        fc = _FakeBotChannel(persona="eddy", reply="PASS")
        ctx = _base.JobContext(deps=fc.deps())
        out = asyncio.run(update_draft._draft_review(ctx, window, st, prev, today, draft_text))
        self.assertEqual(out, "")

    def test_no_team_yields_empty_review(self):
        window, st, prev, today, draft_text = self._args()
        out = asyncio.run(update_draft._draft_review(_base.JobContext(), window, st, prev, today, draft_text))
        self.assertEqual(out, "")

    def test_prompt_carries_hygiene_walk(self):
        # The hygiene walk lives in the prompt itself — one Sonnet call,
        # no separate scanner. Pin it so a future edit can't silently drop
        # the deliverability lens.
        from apps.workshop_bot.tools import anthropic_client
        # Clear the in-process cache so a parallel test that already loaded
        # the prompt doesn't shadow what's on disk right now.
        anthropic_client._prompt_cache.pop("eddy-draft-review", None)
        prompt = anthropic_client.load_prompt("eddy-draft-review")
        # Section heading + the distinguishing-lens framing.
        self.assertIn("**Hygiene**", prompt)
        self.assertIn("deliverability", prompt.lower())
        # The most-load-bearing checks.
        for token in ("Anchor text quality", "Heading hype", "Spam-filter signal",
                      "Alt-text quality", "anchor/domain mismatch"):
            self.assertIn(token, prompt)

    def test_hygiene_section_surfaces_in_returned_review(self):
        # When Eddy returns a review with a Hygiene section the bot passes it
        # through verbatim — the drawer renders multi-section markdown cleanly.
        window, st, prev, today, draft_text = self._args()
        reply = (
            "## Notable\n\n"
            "- Tighten the opening line of the Wuphf blurb.\n\n"
            "## Hygiene\n\n"
            "- Anchor reads like ad copy: `> click here to read the most insightful "
            "take on AI yet`. The destination is a level-headed essay; lead with the "
            "argument, not the hype."
        )
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        ctx = _base.JobContext(deps=fc.deps())
        out = asyncio.run(update_draft._draft_review(ctx, window, st, prev, today, draft_text))
        self.assertEqual(out, reply)
        self.assertIn("## Hygiene", out)


class LinkyReplyHandlerTests(_DBTestCase):
    """LinkyBot's research-reply listener: Jamie's reply to a per-link
    research card writes his text as the Pinboard bookmark's description.
    """

    def setUp(self):
        super().setUp()
        import types
        from apps.workshop_bot.personas.linky import LinkyBot
        self.bot = LinkyBot.__new__(LinkyBot)
        self.bot.user = MagicMock()
        self.bot.user.id = 1000
        self.bot.deps = types.SimpleNamespace(team=None, corpus=None)
        os.environ["DISCORD_OWNER_USER_ID"] = "777"

    def tearDown(self):
        os.environ.pop("DISCORD_OWNER_USER_ID", None)
        super().tearDown()

    def _msg(self, *, author_id, content, reference_id=None):
        m = MagicMock()
        m.guild = object()
        m.author = MagicMock()
        m.author.id = author_id
        m.author.bot = False
        m.author.__eq__ = lambda s, other: False  # not Linky
        m.content = content
        if reference_id is not None:
            m.reference = MagicMock()
            m.reference.message_id = reference_id
        else:
            m.reference = None
        m.add_reaction = AsyncMock()
        m.reply = AsyncMock()
        return m

    def _patch_set(self, *, side_effect=None, return_value=None):
        from apps.workshop_bot.systems.pinboard import client as pbc
        return patch.object(pbc, "set_description",
                            side_effect=side_effect, return_value=return_value)

    def test_non_reply_passes_through(self):
        m = self._msg(author_id=777, content="hi")
        out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertFalse(out)

    def test_reply_to_unknown_message_passes_through(self):
        m = self._msg(author_id=777, content="hi", reference_id=99999)
        out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertFalse(out)

    def test_reply_from_non_owner_passes_through(self):
        db.record_research_message(
            discord_message_id="1001", url="http://x", source="toread",
        )
        m = self._msg(author_id=888, content="hi", reference_id=1001)
        out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertFalse(out)

    def test_jamie_reply_to_toread_card_writes_description(self):
        db.record_research_message(
            discord_message_id="1001", url="http://x", source="toread",
            title="Some Title",
        )
        m = self._msg(
            author_id=777, content="Loved this take.", reference_id=1001,
        )
        with self._patch_set(return_value={
            "result_code": "done", "created": False, "replaced": True,
        }) as p:
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertTrue(out)
        # set_description was called with the URL + Jamie's reply verbatim.
        args, kwargs = p.call_args
        self.assertEqual(args[0], "http://x")
        self.assertEqual(args[1], "Loved this take.")
        self.assertEqual(kwargs["fallback_title"], "Some Title")
        m.add_reaction.assert_awaited_with("✅")

    def test_jamie_reply_to_popular_card_creates_bookmark_with_pin_emoji(self):
        db.record_research_message(
            discord_message_id="1002", url="http://y", source="popular",
            title="Popular Title",
        )
        m = self._msg(author_id=777, content="Bookmark with this take.", reference_id=1002)
        with self._patch_set(return_value={
            "result_code": "done", "created": True, "replaced": False,
        }):
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertTrue(out)
        # 📌 distinguishes "new bookmark created" from "existing one updated".
        m.add_reaction.assert_awaited_with("📌")

    def test_empty_reply_consumed_with_question_mark(self):
        db.record_research_message(
            discord_message_id="1003", url="http://x", source="toread",
        )
        m = self._msg(author_id=777, content="", reference_id=1003)
        with self._patch_set(return_value={"result_code": "done"}) as p:
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        # Consumed (so the LLM doesn't ALSO reply), reacted ❓, but
        # set_description was NOT called.
        self.assertTrue(out)
        p.assert_not_called()
        m.add_reaction.assert_awaited_with("❓")

    def test_set_description_failure_reacts_with_x(self):
        db.record_research_message(
            discord_message_id="1004", url="http://x", source="toread",
        )
        m = self._msg(author_id=777, content="text", reference_id=1004)
        with self._patch_set(side_effect=RuntimeError("boom")):
            out = asyncio.run(self.bot._maybe_handle_research_reply(m))
        self.assertTrue(out)
        m.add_reaction.assert_awaited_with("❌")
        m.reply.assert_awaited()


class LinkySaveReactionTests(_DBTestCase):
    """Owner reactions ✅/👍 on a popular-feed research card → save the
    URL to Pinboard as toread+public with a blank description."""

    def setUp(self):
        super().setUp()
        import types
        from apps.workshop_bot.personas.linky import LinkyBot
        self.bot = LinkyBot.__new__(LinkyBot)
        self.bot.user = MagicMock()
        self.bot.user.id = 1000
        self.bot.deps = types.SimpleNamespace(team=None, corpus=None)
        # Patch _react_card to capture the emoji we'd render onto the card
        # without going through discord fetch_channel / fetch_message.
        self.reactions: list[str] = []
        async def _fake_react(payload, emoji):
            self.reactions.append(emoji)
        self.bot._react_card = _fake_react
        os.environ["DISCORD_OWNER_USER_ID"] = "777"

    def tearDown(self):
        os.environ.pop("DISCORD_OWNER_USER_ID", None)
        super().tearDown()

    def _payload(self, *, user_id, emoji, message_id, channel_id=999):
        p = MagicMock()
        p.user_id = user_id
        p.message_id = message_id
        p.channel_id = channel_id
        p.emoji = MagicMock()
        p.emoji.__str__ = lambda s: emoji
        return p

    def _patch_pinboard(
        self, *, existing_posts=None, add_result=None, add_side_effect=None,
        get_side_effect=None,
    ):
        from apps.workshop_bot.systems.pinboard import client as pbc
        get_mock = MagicMock(return_value={"posts": existing_posts or []})
        if get_side_effect is not None:
            get_mock.side_effect = get_side_effect
        add_mock = MagicMock(return_value=add_result or {"result_code": "done"})
        if add_side_effect is not None:
            add_mock.side_effect = add_side_effect
        return (
            patch.object(pbc, "posts_get", get_mock),
            patch.object(pbc, "posts_add", add_mock),
            add_mock,
        )

    def test_save_reaction_on_popular_creates_bookmark(self):
        db.record_research_message(
            discord_message_id="2001", url="http://p/1", source="popular",
            title="Popular Title",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2001)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs["url"], "http://p/1")
        self.assertEqual(kwargs["description"], "")
        self.assertTrue(kwargs["toread"])
        self.assertTrue(kwargs["shared"])
        self.assertFalse(kwargs["replace"])
        self.assertEqual(self.reactions, ["📌"])

    def test_thumbs_up_works_too(self):
        db.record_research_message(
            discord_message_id="2002", url="http://p/2", source="popular",
        )
        p = self._payload(user_id=777, emoji="👍", message_id=2002)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_called_once()
        self.assertEqual(self.reactions, ["📌"])

    def test_other_emoji_ignored(self):
        db.record_research_message(
            discord_message_id="2003", url="http://p/3", source="popular",
        )
        p = self._payload(user_id=777, emoji="❤️", message_id=2003)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()
        self.assertEqual(self.reactions, [])

    def test_non_owner_reaction_ignored(self):
        db.record_research_message(
            discord_message_id="2004", url="http://p/4", source="popular",
        )
        p = self._payload(user_id=888, emoji="✅", message_id=2004)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()

    def test_toread_card_save_reaction_is_noop(self):
        # Toread URLs are already bookmarked — nothing to do.
        db.record_research_message(
            discord_message_id="2005", url="http://t/1", source="toread",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2005)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()
        self.assertEqual(self.reactions, [])  # no acknowledgment either

    def test_unknown_message_id_ignored(self):
        p = self._payload(user_id=777, emoji="✅", message_id=999999)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()

    def test_already_bookmarked_just_acknowledges(self):
        db.record_research_message(
            discord_message_id="2006", url="http://p/6", source="popular",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2006)
        # posts_get returns an existing bookmark; posts_add should NOT be called.
        get_p, add_p, add_mock = self._patch_pinboard(
            existing_posts=[{"href": "http://p/6"}],
        )
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        add_mock.assert_not_called()
        self.assertEqual(self.reactions, ["📌"])

    def test_posts_add_failure_reacts_with_x(self):
        db.record_research_message(
            discord_message_id="2007", url="http://p/7", source="popular",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2007)
        get_p, add_p, _ = self._patch_pinboard(
            add_side_effect=RuntimeError("boom"),
        )
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        self.assertEqual(self.reactions, ["❌"])

    def test_save_reaction_on_hackernews_card_creates_bookmark(self):
        db.record_research_message(
            discord_message_id="2009", url="https://x.example/hn-link",
            source="hackernews", title="An HN Story",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2009)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        # HN items behave just like Pinboard popular and Lobsters for save.
        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs["url"], "https://x.example/hn-link")
        self.assertEqual(kwargs["title"], "An HN Story")
        self.assertTrue(kwargs["toread"])
        self.assertTrue(kwargs["shared"])
        self.assertEqual(self.reactions, ["📌"])

    def test_save_reaction_on_lobsters_card_creates_bookmark(self):
        db.record_research_message(
            discord_message_id="2008", url="https://kde.org/news",
            source="lobsters", title="KDE Funding",
        )
        p = self._payload(user_id=777, emoji="✅", message_id=2008)
        get_p, add_p, add_mock = self._patch_pinboard()
        get_p.start(); add_p.start()
        try:
            asyncio.run(self.bot.on_raw_reaction_add(p))
        finally:
            add_p.stop(); get_p.stop()
        # Lobsters items behave just like Pinboard popular for the save flow.
        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs["url"], "https://kde.org/news")
        self.assertEqual(kwargs["title"], "KDE Funding")
        self.assertTrue(kwargs["toread"])
        self.assertTrue(kwargs["shared"])
        self.assertEqual(self.reactions, ["📌"])


if __name__ == "__main__":
    unittest.main()
