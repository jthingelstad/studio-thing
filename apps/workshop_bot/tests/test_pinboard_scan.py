"""Linky ``pinboard-scan`` job tests + the new Pinboard client / server verbs.

Pulled out of ``test_content_jobs.py`` in Batch F of the project-
integrity sweep — the Pinboard cluster was ~1200 lines, the single
largest topic in the file. Imports the shared fixtures (in-memory S3
workspace + temp-DB base class) from ``tests/_fixtures.py``; adds
its own local ``_FakeLinkyTeam`` since that stub is Pinboard-specific.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, pinboard_scan  # noqa: E402
from apps.workshop_bot.tools import db, s3  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase as _DBTestCase, FakeWorkspace  # noqa: E402


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
        from apps.workshop_bot.tools.feeds import hackernews as hn_mod
        from apps.workshop_bot.tools.feeds import indieweb_news as iwn_mod
        from apps.workshop_bot.tools.feeds import lobsters as lob
        from apps.workshop_bot.tools.feeds import tildes as tldes_mod
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
        # The URL is stored in normalised dedup-key form (trailing slash
        # stripped). The card content rendered in Discord still uses
        # whatever URL the upstream item handed us; only the persisted
        # row in linky_research_messages is canonical.
        self.assertEqual(row["url"], "https://www.xda-developers.com/linux-gaming")
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

    def test_concurrent_run_is_blocked_by_job_lock(self):
        """A second `pinboard-scan` firing while the first is mid-run
        must bail with a friendly "already running" message — protects
        against manual `/workshop links scan` overlapping the cron
        fire. We simulate the first scan by acquiring the same job-key
        lock manually in the test."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team()
        patches = self._stub_sources()
        # Pre-acquire the lock so run() sees it as "already running."
        from apps.workshop_bot.jobs._base import job_lock
        try:
            for p in patches:
                p.start()
            try:
                with job_lock([f"job:{pinboard_scan.NAME}"], pinboard_scan.NAME):
                    result = asyncio.run(pinboard_scan.run(ctx))
            finally:
                for p in patches:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["posted"], 0)
        self.assertIn("already running", result.message)
        # Lock-held path doesn't even reach the LLM.
        team.linky.core.assert_not_awaited()

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

    def test_cross_source_uplift_uses_verdict_source_column(self):
        """The uplift block labels the original verdict's source via the
        ``verdict_source`` column on ``pinboard_popular_seen`` — not by
        inferring from the oldest sighting (which was the prior
        approach and could mis-label if the data ever diverged)."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/verdict-source"
        # Verdict was produced from HN; the *oldest* sighting in
        # `popular_seen_sightings` happens to be Lobsters (different
        # from the verdict source). The uplift block should still
        # label the SKIP source as "Hacker News", not "Lobsters".
        db.mark_popular_seen(
            [{"url": url, "title": "Verdict-Source Test"}],
            judged={url: (False, "off-topic")},
            verdict_source="hackernews",
        )
        # Sightings recorded out-of-order: Lobsters first, then HN.
        db.record_sighting(url=url, source="lobsters")
        db.record_sighting(url=url, source="hackernews")

        ctx, team = self._ctx_and_team(replies=["SKIP: still off-topic"])
        tildes_items = [{"url": url, "title": "Tildes title",
                         "discussion_url": "https://tildes.net/~tech/v"}]
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
        self.assertEqual(result.data["skip"], 1)
        sent = team.linky.core.call_args.kwargs["latest"]
        # Label is HN (the recorded verdict_source), not Lobsters
        # (the first sighting in history).
        self.assertIn("SKIP'd from Hacker News", sent)
        self.assertNotIn("SKIP'd from Lobsters", sent)

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

    def test_fragment_only_difference_dedups_across_scans(self):
        """Regression: HN's feed handed back the same article in two
        different URL forms on 2026-05-14 —
        ``.../one-line.html#fnref1`` at 15:06 and ``.../one-line.html``
        at 21:06. Two cards posted for the same piece. The dedup
        tables now normalise URLs via ``url_normalize.dedup_key``
        (which strips the fragment), so the second scan's lookup hits
        the first scan's row and the URL is silent-dropped (or
        classified as an uplift if a different feed surfaces it)."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url_first = "https://homewithinnowhere.com/posts/x.html#fnref1"
        url_second = "https://homewithinnowhere.com/posts/x.html"

        # Scan #1 — HN surfaces the URL with the fragment.
        ctx1, team1 = self._ctx_and_team(replies=[
            f"**[Piece]({url_first})** · [HN](https://hn/1)\n\n"
            "Body.\n\nNotable.\n\n📖 medium · `hackernews`"
        ])
        hn1 = [{"url": url_first, "title": "Piece",
                 "discussion_url": "https://hn/1"}]
        patches = self._stub_sources(hn=hn1)
        try:
            for p in patches:
                p.start()
            try:
                asyncio.run(pinboard_scan.run(ctx1))
            finally:
                for p in patches:
                    p.stop()
        finally:
            pass

        # Scan #2 — same article, no fragment, same feed. Should NOT
        # produce a fresh card (same-feed-repeat → silent drop).
        ctx2, team2 = self._ctx_and_team(replies=[])
        hn2 = [{"url": url_second, "title": "Piece",
                 "discussion_url": "https://hn/1"}]
        patches2 = self._stub_sources(hn=hn2)
        try:
            for p in patches2:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx2))
            finally:
                for p in patches2:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["posted"], 0)
        self.assertEqual(result.data.get("uplift", 0), 0)
        team2.linky.core.assert_not_awaited()

    def test_toread_card_writes_cross_lane_seen_tables(self):
        """Toread card-post should write both lanes' dedup tables. The
        URL ends up in ``pinboard_popular_seen`` with ``verdict_source=
        'toread'`` and in ``popular_seen_sightings`` as ``('url',
        'toread')`` — so a later discovery-feed surfacing of the same
        URL classifies as cross-source uplift, not as fresh."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://example.com/jamies-pick"
        ctx, team = self._ctx_and_team(replies=[
            f"**[Pick]({url})** · [pin](https://pinboard.in/b/xx)\n\n"
            "A solid argument.\n\nLikely Notable.\n\n📖 medium · `toread`"
        ])
        toread = [{
            "url": url, "title": "Pick", "description": "",
            "pinboard_url": "https://pinboard.in/b/xx",
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
        # All three dedup writes happen:
        # 1. pinboard_research_done (toread lane's original write)
        self.assertEqual(db.filter_unresearched_urls([url]), [])
        # 2. pinboard_popular_seen (the cross-lane addition)
        verdict = db.popular_verdict(url)
        self.assertIsNotNone(verdict, "popular_seen row missing for toread card")
        self.assertEqual(verdict["judged_interesting"], 1)
        self.assertEqual(verdict["verdict_source"], "toread")
        # 3. popular_seen_sightings (the cross-lane sighting)
        self.assertTrue(db.feed_has_seen(url=url, source="toread"))

    def test_discovery_card_writes_pinboard_research_done(self):
        """Discovery card-post should also write ``pinboard_research_done``
        so a later toread-lane fetch silent-drops the URL — closing the
        cross-lane gap where a Lobsters-cardified URL Jamie later adds
        to his toread queue would otherwise be re-researched."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/discovery-rd"
        ctx, team = self._ctx_and_team(replies=[
            f"**[Lobsters Pick]({url})** · [lobste.rs](https://lobste.rs/s/zz)\n\n"
            "A piece.\n\nNotable.\n\n📖 short · `lobsters`"
        ])
        lobs = [{"url": url, "title": "Lobsters Pick",
                  "discussion_url": "https://lobste.rs/s/zz"}]
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
        self.assertEqual(db.filter_unresearched_urls([url]), [])

    def test_toread_then_discovery_surfaces_as_uplift(self):
        """End-to-end: Jamie's toread pick gets cardified Monday; the
        same URL trends on Lobsters Wednesday. The Wednesday scan should
        classify as cross-source uplift (with ``verdict_source='toread'``
        in the uplift block), not as a fresh second card."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/early-pick"

        # Day 1: toread card posted.
        ctx1, team1 = self._ctx_and_team(replies=[
            f"**[Early]({url})** · [pin](https://pinboard.in/b/yy)\n\n"
            "Body.\n\nNotable.\n\n📖 medium · `toread`"
        ])
        toread = [{"url": url, "title": "Early", "description": "",
                    "pinboard_url": "https://pinboard.in/b/yy"}]
        patches = self._stub_sources(toread=toread)
        try:
            for p in patches:
                p.start()
            try:
                asyncio.run(pinboard_scan.run(ctx1))
            finally:
                for p in patches:
                    p.stop()
        finally:
            pass

        # Day 2 scan: same URL on Lobsters (and no longer in Jamie's
        # toread — researched). Expect uplift.
        ctx2, team2 = self._ctx_and_team(replies=[
            f"**[Caught up]({url})** · [lobste.rs](https://lobste.rs/s/y)\n\n"
            "Community catching up.\n\nFresh angle.\n\n📖 short · `lobsters`"
        ])
        lobs = [{"url": url, "title": "Caught up",
                  "discussion_url": "https://lobste.rs/s/y"}]
        patches2 = self._stub_sources(lobs=lobs)
        try:
            for p in patches2:
                p.start()
            try:
                result = asyncio.run(pinboard_scan.run(ctx2))
            finally:
                for p in patches2:
                    p.stop()
        finally:
            os.environ.pop("DISCORD_CHANNEL_RESEARCH", None)
        self.assertEqual(result.data["uplift"], 1)
        self.assertEqual(result.data["posted"], 1)
        # The uplift block in the Day 2 user message names "toread" as
        # the prior verdict source — which the prompt special-cases as
        # Jamie's own pick.
        sent = team2.linky.core.call_args.kwargs["latest"]
        self.assertIn("## Cross-source uplift", sent)
        # The previous verdict block labels toread as the verdict source.
        # (The prompt's label resolution for toread is whatever the
        # render code produces — assert on the substring, not the exact
        # display text, to keep the test resilient to label tweaks.)
        self.assertIn("toread", sent.lower())

    def test_discovery_then_toread_silently_drops(self):
        """Mirror of the uplift case: a URL Linky cardified from a
        discovery feed Monday, then Jamie added to his toread queue
        Tuesday. The Tuesday toread fetch should silent-drop it —
        ``pinboard_research_done`` was written by the discovery card-
        post, so ``toread_public_unresearched`` filters it out."""
        url = "https://x.example/already-cardified"

        # Pre-state: discovery card already posted (researched in both
        # tables thanks to the cross-lane write).
        db.mark_popular_seen([{"url": url, "title": "Already"}],
                              judged={url: (True, "card posted (lobsters)")},
                              verdict_source="lobsters")
        db.record_sighting(url=url, source="lobsters")
        db.mark_url_researched(url=url, title="Already", summary="…",
                                confidence="✦", fit_note="card posted (lobsters)")

        # `toread_public_unresearched` filters against
        # `pinboard_research_done`. Confirm the URL is filtered.
        self.assertEqual(db.filter_unresearched_urls([url]), [])

    def test_uplift_card_replies_to_original_card_message(self):
        """A cross-source uplift card should post as a Discord reply to
        the earliest card-message that surfaced the URL. Visually this
        clusters the trend under one root in ``#research``."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/uplift-thread"
        # Pre-state: an existing card-post recorded under a known
        # message id. ``record_research_message`` is the persistence
        # point ``_process_one`` writes to after a card-post.
        db.record_research_message(
            discord_message_id="500", url=url, source="hackernews",
            title="Original",
        )
        db.mark_popular_seen([{"url": url, "title": "Original"}],
                              judged={url: (True, "card posted (hackernews)")},
                              verdict_source="hackernews")
        db.record_sighting(url=url, source="hackernews")

        ctx, team = self._ctx_and_team(replies=[
            f"**[Trending]({url})** · [lobste.rs](https://lobste.rs/s/a)\n\n"
            "Caught up.\n\nNotable.\n\n📖 short · `lobsters`"
        ])
        lobs = [{"url": url, "title": "Trending",
                  "discussion_url": "https://lobste.rs/s/a"}]
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
        self.assertEqual(result.data["uplift"], 1)
        # channel.send was called with a ``reference`` kwarg pointing
        # at the original card's message id. ``_FakeLinkyTeam``'s
        # ``_fake_send`` records the call shape; pick it out of the
        # call args.
        call_kwargs = team.channel.send.await_args.kwargs
        ref = call_kwargs.get("reference")
        self.assertIsNotNone(ref, "uplift card was not posted as a reply")
        # The reference object resolved to int(500) for the original
        # message id. (discord.MessageReference exposes ``message_id``
        # but we only need to confirm the integer round-trip; the
        # ``_stubs`` MessageReference shape should expose the same.)
        self.assertEqual(int(getattr(ref, "message_id", -1)), 500)

    def test_fresh_discovery_card_is_not_a_reply(self):
        """The reply-threading is uplift-only. A normal fresh card has
        no original to thread under, so ``send_one`` is called without
        a reference."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/no-reply"
        ctx, team = self._ctx_and_team(replies=[
            f"**[Fresh]({url})** · [lobste.rs](https://lobste.rs/s/b)\n\n"
            "Body.\n\nNotable.\n\n📖 short · `lobsters`"
        ])
        lobs = [{"url": url, "title": "Fresh",
                  "discussion_url": "https://lobste.rs/s/b"}]
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
        call_kwargs = team.channel.send.await_args.kwargs
        self.assertIsNone(call_kwargs.get("reference"))

    def test_first_research_message_for_returns_earliest(self):
        """``first_research_message_for`` returns the smallest-id row for
        a URL — ``ORDER BY posted_at ASC, discord_message_id ASC``."""
        url = "https://x.example/many-cards"
        # Record three cards for the same URL, out of insertion order.
        db.record_research_message(
            discord_message_id="2000", url=url, source="toread", title="t",
        )
        db.record_research_message(
            discord_message_id="3000", url=url, source="lobsters", title="t",
        )
        db.record_research_message(
            discord_message_id="1000", url=url, source="popular", title="t",
        )
        # The earliest posted_at is whichever was inserted first; with
        # default ``CURRENT_TIMESTAMP``-tied semantics, the records are
        # ordered by insertion. Either way the test asserts a non-empty
        # value, and that ``None`` is returned for a URL we never carded.
        first = db.first_research_message_for(url)
        self.assertIn(first, {"1000", "2000", "3000"})
        self.assertIsNone(db.first_research_message_for("https://x.example/never"))

    def test_legacy_popular_seen_with_no_sightings_does_not_uplift(self):
        """Regression: a ``pinboard_popular_seen`` row written *before*
        the ``popular_seen_sightings`` table existed (or before the
        sightings co-write was deployed) used to falsely trigger an
        uplift card the next time the same feed surfaced the URL —
        because ``feed_has_seen`` returned False (no sighting), so the
        classifier thought "this is a new feed's first sighting of a
        URL another feed already knew about" → cross-source signal.

        Real-world example: ``https://sinceyouarrived.world/taken``
        produced THREE cards on 2026-05-14 (one of them via this path).
        Guard: if no sighting exists at all, no cross-source signal is
        supportable. Backfill a sighting for the current spec and
        silent-drop, same as the normal same-feed-repeat case."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/legacy-orphan"
        # popular_seen row exists; sightings table is EMPTY for this URL.
        db.mark_popular_seen([{"url": url, "title": "Orphan"}],
                              judged={url: (True, "card posted")})
        self.assertEqual(db.sightings_for(url), [])

        ctx, team = self._ctx_and_team(replies=[])
        popular = [{"url": url, "title": "Orphan"}]
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
        # No card, no uplift, no LLM call.
        self.assertEqual(result.data["posted"], 0)
        self.assertEqual(result.data.get("uplift", 0), 0)
        team.linky.core.assert_not_awaited()
        # Sighting backfilled so the next scan silent-drops via the
        # normal feed_has_seen path, not via this guard.
        self.assertTrue(db.feed_has_seen(url=url, source="popular"))

    def test_legacy_popular_seen_with_different_feeds_sightings_still_uplifts(self):
        """The legacy-row guard is narrow: it only short-circuits when
        the sightings table is EMPTY. If at least one sighting exists
        from a different feed, the cross-source signal is genuine and
        the URL should still produce an uplift card."""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/legit-cross-source"
        db.mark_popular_seen([{"url": url, "title": "Genuine"}],
                              judged={url: (True, "card posted")})
        # Sighting from a DIFFERENT feed.
        db.record_sighting(url=url, source="hackernews")

        ctx, team = self._ctx_and_team(replies=[
            "**[Genuine](https://x.example/legit-cross-source)**\n\nFit.\n\n📖 short · `lobsters`",
        ])
        lobs = [{"url": url, "title": "Genuine",
                  "discussion_url": "https://lobste.rs/s/yy"}]
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
        # Genuine cross-source uplift card.
        self.assertEqual(result.data["uplift"], 1)
        self.assertEqual(result.data["posted"], 1)

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

    # ---------- _record_sightings_for_item ----------

    def test_record_sightings_for_item_writes_primary_only_when_no_extras(self):
        item = {"_url": "https://x.example/a", "_source": "lobsters",
                "co_sources": [], "new_sightings": []}
        pinboard_scan._record_sightings_for_item(item, "lobsters")
        self.assertTrue(db.feed_has_seen(url="https://x.example/a", source="lobsters"))
        self.assertFalse(db.feed_has_seen(url="https://x.example/a", source="hackernews"))

    def test_record_sightings_for_item_writes_primary_plus_co_sources(self):
        item = {
            "_url": "https://x.example/b", "_source": "lobsters",
            "co_sources": [
                {"source": "hackernews", "discussion_url": "", "score": 0, "comment_count": 0},
                {"source": "tildes", "discussion_url": "", "score": 0, "comment_count": 0},
            ],
            "new_sightings": [],
        }
        pinboard_scan._record_sightings_for_item(item, "lobsters")
        for src in ("lobsters", "hackernews", "tildes"):
            self.assertTrue(
                db.feed_has_seen(url="https://x.example/b", source=src),
                f"sighting missing for {src}",
            )

    def test_record_sightings_for_item_writes_primary_plus_new_sightings(self):
        item = {
            "_url": "https://x.example/c", "_source": "tildes",
            "co_sources": [],
            "new_sightings": [
                {"source": "tildes", "discussion_url": "", "score": 0, "comment_count": 0},
                {"source": "indieweb_news", "discussion_url": "", "score": 0, "comment_count": 0},
            ],
        }
        pinboard_scan._record_sightings_for_item(item, "tildes")
        # primary + new_sightings; the primary's own entry in
        # new_sightings is deduplicated against the primary record.
        for src in ("tildes", "indieweb_news"):
            self.assertTrue(db.feed_has_seen(url="https://x.example/c", source=src))

    def test_record_sightings_for_item_is_idempotent(self):
        item = {"_url": "https://x.example/d", "_source": "popular",
                "co_sources": [], "new_sightings": []}
        pinboard_scan._record_sightings_for_item(item, "popular")
        pinboard_scan._record_sightings_for_item(item, "popular")
        # Two calls, one row.
        with db.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM popular_seen_sightings WHERE url = ?",
                ("https://x.example/d",),
            ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_record_sightings_for_item_no_url_is_noop(self):
        # Defensive: missing _url field shouldn't raise.
        pinboard_scan._record_sightings_for_item(
            {"co_sources": [], "new_sightings": []}, "popular",
        )

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

    def test_archive_resonance_omitted_when_corpus_is_none(self):
        """When the job's `ctx.deps.corpus` is None (a deployment with no
        corpus loaded yet) the resonance block is omitted entirely from
        the per-link `## The link` data section. (The prompt body itself
        legitimately mentions `## Archive resonance` in its workflow
        description, so we check only the link block — the bit appended
        after the prompt — to verify the data block is absent.)"""
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        ctx, team = self._ctx_and_team(replies=[
            "**[A](https://x/y)**\n\nA.\n\nB.\n\n📖 short · `lobsters`"
        ])
        # Override the auto-MagicMock corpus that _ctx_and_team produces.
        ctx.deps.corpus = None
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
        link_block = sent.rsplit("## The link", 1)[-1]
        self.assertNotIn("## Archive resonance", link_block)
        self.assertNotIn("no resonance", link_block)
        # And `corpus.search` was never called either — there's no corpus.
        # (No assertion needed since `ctx.deps.corpus is None`; the
        # `_render_archive_resonance` guard returns [] early.)

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


