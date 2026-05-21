"""Tests for ``tools.feedbin`` (RSS parsing) and
``jobs.feedbin_ingest`` (dedup + Pinboard mirror)."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, feedbin_ingest  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase  # noqa: E402
from apps.workshop_bot.tools import db, feedbin  # noqa: E402


_SAMPLE_FEED = ("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Starred Articles</title>
    <link>https://feedbin.com/</link>
    <item>
      <title>Item one</title>
      <description>First description</description>
      <link>https://example.test/one</link>
      <pubDate>Thu, 21 May 2026 05:47:02 +0000</pubDate>
      <dc:creator>Some Creator</dc:creator>
      <guid isPermaLink="false">https://feedbin.me/entries/100</guid>
    </item>
    <item>
      <title>Item two</title>
      <description><![CDATA[Has <em>HTML</em>]]></description>
      <link>https://example.test/two</link>
      <pubDate>Thu, 21 May 2026 04:00:00 +0000</pubDate>
      <dc:creator>Another</dc:creator>
      <guid isPermaLink="false">https://feedbin.me/entries/101</guid>
    </item>
    <item>
      <title>No guid item -- should be skipped</title>
      <link>https://example.test/three</link>
    </item>
    <item>
      <title>No link -- should be skipped</title>
      <guid isPermaLink="false">https://feedbin.me/entries/103</guid>
    </item>
  </channel>
</rss>
""").encode("utf-8")


class FeedbinParseTests(unittest.TestCase):
    def test_parse_extracts_two_items(self):
        items = feedbin.parse_feed(_SAMPLE_FEED)
        self.assertEqual(len(items), 2)
        first, second = items
        self.assertEqual(first["guid"], "https://feedbin.me/entries/100")
        self.assertEqual(first["url"], "https://example.test/one")
        self.assertEqual(first["title"], "Item one")
        self.assertEqual(first["description"], "First description")
        self.assertEqual(first["creator"], "Some Creator")
        self.assertIn("2026", first["pub_date"])
        self.assertEqual(second["guid"], "https://feedbin.me/entries/101")
        self.assertIn("HTML", second["description"])

    def test_parse_skips_items_without_guid_or_link(self):
        items = feedbin.parse_feed(_SAMPLE_FEED)
        guids = {i["guid"] for i in items}
        self.assertNotIn("https://feedbin.me/entries/103", guids)

    def test_parse_bad_xml_raises(self):
        with self.assertRaises(feedbin.FeedbinError):
            feedbin.parse_feed(b"<rss><not-closed>")

    def test_feed_url_reads_env(self):
        with patch.dict(os.environ, {"FEEDBIN_STARRED_FEED_URL": "https://x.test/foo.xml"}):
            self.assertEqual(feedbin.feed_url(), "https://x.test/foo.xml")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEEDBIN_STARRED_FEED_URL", None)
            self.assertIsNone(feedbin.feed_url())


