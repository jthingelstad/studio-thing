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
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, update_draft  # noqa: E402
from apps.workshop_bot.tools import db, s3 # noqa: E402
from apps.workshop_bot.tools.content import context, microblog
from apps.workshop_bot.tools.discord import interaction

# Shared fixtures used by this file and the split-out per-topic test
# files (test_pinboard_scan.py, test_issue_flow.py, test_compose_jobs.py,
# test_build_publish.py, test_linky_reactions.py).
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeWorkspace,
    patch_s3 as _patch_s3,
)


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
    def test_delta_against_prior_digest(self):
        from apps.workshop_bot.tools.content import issue as issue_mod
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
        from apps.workshop_bot.tools.content import issue as issue_mod
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


class LinkyContextTests(_DBTestCase):
    def test_build_linky_context(self):
        from apps.workshop_bot.tools.content import issue as issue_mod, context
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
        from apps.workshop_bot.tools.content import context
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
        from apps.workshop_bot.tools.content import context
        self.assertTrue(context._is_no_publish_saturday(date(2026, 7, 4)))
        self.assertTrue(context._is_no_publish_saturday(date(2026, 8, 15)))
        self.assertTrue(context._is_no_publish_saturday(date(2026, 12, 20)))
        self.assertTrue(context._is_no_publish_saturday(date(2027, 1, 10)))
        self.assertFalse(context._is_no_publish_saturday(date(2026, 5, 16)))
        self.assertFalse(context._is_no_publish_saturday(date(2026, 12, 13)))

