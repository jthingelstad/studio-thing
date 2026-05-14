"""Tests for tools/lobsters.py — fetching + normalising hottest.json."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import lobsters  # noqa: E402


def _fake_get(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


class HottestTests(unittest.TestCase):
    def test_normalises_each_item(self):
        payload = [
            {
                "short_id": "yyfjd1",
                "title": "Sovereign Tech Fund invests in KDE",
                "url": "https://kde.org/announcements/sovereign-tech-fund-invests-kde/",
                "score": 110,
                "comment_count": 15,
                "tags": ["linux"],
                "short_id_url": "https://lobste.rs/s/yyfjd1",
                "submitter_user": "zanlib",
            },
        ]
        with patch.object(lobsters.requests, "get", return_value=_fake_get(payload)):
            out = lobsters.hottest()
        self.assertEqual(len(out), 1)
        item = out[0]
        self.assertEqual(item["url"], "https://kde.org/announcements/sovereign-tech-fund-invests-kde/")
        self.assertEqual(item["title"], "Sovereign Tech Fund invests in KDE")
        self.assertEqual(item["discussion_url"], "https://lobste.rs/s/yyfjd1")
        self.assertEqual(item["tags"], ["linux"])
        self.assertEqual(item["score"], 110)
        self.assertEqual(item["comment_count"], 15)
        self.assertEqual(item["submitter"], "zanlib")

    def test_skips_items_without_url(self):
        payload = [
            {"url": "", "title": "no url"},
            {"title": "missing url field"},
            {"url": "https://x.example/y", "title": "good"},
        ]
        with patch.object(lobsters.requests, "get", return_value=_fake_get(payload)):
            out = lobsters.hottest()
        self.assertEqual([i["url"] for i in out], ["https://x.example/y"])

    def test_honors_limit(self):
        payload = [
            {"url": f"https://x.example/{i}", "title": f"t{i}"}
            for i in range(40)
        ]
        with patch.object(lobsters.requests, "get", return_value=_fake_get(payload)):
            out = lobsters.hottest(limit=5)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["url"], "https://x.example/0")

    def test_handles_empty_response(self):
        with patch.object(lobsters.requests, "get", return_value=_fake_get([])):
            out = lobsters.hottest()
        self.assertEqual(out, [])

    def test_handles_missing_optional_fields(self):
        # A minimal item — only url + title; lobsters might omit tags / score.
        payload = [{"url": "https://x/1", "title": "t"}]
        with patch.object(lobsters.requests, "get", return_value=_fake_get(payload)):
            out = lobsters.hottest()
        self.assertEqual(out, [{
            "url": "https://x/1",
            "title": "t",
            "discussion_url": "",
            "tags": [],
            "score": 0,
            "comment_count": 0,
            "submitter": "",
        }])


if __name__ == "__main__":
    unittest.main()