class FeedbinIngestTests(DBTestCase):
    def setUp(self) -> None:
        super().setUp()
        os.environ["FEEDBIN_STARRED_FEED_URL"] = "https://feedbin.test/starred.xml"
        os.environ["PINBOARD_API_TOKEN"] = "user:HEX"

    def tearDown(self) -> None:
        os.environ.pop("FEEDBIN_STARRED_FEED_URL", None)
        os.environ.pop("PINBOARD_API_TOKEN", None)
        super().tearDown()

    def _run(self, items, *, posts_add_results=None, posts_add_side_effect=None):
        """Run the ingest with patched feedbin + pinboard."""
        ctx = _base.JobContext(trigger="manual")
        if posts_add_results is None:
            posts_add_mock = MagicMock(return_value={"result_code": "done", "pinboard_url": ""})
        else:
            posts_add_mock = MagicMock(side_effect=posts_add_results)
        if posts_add_side_effect is not None:
            posts_add_mock.side_effect = posts_add_side_effect
        with patch.object(feedbin, "fetch_starred", return_value=items), \
             patch("apps.workshop_bot.jobs.feedbin_ingest.pinboard_client.posts_add",
                   posts_add_mock):
            result = asyncio.run(feedbin_ingest.run(ctx))
        return result, posts_add_mock

    def test_first_run_creates_pinboard_bookmarks(self):
        items = feedbin.parse_feed(_SAMPLE_FEED)
        result, posts_add_mock = self._run(items)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["new"], 2)
        self.assertEqual(result.data["skipped"], 0)
        self.assertEqual(posts_add_mock.call_count, 2)

        # Both calls used toread=True, shared=True, replace=False, and an
        # empty description (Feedbin RSS <description> is intentionally
        # NOT carried over — Jamie writes his own commentary later).
        for call in posts_add_mock.call_args_list:
            kwargs = call.kwargs
            self.assertTrue(kwargs["toread"])
            self.assertTrue(kwargs["shared"])
            self.assertFalse(kwargs["replace"])
            self.assertEqual(kwargs["description"], "")

        # Both GUIDs filed locally.
        with patch("apps.workshop_bot.tools.db.feedbin_seen_guids", db.feedbin_seen_guids):
            seen = db.feedbin_seen_guids([
                "https://feedbin.me/entries/100",
                "https://feedbin.me/entries/101",
            ])
        self.assertEqual(seen, {
            "https://feedbin.me/entries/100",
            "https://feedbin.me/entries/101",
        })

    def test_second_run_is_silent_when_no_new_items(self):
        items = feedbin.parse_feed(_SAMPLE_FEED)
        self._run(items)  # first run files both
        # Second run with same items.
        result, posts_add_mock = self._run(items)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["new"], 0)
        self.assertEqual(result.data["skipped"], 2)
        posts_add_mock.assert_not_called()

    def test_partial_new_items(self):
        # Pre-seed one GUID; only the other should be sent to Pinboard.
        db.record_feedbin_seen(
            guid="https://feedbin.me/entries/100",
            url="https://example.test/one",
            title="Item one",
            pinboard_result="done",
        )
        items = feedbin.parse_feed(_SAMPLE_FEED)
        result, posts_add_mock = self._run(items)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["new"], 1)
        self.assertEqual(result.data["skipped"], 1)
        self.assertEqual(posts_add_mock.call_count, 1)
        # The one un-seeded GUID is the one that got sent.
        self.assertEqual(
            posts_add_mock.call_args.kwargs["url"], "https://example.test/two",
        )

    def test_pinboard_existing_item_counts_as_skipped(self):
        items = feedbin.parse_feed(_SAMPLE_FEED)
        # Pinboard responds with "item already exists" for one; we still
        # record the GUID locally so we don't keep retrying.
        result, posts_add_mock = self._run(items, posts_add_results=[
            {"result_code": "item already exists", "pinboard_url": ""},
            {"result_code": "done", "pinboard_url": ""},
        ])
        self.assertTrue(result.ok)
        self.assertEqual(result.data["new"], 1)
        self.assertEqual(result.data["skipped"], 1)
        # Both GUIDs are filed locally despite one being "already exists".
        seen = db.feedbin_seen_guids([
            "https://feedbin.me/entries/100",
            "https://feedbin.me/entries/101",
        ])
        self.assertEqual(len(seen), 2)

    def test_pinboard_exception_counts_as_error_but_continues(self):
        items = feedbin.parse_feed(_SAMPLE_FEED)
        result, posts_add_mock = self._run(items, posts_add_side_effect=[
            RuntimeError("boom"),
            {"result_code": "done", "pinboard_url": ""},
        ])
        self.assertTrue(result.ok)
        self.assertEqual(result.data["new"], 1)
        self.assertEqual(result.data["errors"], 1)
        # The errored item is NOT recorded — so the next run can retry it.
        seen = db.feedbin_seen_guids(["https://feedbin.me/entries/100"])
        self.assertEqual(seen, set())

    def test_skips_when_feed_url_unset(self):
        os.environ.pop("FEEDBIN_STARRED_FEED_URL", None)
        ctx = _base.JobContext(trigger="manual")
        result = asyncio.run(feedbin_ingest.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("FEEDBIN_STARRED_FEED_URL", result.message)

    def test_skips_when_pinboard_token_unset(self):
        os.environ.pop("PINBOARD_API_TOKEN", None)
        ctx = _base.JobContext(trigger="manual")
        result = asyncio.run(feedbin_ingest.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("PINBOARD_API_TOKEN", result.message)

    def test_feedbin_fetch_error_passes_cleanly(self):
        ctx = _base.JobContext(trigger="manual")
        with patch.object(
            feedbin, "fetch_starred",
            side_effect=feedbin.FeedbinError("HTTP 503"),
        ):
            result = asyncio.run(feedbin_ingest.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("HTTP 503", result.message)


if __name__ == "__main__":
    unittest.main()