class PerLinkModelSelectionTests(_DBTestCase):
    """Discovery sources use Haiku (cheap throughput); toread items use
    Sonnet (Jamie's own picks, higher-fidelity write-ups warranted).
    Together with the HN score filter and the `issue_index` removal,
    this brings Linky's weekly cost from ~$65 toward ~$5."""

    def _ctx_and_team(self, replies=None):
        team = _FakeLinkyTeam(replies=replies)
        return _base.JobContext(deps=_deps_with_linky_team(team)), team

    def _stub_sources(self, **kw):
        return PinboardScanJobTests._stub_sources(self, **kw)

    def test_discovery_source_uses_haiku(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/discovery-haiku"
        ctx, team = self._ctx_and_team(replies=[
            f"**[T]({url})** · [lobste.rs](https://l/1)\n\nbody.\n\n📖 short · `lobsters`"
        ])
        lobs = [{"url": url, "title": "T", "discussion_url": "https://l/1"}]
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
        # linky.core was called with model="haiku" for the discovery item.
        self.assertEqual(team.linky.core.call_args.kwargs["model"], "haiku")

    def test_toread_source_keeps_sonnet(self):
        os.environ["DISCORD_CHANNEL_RESEARCH"] = "999"
        url = "https://x.example/toread-sonnet"
        ctx, team = self._ctx_and_team(replies=[
            f"**[T]({url})** · [pin](https://p/1)\n\nbody.\n\n📖 short · `toread`"
        ])
        toread = [{"url": url, "title": "T", "description": "",
                    "pinboard_url": "https://p/1"}]
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
        # Jamie's own picks stay on Sonnet.
        self.assertEqual(team.linky.core.call_args.kwargs["model"], "sonnet")


class ParseSignalTests(unittest.TestCase):
    """``_parse_signal`` classifies the per-link LLM response into
    ``card`` / ``skip`` / ``fail``. The prompt asks for the signal to
    be the entire response, but the model occasionally leads with a
    reasoning paragraph before the ``SKIP:`` line — when that happens
    we'd rather honour the signal than post the prose as a card."""

    def test_first_line_skip(self):
        self.assertEqual(
            pinboard_scan._parse_signal("SKIP: not Jamie's lane"),
            ("skip", "not Jamie's lane"),
        )

    def test_first_line_fetch_failed(self):
        self.assertEqual(
            pinboard_scan._parse_signal("FETCH_FAILED: 404"),
            ("fail", "404"),
        )

    def test_skip_after_reasoning_prose(self):
        """Regression: Linky led with a reasoning paragraph (`Low
        signal. 48 points...`) then put the SKIP at the end. The old
        parser only checked the first line and classified the response
        as a card; the reasoning got posted to ``#research``."""
        answer = (
            "Low signal. 48 points, 13 comments, and the article itself is\n"
            "just an OpenAI product announcement. Nothing here adds a new\n"
            "angle — it's a feature drop, not a take.\n"
            "\n"
            "SKIP: Minor Codex feature release; Jamie covered Codex in #340."
        )
        kind, payload = pinboard_scan._parse_signal(answer)
        self.assertEqual(kind, "skip")
        self.assertIn("Minor Codex feature release", payload)

    def test_fetch_failed_wins_over_skip_when_both_appear(self):
        # FETCH_FAILED is the safer route (URL retries next scan).
        # If the model writes both lines, prefer fail.
        answer = "FETCH_FAILED: 403\nSKIP: paywalled"
        self.assertEqual(pinboard_scan._parse_signal(answer)[0], "fail")

    def test_card_when_no_signal_present(self):
        answer = "**[Title](https://x)** · [HN](https://h)\n\nBody.\n\n📖 short · `hackernews`"
        kind, payload = pinboard_scan._parse_signal(answer)
        self.assertEqual(kind, "card")
        self.assertEqual(payload, answer)

    def test_empty_response_is_fail(self):
        self.assertEqual(pinboard_scan._parse_signal("")[0], "fail")
        self.assertEqual(pinboard_scan._parse_signal("   \n\n  ")[0], "fail")

    def test_case_insensitive(self):
        self.assertEqual(pinboard_scan._parse_signal("skip: lowercase")[0], "skip")
        self.assertEqual(pinboard_scan._parse_signal("Fetch_Failed: mixed")[0], "fail")


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

    def test_bookmark_blank_creates_when_not_bookmarked(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        captured = {}

        def fake_add(*, url, title, description, tags, toread, shared, replace):
            captured.update(dict(url=url, title=title, description=description,
                                 tags=tags, toread=toread, shared=shared, replace=replace))
            return {"result_code": "done", "pinboard_url": ""}

        with patch.object(pbc, "posts_get", lambda u: {"posts": []}), \
             patch.object(pbc, "posts_add", fake_add):
            out = pbc.bookmark_blank(
                "https://example.com/x", fallback_title="The Title",
            )
        self.assertTrue(out["created"])
        # Defaults: toread=yes, shared=yes, blank description, no tags.
        self.assertEqual(captured["title"], "The Title")
        self.assertEqual(captured["description"], "")
        self.assertEqual(captured["tags"], "")
        self.assertTrue(captured["toread"])
        self.assertTrue(captured["shared"])
        self.assertFalse(captured["replace"])

    def test_bookmark_blank_noop_when_already_bookmarked(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        existing = {"posts": [{"href": "https://example.com/x",
                                "description": "Existing Title",
                                "extended": "Jamie's prior commentary",
                                "tags": "ai", "shared": "yes", "toread": "yes"}]}
        add_mock = MagicMock()
        with patch.object(pbc, "posts_get", lambda u: existing), \
             patch.object(pbc, "posts_add", add_mock):
            out = pbc.bookmark_blank("https://example.com/x")
        # No posts_add call — we leave existing record alone.
        add_mock.assert_not_called()
        self.assertFalse(out["created"])
        self.assertEqual(out["result_code"], "item already exists")

    def test_tag_as_brief_merges_brief_into_existing_tags(self):
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
            out = pbc.tag_as_brief("https://example.com/x")
        self.assertEqual(out["result_code"], "done")
        self.assertFalse(out["created"])
        # `_brief` appended, existing tags preserved, ordering intact.
        self.assertEqual(set(captured["tags"].split()), {"ai", "web", "_brief"})
        # Everything else preserved.
        self.assertEqual(captured["title"], "Existing Title")
        self.assertEqual(captured["description"], "old commentary")
        self.assertTrue(captured["toread"])
        self.assertTrue(captured["shared"])
        self.assertTrue(captured["replace"])

    def test_tag_as_brief_idempotent_when_brief_already_present(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        captured = {}

        def fake_get(url):
            return {"posts": [{
                "href": url, "description": "X", "extended": "y",
                "tags": "ai _brief web", "shared": "yes", "toread": "no",
            }]}

        def fake_add(*, url, title, description, tags, toread, shared, replace):
            captured.update(tags=tags)
            return {"result_code": "done", "pinboard_url": ""}

        with patch.object(pbc, "posts_get", fake_get), patch.object(pbc, "posts_add", fake_add):
            pbc.tag_as_brief("https://example.com/x")
        # `_brief` already in tags — it's not duplicated.
        tags = captured["tags"].split()
        self.assertEqual(tags.count("_brief"), 1)

    def test_tag_as_brief_creates_when_not_bookmarked(self):
        from apps.workshop_bot.systems.pinboard import client as pbc
        captured = {}

        def fake_add(*, url, title, description, tags, toread, shared, replace):
            captured.update(dict(url=url, title=title, description=description,
                                 tags=tags, toread=toread, shared=shared, replace=replace))
            return {"result_code": "done", "pinboard_url": ""}

        with patch.object(pbc, "posts_get", lambda u: {"posts": []}), \
             patch.object(pbc, "posts_add", fake_add):
            out = pbc.tag_as_brief(
                "https://example.com/new", fallback_title="Article Title",
            )
        self.assertTrue(out["created"])
        # New bookmark gets toread=yes shared=yes, tags=_brief, empty description.
        self.assertEqual(captured["title"], "Article Title")
        self.assertEqual(captured["description"], "")
        self.assertEqual(captured["tags"], "_brief")
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


class EmbedSuppressionTests(unittest.TestCase):
    """The Discord card carries multiple URLs (article + 1+ discussion-
    thread links). We want only the *article* embed to render; every
    other URL gets wrapped in ``<…>`` so Discord skips its preview."""

    def test_discussion_link_gets_wrapped_article_stays_bare(self):
        card = (
            "**[Three things about RSS](https://example.com/rss)** · "
            "[lobste.rs](https://lobste.rs/s/abc)\n\n"
            "Concrete take on RSS readers."
        )
        out = pinboard_scan._suppress_non_article_embeds(card, "https://example.com/rss")
        # Article URL is unchanged (bare → embed fires).
        self.assertIn("[Three things about RSS](https://example.com/rss)", out)
        # Discussion link is wrapped.
        self.assertIn("[lobste.rs](<https://lobste.rs/s/abc>)", out)
        # No raw `[lobste.rs](https://...)` form remains.
        self.assertNotIn("[lobste.rs](https://lobste.rs", out)

    def test_multiple_discussion_links_all_wrapped(self):
        card = (
            "**[The Piece](https://example.com/x)** · "
            "[HN](https://news.ycombinator.com/item?id=1) · "
            "[tildes](https://tildes.net/~tech/abc)\n\n"
            "Cross-source signal."
        )
        out = pinboard_scan._suppress_non_article_embeds(card, "https://example.com/x")
        self.assertIn("[HN](<https://news.ycombinator.com/item?id=1>)", out)
        self.assertIn("[tildes](<https://tildes.net/~tech/abc>)", out)
        # Article stays bare.
        self.assertIn("[The Piece](https://example.com/x)", out)

    def test_bare_url_in_prose_gets_wrapped(self):
        card = (
            "**[Title](https://example.com/x)**\n\n"
            "Reminds me of https://other.example/y and the earlier piece."
        )
        out = pinboard_scan._suppress_non_article_embeds(card, "https://example.com/x")
        self.assertIn("<https://other.example/y>", out)
        # Article URL preserved.
        self.assertIn("[Title](https://example.com/x)", out)

    def test_already_wrapped_url_left_alone(self):
        card = (
            "**[Title](https://example.com/x)** · "
            "[lobste.rs](<https://lobste.rs/s/abc>)"
        )
        out = pinboard_scan._suppress_non_article_embeds(card, "https://example.com/x")
        # Already wrapped — no double-wrap.
        self.assertIn("[lobste.rs](<https://lobste.rs/s/abc>)", out)
        self.assertNotIn("<<https", out)
        self.assertNotIn(">>)", out)

    def test_article_url_bare_in_prose_stays_bare(self):
        # Edge case: model puts the article URL bare in prose. It should
        # stay bare so its embed fires (matches the markdown link's URL).
        card = (
            "**[Title](https://example.com/x)**\n\n"
            "See also https://example.com/x for the talk version."
        )
        out = pinboard_scan._suppress_non_article_embeds(card, "https://example.com/x")
        # The prose URL is left bare (matches article).
        self.assertIn("See also https://example.com/x ", out)
        self.assertNotIn("<https://example.com/x>", out)

    def test_no_article_url_returns_payload_unchanged(self):
        card = "**[Title](https://example.com/x)** · [pin](https://lobste.rs/s/abc)"
        self.assertEqual(
            pinboard_scan._suppress_non_article_embeds(card, ""),
            card,
        )


if __name__ == "__main__":
    unittest.main()


