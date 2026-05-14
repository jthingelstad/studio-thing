"""Tests for tools/url_normalize.py — `dedup_key` for cross-source dedup."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.url_normalize import dedup_key  # noqa: E402


class DedupKeyTests(unittest.TestCase):
    def test_round_trip_on_clean_url(self):
        url = "https://example.com/article"
        self.assertEqual(dedup_key(url), url)

    def test_lowercases_host(self):
        self.assertEqual(
            dedup_key("https://Example.COM/article"),
            "https://example.com/article",
        )

    def test_strips_trailing_slash_from_path(self):
        self.assertEqual(
            dedup_key("https://example.com/article/"),
            "https://example.com/article",
        )

    def test_keeps_bare_domain_slash(self):
        # A bare-domain URL `https://example.com/` shouldn't become
        # `https://example.com` after stripping — leave the root slash.
        self.assertEqual(
            dedup_key("https://example.com/"),
            "https://example.com/",
        )

    def test_strips_utm_params(self):
        self.assertEqual(
            dedup_key("https://example.com/x?utm_source=hn&utm_medium=feed"),
            "https://example.com/x",
        )

    def test_strips_fbclid_gclid_mc_ref(self):
        self.assertEqual(
            dedup_key("https://example.com/x?fbclid=abc&gclid=def&mc_cid=ghi"),
            "https://example.com/x",
        )
        self.assertEqual(
            dedup_key("https://example.com/x?ref=hn&ref_src=other"),
            "https://example.com/x",
        )

    def test_preserves_non_tracking_query(self):
        self.assertEqual(
            dedup_key("https://example.com/search?q=keyword&page=2"),
            "https://example.com/search?q=keyword&page=2",
        )

    def test_mixed_tracking_and_real_params(self):
        # Only tracking params are dropped; real ones survive.
        self.assertEqual(
            dedup_key("https://example.com/x?id=42&utm_source=hn&page=3"),
            "https://example.com/x?id=42&page=3",
        )

    def test_strips_fragment(self):
        # Same article, two URL forms — one with a footnote anchor.
        # The fragment is a UI-only locator inside the same resource;
        # cross-scan dedup must collapse them. Regression: the
        # homewithinnowhere.com/posts/...one-line.html duplicate cards
        # on 2026-05-14 hit this case.
        self.assertEqual(
            dedup_key("https://example.com/x#section-2"),
            "https://example.com/x",
        )
        self.assertEqual(
            dedup_key("https://homewithinnowhere.com/posts/x.html#fnref1"),
            dedup_key("https://homewithinnowhere.com/posts/x.html"),
        )

    def test_collapses_cross_feed_duplicates(self):
        # The whole point: same article, two feeds, different tracking
        # params → identical key.
        a = dedup_key("https://example.com/article?utm_source=hn")
        b = dedup_key("https://example.com/article?ref=lobsters")
        self.assertEqual(a, b)
        self.assertEqual(a, "https://example.com/article")

    def test_empty_or_garbage_returns_empty_string(self):
        self.assertEqual(dedup_key(""), "")
        self.assertEqual(dedup_key("not a url"), "")
        self.assertEqual(dedup_key("file://local/x"), "file://local/x")  # scheme-only check

    def test_non_string_returns_empty(self):
        self.assertEqual(dedup_key(None), "")  # type: ignore[arg-type]
        self.assertEqual(dedup_key(123), "")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
