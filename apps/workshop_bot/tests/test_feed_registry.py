"""Invariants on the discovery-feed registry.

The registry is the single source of truth for "which feeds Linky pulls
from." These tests pin the data shape so a future spec edit can't
silently land an invalid configuration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs.pinboard_scan import DISCOVERY_FEEDS  # noqa: E402
from apps.workshop_bot.tools.feeds.feed_registry import FeedSpec, by_name  # noqa: E402


class RegistryInvariantsTests(unittest.TestCase):
    def test_at_least_one_feed_defined(self):
        self.assertGreater(len(DISCOVERY_FEEDS), 0)

    def test_every_entry_is_a_feedspec(self):
        for spec in DISCOVERY_FEEDS:
            self.assertIsInstance(spec, FeedSpec)

    def test_names_are_unique(self):
        names = [spec.name for spec in DISCOVERY_FEEDS]
        self.assertEqual(len(names), len(set(names)),
                         f"duplicate feed name in DISCOVERY_FEEDS: {names}")

    def test_primary_priorities_are_unique(self):
        priorities = [spec.primary_priority for spec in DISCOVERY_FEEDS]
        self.assertEqual(len(priorities), len(set(priorities)),
                         f"duplicate primary_priority — cross-source merge tie: {priorities}")

    def test_fetch_callable(self):
        for spec in DISCOVERY_FEEDS:
            self.assertTrue(callable(spec.fetch),
                            f"spec {spec.name!r} has non-callable fetch")

    def test_labels_are_non_empty(self):
        for spec in DISCOVERY_FEEDS:
            self.assertTrue(spec.label.strip(),
                            f"spec {spec.name!r} has empty label")

    def test_pin_label_is_empty_or_non_whitespace(self):
        for spec in DISCOVERY_FEEDS:
            if spec.pin_label:
                self.assertEqual(spec.pin_label, spec.pin_label.strip(),
                                 f"spec {spec.name!r} pin_label has whitespace")

    def test_per_scan_cap_positive(self):
        for spec in DISCOVERY_FEEDS:
            self.assertGreater(spec.per_scan_cap, 0,
                               f"spec {spec.name!r} has non-positive per_scan_cap")
            self.assertGreater(spec.feed_limit, 0,
                               f"spec {spec.name!r} has non-positive feed_limit")

    def test_toread_is_not_in_discovery_registry(self):
        # Toread is a separate lane with different mechanics; it should
        # never be in DISCOVERY_FEEDS.
        self.assertNotIn("toread", {s.name for s in DISCOVERY_FEEDS})

    def test_by_name_resolves_and_returns_none_for_unknown(self):
        # by_name is the canonical lookup helper.
        first = DISCOVERY_FEEDS[0]
        self.assertIs(by_name(DISCOVERY_FEEDS, first.name), first)
        self.assertIsNone(by_name(DISCOVERY_FEEDS, "toread"))
        self.assertIsNone(by_name(DISCOVERY_FEEDS, "no-such-feed"))


if __name__ == "__main__":
    unittest.main()
