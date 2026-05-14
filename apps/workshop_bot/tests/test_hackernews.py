"""Tests for tools/hackernews.py — fetching + normalising HN front_page."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.feeds import hackernews  # noqa: E402


def _fake_get(hits):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"hits": hits})
    return resp


class TopTests(unittest.TestCase):
    def test_normalises_each_item(self):
        hits = [
            {
                "title": "Linux gaming is faster because Windows APIs are becoming Linux kernel features",
                "url": "https://www.xda-developers.com/linux-gaming/",
                "objectID": "48087887",
                "points": 412,
                "num_comments": 187,
                "author": "haunter",
                "created_at": "2026-05-14T01:23:45Z",
            },
        ]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top()
        self.assertEqual(len(out), 1)
        item = out[0]
        self.assertEqual(item["url"], "https://www.xda-developers.com/linux-gaming/")
        self.assertEqual(item["title"], "Linux gaming is faster because Windows APIs are becoming Linux kernel features")
        self.assertEqual(item["discussion_url"], "https://news.ycombinator.com/item?id=48087887")
        self.assertEqual(item["score"], 412)
        self.assertEqual(item["comment_count"], 187)
        self.assertEqual(item["submitter"], "haunter")

    def test_skips_ask_hn_without_url(self):
        # Ask HN / Show HN text posts have no `url` — they ARE the
        # discussion. Skip them; they aren't bookmarkable links.
        hits = [
            {"objectID": "1", "title": "Ask HN: …", "url": None, "points": 5},
            {"objectID": "2", "title": "Real link", "url": "https://x/y",
             "points": 100, "num_comments": 20, "author": "u"},
            {"objectID": "3", "title": "Show HN: …", "url": "", "points": 5},
        ]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top()
        self.assertEqual([i["url"] for i in out], ["https://x/y"])

    def test_honors_limit(self):
        hits = [
            {"objectID": str(i), "title": f"t{i}", "url": f"https://x.example/{i}"}
            for i in range(40)
        ]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top(limit=5)
        self.assertEqual(len(out), 5)

    def test_discussion_url_omitted_when_no_object_id(self):
        hits = [{"url": "https://x/y", "title": "t"}]  # no objectID
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top()
        self.assertEqual(out[0]["discussion_url"], "")

    def test_passes_front_page_tag(self):
        captured = {}

        def fake_get(url, *, params=None, **_kw):
            captured.update(url=url, params=params or {})
            return _fake_get([])

        with patch.object(hackernews.requests, "get", side_effect=fake_get):
            hackernews.top(limit=12)
        self.assertEqual(captured["url"], hackernews.SEARCH_URL)
        self.assertEqual(captured["params"]["tags"], "front_page")
        self.assertEqual(captured["params"]["hitsPerPage"], 12)

    def test_handles_empty_response(self):
        with patch.object(hackernews.requests, "get", return_value=_fake_get([])):
            self.assertEqual(hackernews.top(), [])

    def test_handles_missing_optional_fields(self):
        hits = [{"url": "https://x/y", "title": "t", "objectID": "9"}]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top()
        self.assertEqual(out, [{
            "url": "https://x/y",
            "title": "t",
            "discussion_url": "https://news.ycombinator.com/item?id=9",
            "score": 0,
            "comment_count": 0,
            "submitter": "",
        }])


if __name__ == "__main__":
    unittest.main()
