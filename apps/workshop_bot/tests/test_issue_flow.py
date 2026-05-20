"""Tests for the issue-assembly flow: start_issue, update_draft, issue_status,
DraftSectionStatus, EddyReviewTests, DraftReviewTests. Extracted from
``test_content_jobs.py`` in Item 1 of the project-integrity follow-up
sweep. Shared fixtures come from ``tests/_fixtures.py``."""

from __future__ import annotations

import asyncio
import json
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

from apps.workshop_bot.jobs import _base, issue_status, start_issue, update_draft  # noqa: E402
from apps.workshop_bot.tools import db, s3  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
    FakeWorkspace,
    patch_s3 as _patch_s3,
)


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
        # currently_json is intentionally absent — Currently moved to workshop.db.
        for key in ("cover_jpg", "cover_json", "intro_md",
                    "haiku_md", "metadata_json", "draft_md", "draft_html",
                    "final_md", "buttondown_md", "buttondown_html"):
            self.assertTrue(ptr["files"][key].startswith("https://files.thingelstad.com/weekly-thing/458/"), key)
        self.assertNotIn("currently_json", ptr["files"])
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

    def test_start_issue_schedules_mon_and_wed_currently_nudges(self):
        # Saturday far in the future so both Mon + Wed are future-due.
        result = asyncio.run(start_issue.run(
            _base.JobContext(), number=458, pub_date="2099-05-23",
        ))
        self.assertTrue(result.ok, result.message)
        # Two follow-up rows: persona=eddy, time-based, due_at Mon 17:00 and Wed 17:00 in CT.
        rows = db.open_follow_ups(persona="eddy")
        self.assertEqual(len(rows), 2)
        due_dates = sorted(r["due_at"] for r in rows)
        self.assertEqual(due_dates, ["2099-05-18T17:00:00", "2099-05-20T17:00:00"])
        for r in rows:
            self.assertEqual(r["trigger_kind"], "time")
            self.assertIn("WT458", r["note"])
        # The success message surfaces the schedule.
        self.assertIn("Currently nudges scheduled", result.message)
        self.assertEqual(set(result.data["currently_nudges"]),
                         {r["id"] for r in rows})

    def test_start_issue_skips_past_currently_nudges(self):
        # Pub date in the past — both Mon (pub-5) and Wed (pub-3) are past;
        # the scheduler should insert nothing.
        result = asyncio.run(start_issue.run(
            _base.JobContext(), number=459, pub_date="2020-01-04",
        ))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(db.open_follow_ups(persona="eddy"), [])
        self.assertEqual(result.data["currently_nudges"], [])
        self.assertNotIn("Currently nudges scheduled", result.message)


# ---------- update-draft ----------


class UpdateDraftTests(_DBTestCase):
    def _set_window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools.content import issue as issue_mod
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
        from apps.workshop_bot.tools.content import issue as issue_mod
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
        # haiku.md / metadata.json / cover.jpg missing → ❌ markers.
        # final.md is no longer a tracked asset; archive.md / buttondown.md
        # are now in the daily-rendered triplet line.
        self.assertIn("❌ `haiku.md`", result.message)
        self.assertIn("❌ `metadata.json`", result.message)
        self.assertIn("cta-1.md", result.message)
        st = result.data["section_status"]
        self.assertEqual(st["issue_number"], 458)
        self.assertEqual(st["cta_files"], ["cta-1.md"])
        self.assertFalse(st["ship_ready"])


# ---------- Step 4: real fills + section_status + context + Eddy review ----------

from datetime import date, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from apps.workshop_bot.tools.content import context, draft as draft_mod, microblog
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
        files = {"haiku.md", "metadata.json", "intro.md", "cover.jpg", "draft.md"}
        st = draft_mod.section_status(458, draft_text=d, list_objects=files)
        self.assertTrue(st["ship_ready"], st["required_missing"])



