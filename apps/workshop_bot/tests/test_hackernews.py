"""Tests for tools/hackernews.py — fetching + normalising HN front_page."""

from __future__ import annotations

import os
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
    def setUp(self):
        # The existing normalisation tests don't care about the score
        # filter; disable it via the env override so a missing/low
        # ``points`` in the fixture doesn't drop the item.
        self._orig = os.environ.get("WORKSHOP_HN_MIN_SCORE")
        os.environ["WORKSHOP_HN_MIN_SCORE"] = "0"

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_HN_MIN_SCORE", None)
        else:
            os.environ["WORKSHOP_HN_MIN_SCORE"] = self._orig
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
        # The fetcher requests at least 30 hits so the score filter has
        # room to drop items below the threshold without starving the
        # caller — the caller's ``limit`` still caps the returned set.
        self.assertGreaterEqual(captured["params"]["hitsPerPage"], 12)

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


class ScoreFilterTests(unittest.TestCase):
    """The score floor keeps the lower-third HN noise out of Linky's
    queue. Default is 100 points; tunable via WORKSHOP_HN_MIN_SCORE
    (so Jamie can dial it up or down without a redeploy)."""

    def setUp(self):
        self._orig = os.environ.get("WORKSHOP_HN_MIN_SCORE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_HN_MIN_SCORE", None)
        else:
            os.environ["WORKSHOP_HN_MIN_SCORE"] = self._orig

    def _hit(self, oid, score, url="https://x.example/y"):
        return {"objectID": str(oid), "title": f"t{oid}", "url": url,
                "points": score, "num_comments": 0, "author": "u"}

    def test_default_floor_is_100(self):
        os.environ.pop("WORKSHOP_HN_MIN_SCORE", None)
        hits = [self._hit(1, 250, "https://x/1"),
                self._hit(2, 99,  "https://x/2"),  # just below
                self._hit(3, 100, "https://x/3"),  # at floor
                self._hit(4, 5,   "https://x/4")]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top(limit=10)
        urls = [it["url"] for it in out]
        self.assertEqual(sorted(urls), ["https://x/1", "https://x/3"])

    def test_env_override_lowers_floor(self):
        os.environ["WORKSHOP_HN_MIN_SCORE"] = "50"
        hits = [self._hit(1, 75,  "https://x/1"),
                self._hit(2, 49,  "https://x/2"),
                self._hit(3, 200, "https://x/3")]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top(limit=10)
        self.assertEqual(sorted(it["url"] for it in out),
                          ["https://x/1", "https://x/3"])

    def test_env_override_disables_filter_at_zero(self):
        os.environ["WORKSHOP_HN_MIN_SCORE"] = "0"
        hits = [self._hit(1, 5, "https://x/1"),
                self._hit(2, 1, "https://x/2")]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top(limit=10)
        self.assertEqual(len(out), 2)

    def test_bad_env_value_falls_back_to_default(self):
        os.environ["WORKSHOP_HN_MIN_SCORE"] = "not-a-number"
        hits = [self._hit(1, 50, "https://x/1"),
                self._hit(2, 200, "https://x/2")]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top(limit=10)
        # Default 100 enforced.
        self.assertEqual([it["url"] for it in out], ["https://x/2"])

    def test_filter_runs_before_limit_so_high_scorers_aren_t_starved(self):
        """Filter drops below-threshold items first; the cap applies to
        the survivors. Otherwise a front page heavy on low-score items
        could starve the high-score ones below the cap."""
        os.environ["WORKSHOP_HN_MIN_SCORE"] = "100"
        # 5 low-score followed by 3 high-score. limit=3 should return
        # the 3 high-score, not run out after the 5 low-score drops.
        hits = [self._hit(i, 10, f"https://low/{i}") for i in range(5)]
        hits += [self._hit(100 + i, 500, f"https://high/{i}") for i in range(3)]
        with patch.object(hackernews.requests, "get", return_value=_fake_get(hits)):
            out = hackernews.top(limit=3)
        self.assertEqual(len(out), 3)
        for it in out:
            self.assertTrue(it["url"].startswith("https://high/"))


if __name__ == "__main__":
    unittest.main()
