"""Tests for the purpose-keyed Anthropic client factory.

Each call purpose (the five personas + "general") bills to its own API key so
the Anthropic console attributes spend per agent. The factory fails fast on an
unknown purpose or a missing key rather than silently sharing one key.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.llm import anthropic_client  # noqa: E402

_ALL_KEYS = {
    "ANTHROPIC_EDDY_API_KEY": "k-eddy",
    "ANTHROPIC_LINKY_API_KEY": "k-linky",
    "ANTHROPIC_MARKY_API_KEY": "k-marky",
    "ANTHROPIC_PATTY_API_KEY": "k-patty",
    "ANTHROPIC_SCOUT_API_KEY": "k-scout",
    "ANTHROPIC_GENERAL_API_KEY": "k-general",
}


class ClientFactoryTests(unittest.TestCase):
    def setUp(self):
        # The factory caches one client per purpose; clear it so each test
        # builds fresh against its own patched environment.
        anthropic_client._clients.clear()

    def test_client_caches_per_purpose(self):
        with mock.patch.dict(os.environ, _ALL_KEYS, clear=False):
            a = anthropic_client.client("eddy")
            b = anthropic_client.client("eddy")
            self.assertIs(a, b)
            self.assertIsNot(a, anthropic_client.client("linky"))

    def test_unknown_purpose_raises(self):
        with mock.patch.dict(os.environ, _ALL_KEYS, clear=False):
            with self.assertRaises(RuntimeError) as cm:
                anthropic_client.client("bogus")
        self.assertIn("bogus", str(cm.exception))

    def test_missing_key_raises_naming_the_env_var(self):
        env = dict(_ALL_KEYS)
        env.pop("ANTHROPIC_EDDY_API_KEY")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                anthropic_client.client("eddy")
        self.assertIn("ANTHROPIC_EDDY_API_KEY", str(cm.exception))

    def test_default_purpose_is_general(self):
        with mock.patch.dict(os.environ, _ALL_KEYS, clear=False):
            self.assertIs(anthropic_client.client(), anthropic_client.client("general"))


class ValidateKeysTests(unittest.TestCase):
    def test_passes_when_all_present(self):
        with mock.patch.dict(os.environ, _ALL_KEYS, clear=False):
            anthropic_client.validate_keys()  # should not raise

    def test_can_validate_only_enabled_purposes(self):
        env = {
            "ANTHROPIC_EDDY_API_KEY": "k-eddy",
            "ANTHROPIC_SCOUT_API_KEY": "k-scout",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            anthropic_client.validate_keys(purposes=["scout", "eddy"])  # should not raise

    def test_subset_validation_rejects_unknown_purpose(self):
        with mock.patch.dict(os.environ, _ALL_KEYS, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                anthropic_client.validate_keys(purposes=["scout", "bogus"])
        self.assertIn("bogus", str(cm.exception))

    def test_raises_listing_every_missing_key(self):
        env = dict(_ALL_KEYS)
        env.pop("ANTHROPIC_MARKY_API_KEY")
        env.pop("ANTHROPIC_PATTY_API_KEY")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                anthropic_client.validate_keys()
        msg = str(cm.exception)
        self.assertIn("ANTHROPIC_MARKY_API_KEY", msg)
        self.assertIn("ANTHROPIC_PATTY_API_KEY", msg)
        self.assertNotIn("ANTHROPIC_EDDY_API_KEY", msg)


if __name__ == "__main__":
    unittest.main()