class UpdateDraftRealFillsTests(_DBTestCase):
    def _set_window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools.content import issue as issue_mod
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
        # Journal now day-grouped: entries appear beneath a per-day H3
        # sub-header with time-only labels.
        self.assertIn("### Tuesday, May 12", d)
        self.assertIn("[3:02 PM](https://www.thingelstad.com/2026/05/12/post-a.html)", d)
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

    def test_draft_html_carries_full_generation_timestamp(self):
        # The shareable preview's banner must include a full timestamp
        # (date + time + timezone) so anyone opening the link can tell
        # whether they're looking at a fresh projection or a stale one.
        self._set_window()
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        html = self.ws.files[(458, "draft.html")]
        import re
        # Subtitle reads: "DRAFT · WT458 · generated 2026-MM-DD HH:MM TZ · …"
        self.assertRegex(
            html,
            r"generated \d{4}-\d{2}-\d{2} \d{2}:\d{2} [A-Z]{2,5}",
        )

    def test_run_posts_deterministic_status_to_editorial(self):
        # Every `update-draft` run posts the readiness checklist to
        # #editorial — a guaranteed daily snapshot independent of Eddy's
        # LLM availability or PASS behaviour.
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "12345"
        try:
            self._set_window()
            fake_channel = MagicMock()
            fake_channel.send = AsyncMock()
            fake_eddy = MagicMock()
            fake_eddy.user = object()
            fake_eddy.get_channel = MagicMock(return_value=fake_channel)
            fake_eddy.core = AsyncMock(return_value=("PASS", {"iterations": 1}))
            team = MagicMock(); team.bots = {"eddy": fake_eddy}
            deps = MagicMock(); deps.team = team
            ctx = _base.JobContext(deps=deps)
            result = asyncio.run(update_draft.run(ctx))
            self.assertTrue(result.ok, result.message)
            # Even with Eddy returning PASS, the deterministic status card
            # landed in #editorial.
            fake_channel.send.assert_awaited()
            sent = fake_channel.send.call_args.args[0]
            self.assertIn("WT458", sent)
            self.assertIn("issue status", sent)
            self.assertIn("Required for ship", sent)
        finally:
            os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)

    def test_currently_entries_render_into_the_draft(self):
        self._set_window()
        # DB-backed: seed two entries directly. The renderer reads from
        # currently_entries (joined with currently_types), not S3.
        db.currently_set_entry(458, "Listening", "Noah Kahan.")
        db.currently_set_entry(458, "Watching", "Shrinking on Apple TV.")
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        d = self.ws.files[(458, "draft.md")]
        self.assertIn("**Listening:** Noah Kahan.\n\n**Watching:** Shrinking on Apple TV.", d)
        self.assertIn("## Currently", d)

    def test_no_currently_entries_leaves_block_empty(self):
        self._set_window()
        # No DB entries seeded; legacy currently.md in S3 is intentionally
        # ignored after the DB-backed renderer migration.
        self.ws.write_issue_file(458, "currently.md", "**Reading:** ignored legacy.")
        result = asyncio.run(update_draft.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        self.assertNotIn("Reading", self.ws.files[(458, "draft.md")])

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
        from apps.workshop_bot.tools.content import issue as issue_mod
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

    def test_review_runs_every_weekday(self):
        # Eddy no longer skips Sat/Sun/Mon — `update-draft` is the gate
        # (it refuses once final.md exists), so on every day it fires
        # Eddy should at least attempt a review. Pick Monday — the
        # weekday that used to silence him — and confirm he runs.
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "12345"
        try:
            window = self._window()
            deps, fake_eddy, fake_channel = self._fake_team_with_eddy()
            ctx = _base.JobContext(deps=deps)
            st = draft_mod.section_status(458, draft_text=_base.starter_template(), list_objects=set())
            out = asyncio.run(update_draft._maybe_eddy_review(ctx, window, st, None, date(2026, 5, 11)))
            self.assertIn("posted a review", out.lower())
            fake_eddy.core.assert_awaited()
            fake_channel.send.assert_awaited()
        finally:
            os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)

    def test_review_posts_on_review_day(self):
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "12345"
        try:
            window = self._window()
            deps, fake_eddy, fake_channel = self._fake_team_with_eddy()
            ctx = _base.JobContext(deps=deps)
            draft_text = _base.replace_block(
                _base.starter_template(),
                "currently",
                "**Reading:** A book about reliable systems.",
            )
            st = draft_mod.section_status(458, draft_text=draft_text, list_objects=set())
            out = asyncio.run(update_draft._maybe_eddy_review(ctx, window, st, None, date(2026, 5, 12)))  # Tuesday
            self.assertIn("posted a review", out.lower())
            fake_eddy.core.assert_awaited()
            fake_channel.send.assert_awaited()
            # The dynamic context block was prepended to the user message.
            sent_user_msg = fake_eddy.core.call_args.kwargs["latest"]
            self.assertIn("## Today", sent_user_msg)
            self.assertIn("active_issue", sent_user_msg)
            self.assertIn("currently_content", sent_user_msg)
            self.assertIn("A book about reliable systems", sent_user_msg)
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
        self.assertEqual(update_draft._review_model(6), "haiku")   # Sun
        self.assertEqual(update_draft._review_model(0), "haiku")   # Mon
        self.assertEqual(update_draft._review_model(1), "haiku")   # Tue
        self.assertEqual(update_draft._review_model(2), "haiku")   # Wed
        self.assertEqual(update_draft._review_model(3), "sonnet")  # Thu
        self.assertEqual(update_draft._review_model(4), "sonnet")  # Fri
        self.assertEqual(update_draft._review_model(5), "sonnet")  # Sat
        os.environ["WORKSHOP_EDDY_REVIEW_MODEL"] = "opus"
        try:
            self.assertEqual(update_draft._review_model(1), "opus")
        finally:
            os.environ.pop("WORKSHOP_EDDY_REVIEW_MODEL", None)



class DraftSectionStatusToolTests(_DBTestCase):
    def test_tool_returns_status_for_active_issue(self):
        from apps.workshop_bot.tools.content import issue as issue_mod
        from apps.workshop_bot.tools.llm import agent_tools
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
        from apps.workshop_bot.tools.llm import agent_tools
        registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(registry)
        out = registry.dispatch("draft__section_status", deps=None, args={}, persona="eddy")
        self.assertIn("error", out)



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
        # the late-pass hygiene lens or the drawer target markers.
        from apps.workshop_bot.tools.llm import anthropic_client
        # Clear the in-process cache so a parallel test that already loaded
        # the prompt doesn't shadow what's on disk right now.
        anthropic_client._prompt_cache.pop("eddy-draft-review", None)
        prompt = anthropic_client.load_prompt("eddy-draft-review")
        # Section headings + the distinguishing-lens framing.
        self.assertIn("## Hygiene", prompt)
        self.assertIn("## Drawer target markers", prompt)
        self.assertIn("<!-- target:n2 -->", prompt)
        self.assertIn("**Currently**", prompt)
        self.assertIn("target the `currently` section", prompt)
        # The most-load-bearing checks.
        for token in ("Anchor / heading hype", "Tonal lurch around links",
                      "Sales-talk in your own writing", "Alt-text",
                      "anchor/domain mismatch"):
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
