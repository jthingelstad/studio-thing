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
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base  # noqa: E402

# Shared fixtures used by this file and the split-out per-topic test files.
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
)
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.content import context, microblog
from apps.workshop_bot.tools.discord import interaction

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
    """Section-shape coverage moved to test_issue_items_render.py; what
    stays here is the cross-cutting UTC→local conversion test (which
    asserts the renderer correctly localises micro.blog's UTC
    timestamps) and the haiku formatter."""

    def test_render_journal_converts_utc_published_to_local(self):
        # micro.blog emits `published` in UTC; the local-time conversion
        # must drive both the day H3 sub-header and the per-entry time.
        # 2026-05-12T02:21Z → 2026-05-11 21:21 CDT → Monday May 11, 9:21 PM.
        from apps.workshop_bot.tools import issue_items_render
        out = issue_items_render.render_journal([
            {"url": "https://www.thingelstad.com/2026/05/11/late.html",
             "title": "", "body_md": "Posted late.",
             "metadata": {"published": "2026-05-12T02:21:00Z"}},
        ])
        self.assertIn("### Monday, May 11", out)
        self.assertIn("[9:21 PM](https://www.thingelstad.com/2026/05/11/late.html) — Posted late.", out)
        self.assertNotIn("2:21 AM", out)
        self.assertNotIn("May 12", out)

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

class EddyContextTests(_DBTestCase):
    def test_counts_from_db_rows(self):
        from apps.workshop_bot.tools import issue_items
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        for i in range(3):
            issue_items.upsert_item(issue_number=458, section="notable",
                                    source="pinboard", source_id=f"n{i}", body_md="x")
        ctx = context.build_eddy_context(ref_date=date(2026, 5, 12))
        self.assertEqual(ctx["active_issue"], 458)
        self.assertEqual(ctx["sections"]["notable"]["item_count"], 3)
        # The delta vocabulary died with draft_digests (the DB is the draft;
        # there is no projection snapshot to diff).
        self.assertNotIn("delta_since_last_run", ctx)

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


class InteractionPrimitiveTests(unittest.TestCase):
    """The picker is button-based: post a view, the owner clicks a button, the
    callback resolves the awaiting coroutine. These drive the real path —
    capture the posted view, click a button, await the result."""

    @staticmethod
    def _click(view, custom_id, *, user_id="777"):
        btn = next(c for c in view.children if getattr(c, "custom_id", None) == custom_id)
        inter = MagicMock()
        inter.user = MagicMock()
        inter.user.id = user_id
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.response.send_message = AsyncMock()
        return btn.callback(inter)  # a coroutine

    async def _run(self, call, click_custom_id, *, user_id="777"):
        holder = {}

        async def _send(content, **kw):
            if kw.get("view") is not None:
                holder["view"] = kw["view"]
            m = MagicMock()
            m.id = 4242
            return m

        channel = MagicMock()
        channel.send = _send
        task = asyncio.create_task(call(channel))
        for _ in range(100):  # let it post + reach the wait
            if "view" in holder:
                break
            await asyncio.sleep(0)
        await self._click(holder["view"], click_custom_id, user_id=user_id)
        return await asyncio.wait_for(task, timeout=2)

    def test_await_choice_returns_index(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            out = asyncio.run(self._run(
                lambda ch: interaction.await_choice(MagicMock(), ch, ["a", "b", "c"], prompt="pick"),
                "pick:1",  # the "2" button → index 1
            ))
            self.assertEqual(out, 1)
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_choice_refresh(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            out = asyncio.run(self._run(
                lambda ch: interaction.await_choice(MagicMock(), ch, ["a", "b"], prompt="pick"),
                "pick:refresh",
            ))
            self.assertEqual(out, "refresh")
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_choice_non_owner_click_ignored(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            # A non-owner click doesn't resolve; the await times out → None.
            async def scenario():
                holder = {}

                async def _send(content, **kw):
                    if kw.get("view") is not None:
                        holder["view"] = kw["view"]
                    m = MagicMock()
                    m.id = 1
                    return m

                channel = MagicMock()
                channel.send = _send
                task = asyncio.create_task(
                    interaction.await_choice(MagicMock(), channel, ["a"], prompt="p", timeout=0.2)
                )
                for _ in range(100):
                    if "view" in holder:
                        break
                    await asyncio.sleep(0)
                await self._click(holder["view"], "pick:0", user_id="999")  # not the owner
                return await asyncio.wait_for(task, timeout=2)

            self.assertIsNone(asyncio.run(scenario()))
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_choice_no_owner(self):
        os.environ.pop("DISCORD_OWNER_USER_ID", None)
        channel = MagicMock()
        channel.send = AsyncMock()
        out = asyncio.run(interaction.await_choice(MagicMock(), channel, ["a"], prompt="pick"))
        self.assertIsNone(out)
        channel.send.assert_not_awaited()

    def test_await_choice_zero_options(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            channel = MagicMock()
            channel.send = AsyncMock()
            self.assertIsNone(asyncio.run(interaction.await_choice(MagicMock(), channel, [], prompt="p")))
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

    def test_await_approval(self):
        os.environ["DISCORD_OWNER_USER_ID"] = "777"
        try:
            yes = asyncio.run(self._run(
                lambda ch: interaction.await_approval(MagicMock(), ch, prompt="ok?"), "pick:True"))
            self.assertIs(yes, True)
            no = asyncio.run(self._run(
                lambda ch: interaction.await_approval(MagicMock(), ch, prompt="ok?"), "pick:False"))
            self.assertIs(no, False)
        finally:
            os.environ.pop("DISCORD_OWNER_USER_ID", None)

