"""Tests for tools/alt_text.py — vision-generated alt (no cache)."""

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


class DownscaleForVisionTests(unittest.TestCase):
    """Resize-before-vision guards Anthropic's 5 MB base64 cap and cuts
    image tokens. Small images skip the PIL roundtrip; large ones get
    re-encoded as ≤1568px JPEG q85."""

    @staticmethod
    def _png_bytes(size_px: int) -> bytes:
        """Build a real PNG of size_px × size_px in memory (no fixture file)."""
        from io import BytesIO
        from PIL import Image
        img = Image.new("RGB", (size_px, size_px), color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_small_image_passes_through_unchanged(self):
        body = self._png_bytes(400)  # well under 1568px and < 3 MB
        out_body, out_media = alt_text._downscale_for_vision(body, "image/png")
        self.assertEqual(out_body, body)
        self.assertEqual(out_media, "image/png")

    def test_large_image_resized_and_recoded_as_jpeg(self):
        body = self._png_bytes(3000)  # exceeds 1568px long edge
        out_body, out_media = alt_text._downscale_for_vision(body, "image/png")
        self.assertLess(len(out_body), len(body))
        self.assertEqual(out_media, "image/jpeg")
        # Sanity: the resized image should fit comfortably under the API cap.
        approx_base64_size = (len(out_body) * 4 + 2) // 3
        self.assertLess(approx_base64_size, 5 * 1024 * 1024)
        # And the long edge should be at or under the documented sweet spot.
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(out_body)) as img:
            self.assertLessEqual(max(img.size), alt_text._VISION_LONG_EDGE_MAX)

    def test_bad_bytes_falls_back_to_original(self):
        body = b"this is not an image"
        out_body, out_media = alt_text._downscale_for_vision(body, "image/jpeg")
        self.assertEqual(out_body, body)
        self.assertEqual(out_media, "image/jpeg")


class FetchImageBytesTests(unittest.TestCase):
    """micro.blog's upload CDN serves some real images as ``binary/octet-stream``
    (or with no Content-Type at all). The fetch must trust the magic bytes, not
    just the header — otherwise real GIFs/PNGs/JPEGs are wrongly rejected, and
    each one still burns a vision-budget unit (the cap decrements before fetch)."""

    _PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    _JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    _GIF = b"GIF89a" + b"\x00" * 32

    def _fetch(self, body, content_type):
        with patch.object(alt_text.requests, "get",
                          return_value=_fake_image_response(body, content_type)):
            return alt_text._fetch_image_bytes("https://www.thingelstad.com/uploads/x")

    def test_octet_stream_png_accepted_via_sniff(self):
        self.assertEqual(self._fetch(self._PNG, "binary/octet-stream"), (self._PNG, "image/png"))

    def test_empty_content_type_jpeg_accepted_via_sniff(self):
        self.assertEqual(self._fetch(self._JPEG, ""), (self._JPEG, "image/jpeg"))

    def test_octet_stream_gif_accepted_via_sniff(self):
        self.assertEqual(self._fetch(self._GIF, "binary/octet-stream"), (self._GIF, "image/gif"))

    def test_proper_image_header_is_trusted(self):
        # A valid image/* header short-circuits the sniff and is returned as-is.
        self.assertEqual(self._fetch(b"anybytes", "image/webp"), (b"anybytes", "image/webp"))

    def test_non_image_octet_stream_rejected(self):
        # octet-stream whose bytes are NOT a known image → still rejected.
        self.assertIsNone(self._fetch(b"<html>not an image</html>", "binary/octet-stream"))


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


def _fake_404_response():
    """A response whose raise_for_status() raises a 404 HTTPError, shaped like
    requests' (carries .response.status_code)."""
    resp = MagicMock()
    err = alt_text.requests.HTTPError("404 Client Error: Not Found")
    err.response = MagicMock(status_code=404)
    resp.raise_for_status.side_effect = err
    resp.headers = {"Content-Type": "image/jpeg"}
    resp.iter_content = lambda n: iter([b"x"])
    return resp


class DeadUrlTests(unittest.TestCase):
    """Deleted uploads (404/410) must be recorded and skipped for free so a
    block of dead URLs can't re-block the backfill cursor or burn the budget."""

    def setUp(self):
        os.environ.pop("WORKSHOP_ALT_VISION_CAP", None)
        alt_text._dead_urls.clear()
        alt_text._dead_url_log = None
        alt_text.begin_run()

    def tearDown(self):
        alt_text._dead_urls.clear()
        alt_text._dead_url_log = None

    def test_404_records_dead_and_refunds_budget(self):
        client = MagicMock()
        before = alt_text.calls_remaining()
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get", return_value=_fake_404_response()):
            out = alt_text.generate_alt(image_url="https://x/gone.jpg")
        self.assertEqual(out, "")
        client.messages.create.assert_not_called()
        # The dead URL was recorded and its reserved budget unit refunded.
        self.assertIn("https://x/gone.jpg", alt_text._dead_urls)
        self.assertEqual(alt_text.calls_remaining(), before)

    def test_known_dead_url_skipped_for_free(self):
        alt_text._dead_urls.add("https://x/gone.jpg")
        client = MagicMock()
        before = alt_text.calls_remaining()
        with patch.object(alt_text.anthropic_client, "client", return_value=client), \
             patch.object(alt_text.requests, "get") as g:
            out = alt_text.generate_alt(image_url="https://x/gone.jpg")
        self.assertEqual(out, "")
        g.assert_not_called()                       # no fetch
        client.messages.create.assert_not_called()  # no vision call
        self.assertEqual(alt_text.calls_remaining(), before)  # no budget spent

    def test_dead_url_appended_to_log_and_reloaded(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "dead-urls.txt")
            alt_text.begin_run(dead_url_log=log)
            client = MagicMock()
            with patch.object(alt_text.anthropic_client, "client", return_value=client), \
                 patch.object(alt_text.requests, "get", return_value=_fake_404_response()):
                alt_text.generate_alt(image_url="https://x/gone.jpg")
            self.assertIn("https://x/gone.jpg", Path(log).read_text().splitlines())

            # A fresh run (cleared in-memory set) re-seeds from the log and skips.
            alt_text._dead_urls.clear()
            alt_text.begin_run(dead_url_log=log)
            self.assertIn("https://x/gone.jpg", alt_text._dead_urls)
            with patch.object(alt_text.anthropic_client, "client", return_value=client), \
                 patch.object(alt_text.requests, "get") as g:
                out = alt_text.generate_alt(image_url="https://x/gone.jpg")
            self.assertEqual(out, "")
            g.assert_not_called()


if __name__ == "__main__":
    unittest.main()
