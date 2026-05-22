"""Tests for tools/alt_text.py — vision-generated alt (no cache)."""

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

from apps.workshop_bot.tools import alt_text  # noqa: E402


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


class _AltTextCapResetCase(unittest.TestCase):
    def setUp(self):
        os.environ.pop("WORKSHOP_ALT_VISION_CAP", None)
        alt_text.begin_run()


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


class GenerateAltTests(_AltTextCapResetCase):
    def test_returns_cleaned_alt_on_success(self):
        client = MagicMock()
        client.messages.create.return_value = _fake_vision(
            "Minnehaha Creek rushing over rocks below the falls"
        )
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            out = alt_text.generate_alt(
                image_url="https://www.thingelstad.com/uploads/2026/abc.jpg",
                context="A walk at the falls today.",
            )
        self.assertEqual(out, "Minnehaha Creek rushing over rocks below the falls")
        # The vision call included an image block.
        kwargs = client.messages.create.call_args.kwargs
        msg = kwargs["messages"][0]
        content = msg["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["type"], "base64")
        self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")

    def test_cap_exhaustion_returns_empty(self):
        os.environ["WORKSHOP_ALT_VISION_CAP"] = "1"
        alt_text.begin_run()
        client = MagicMock()
        client.messages.create.return_value = _fake_vision("first alt")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            first = alt_text.generate_alt(image_url="https://x/a.jpg")
            second = alt_text.generate_alt(image_url="https://x/b.jpg")
        self.assertEqual(first, "first alt")
        self.assertEqual(second, "")
        self.assertEqual(client.messages.create.call_count, 1)

    def test_fetch_failure_returns_empty(self):
        client = MagicMock()
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", side_effect=RuntimeError("network")):
            out = alt_text.generate_alt(image_url="https://x/y.jpg")
        self.assertEqual(out, "")
        client.messages.create.assert_not_called()

    def test_vision_failure_returns_empty(self):
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("API down")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            out = alt_text.generate_alt(image_url="https://x/y.jpg")
        self.assertEqual(out, "")

    def test_empty_image_url_returns_empty_no_call(self):
        client = MagicMock()
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get") as g:
            out = alt_text.generate_alt(image_url="")
        self.assertEqual(out, "")
        client.messages.create.assert_not_called()
        g.assert_not_called()

    def test_caption_is_forbidden_from_duplication(self):
        # The prompt mentions the caption verbatim so the model can avoid
        # duplicating it.
        client = MagicMock()
        client.messages.create.return_value = _fake_vision("Just the alt")
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_image_response()):
            alt_text.generate_alt(
                image_url="https://files.thingelstad.com/weekly-thing/458/cover.jpg",
                caption="Minnehaha Creek rushing toward the Mississippi.",
            )
        msg = client.messages.create.call_args.kwargs["messages"][0]
        text_block = msg["content"][1]["text"]
        self.assertIn("Minnehaha Creek rushing toward the Mississippi.", text_block)
        self.assertIn("Do NOT repeat this caption", text_block)


if __name__ == "__main__":
    unittest.main()
