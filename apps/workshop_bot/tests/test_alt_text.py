"""Tests for tools/alt_text.py — vision-generated alt + cache."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import alt_text, db  # noqa: E402


def _fake_image_response(body: bytes = b"fakebytes", content_type: str = "image/jpeg"):
    resp = MagicMock()
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()
    resp.iter_content = lambda n: iter([body])
    return resp


def _fake_vision(text: str):
    """A `messages.create` response shaped like the Anthropic SDK's."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


class _AltTextDBTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()
        # Reset the per-run cap.
        os.environ.pop("WORKSHOP_ALT_VISION_CAP", None)
        alt_text.begin_run()

    def tearDown(self):
        if self._orig_db is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_db
        self._tmpdir.cleanup()


class CleanAltTests(unittest.TestCase):
    def test_strip_wrapping_quotes(self):
        self.assertEqual(alt_text._clean_alt('"A creek over rocks"'), "A creek over rocks")
        self.assertEqual(alt_text._clean_alt("'A creek over rocks'"), "A creek over rocks")

    def test_strip_alt_prefix(self):
        self.assertEqual(alt_text._clean_alt("Alt: a wide riverbed"), "a wide riverbed")
        self.assertEqual(alt_text._clean_alt("alt text: trail signs"), "trail signs")

    def test_strips_unsafe_attr_chars(self):
        # Quotes, ampersands, angle brackets — would break the alt attribute.
        self.assertEqual(
            alt_text._clean_alt('A "really" cool <thing> & a flag'),
            "A really cool thing and a flag",
        )

    def test_collapses_whitespace(self):
        self.assertEqual(
            alt_text._clean_alt("A long\n\n  line   with\textra space"),
            "A long line with extra space",
        )

    def test_empty_passes_through(self):
        self.assertEqual(alt_text._clean_alt(""), "")
        self.assertEqual(alt_text._clean_alt("   "), "")


class GetOrGenerateAltTests(_AltTextDBTestCase):
    def test_cache_hit_skips_vision(self):
        db.cache_alt(image_key="abc.jpg", alt="cached alt", source="vision")
        client = MagicMock()
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get") as g:
            out = alt_text.get_or_generate_alt(
                image_key="abc.jpg",
                image_url="https://files.thingelstad.com/weekly-thing/458/journal/abc.jpg",
            )
        self.assertEqual(out, "cached alt")
        client.messages.create.assert_not_called()
        g.assert_not_called()

    def test_cache_miss_calls_vision_and_persists(self):
        client = MagicMock()
        client.messages.create.return_value = _fake_vision("Minnehaha Creek rushing over rocks below the falls")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            out = alt_text.get_or_generate_alt(
                image_key="abc.jpg",
                image_url="https://files.thingelstad.com/weekly-thing/458/journal/abc.jpg",
                context="A walk at the falls today.",
            )
        self.assertEqual(out, "Minnehaha Creek rushing over rocks below the falls")
        # Persisted to the cache.
        self.assertEqual(db.get_cached_alt("abc.jpg"),
                         "Minnehaha Creek rushing over rocks below the falls")
        # The vision call included an image block.
        kwargs = client.messages.create.call_args.kwargs
        msg = kwargs["messages"][0]
        content = msg["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["type"], "base64")
        self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")

    def test_cap_exhaustion_returns_empty(self):
        # Cap of 1 — first call uses it, second returns empty.
        os.environ["WORKSHOP_ALT_VISION_CAP"] = "1"
        alt_text.begin_run()
        client = MagicMock()
        client.messages.create.return_value = _fake_vision("first alt")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            first = alt_text.get_or_generate_alt(
                image_key="a.jpg",
                image_url="https://files.thingelstad.com/weekly-thing/458/journal/a.jpg",
            )
            second = alt_text.get_or_generate_alt(
                image_key="b.jpg",
                image_url="https://files.thingelstad.com/weekly-thing/458/journal/b.jpg",
            )
        self.assertEqual(first, "first alt")
        self.assertEqual(second, "")
        # Only one vision call total.
        self.assertEqual(client.messages.create.call_count, 1)
        # Second key wasn't cached (we don't cache empty).
        self.assertIsNone(db.get_cached_alt("b.jpg"))

    def test_fetch_failure_returns_empty(self):
        client = MagicMock()
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", side_effect=RuntimeError("network")):
            out = alt_text.get_or_generate_alt(
                image_key="x.jpg",
                image_url="https://files.thingelstad.com/weekly-thing/458/journal/x.jpg",
            )
        self.assertEqual(out, "")
        client.messages.create.assert_not_called()
        # Nothing cached on failure.
        self.assertIsNone(db.get_cached_alt("x.jpg"))

    def test_vision_failure_returns_empty(self):
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("API down")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            out = alt_text.get_or_generate_alt(
                image_key="x.jpg",
                image_url="https://files.thingelstad.com/weekly-thing/458/journal/x.jpg",
            )
        self.assertEqual(out, "")
        self.assertIsNone(db.get_cached_alt("x.jpg"))

    def test_set_manual_alt_caches_as_manual(self):
        alt_text.set_manual_alt(image_key="cover-458", alt="A creek below the falls")
        self.assertEqual(db.get_cached_alt("cover-458"), "A creek below the falls")
        # Subsequent get_or_generate is a cache hit; no vision call.
        client = MagicMock()
        with patch.object(alt_text.anthropic_client, "client", return_value=client):
            out = alt_text.get_or_generate_alt(
                image_key="cover-458",
                image_url="https://files.thingelstad.com/weekly-thing/458/cover.jpg",
            )
        self.assertEqual(out, "A creek below the falls")
        client.messages.create.assert_not_called()

    def test_caption_is_forbidden_from_duplication(self):
        # The prompt mentions the caption verbatim so the model can avoid
        # duplicating it.
        client = MagicMock()
        client.messages.create.return_value = _fake_vision("Just the alt")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            alt_text.get_or_generate_alt(
                image_key="cover-458",
                image_url="https://files.thingelstad.com/weekly-thing/458/cover.jpg",
                caption="Minnehaha Creek rushing toward the Mississippi.",
            )
        msg = client.messages.create.call_args.kwargs["messages"][0]
        text_block = msg["content"][1]["text"]
        self.assertIn("Minnehaha Creek rushing toward the Mississippi.", text_block)
        self.assertIn("Do NOT repeat this caption", text_block)


if __name__ == "__main__":
    unittest.main()
