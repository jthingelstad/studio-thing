"""Tests for tools/journal_images.py — rehosting micro.blog journal photos."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import alt_text, s3 # noqa: E402
from apps.workshop_bot.tools.content import journal_images


def _tiny_png_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1200, 800), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _tiny_jpeg_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1800, 2969), (200, 100, 50)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _fake_get(body: bytes, content_type: str = "image/jpeg"):
    resp = MagicMock()
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()
    resp.iter_content = lambda n: iter([body])
    return resp


class ShouldRehostTests(unittest.TestCase):
    def test_blog_upload_image_yes(self):
        self.assertTrue(journal_images._should_rehost("https://www.thingelstad.com/uploads/2026/428e3db12e.jpg"))
        self.assertTrue(journal_images._should_rehost("https://cdn.uploads.micro.blog/123/abc.png"))

    def test_non_blog_image_no(self):
        self.assertFalse(journal_images._should_rehost("https://example.com/photo.jpg"))
        self.assertFalse(journal_images._should_rehost("https://m.media-amazon.com/images/x.jpg"))

    def test_already_local_no(self):
        self.assertFalse(journal_images._should_rehost("https://files.thingelstad.com/weekly-thing/458/journal/x.jpg"))

    def test_non_image_url_no(self):
        self.assertFalse(journal_images._should_rehost("https://www.thingelstad.com/2026/05/12/a.html"))

    def test_thingelstad_non_uploads_path_no(self):
        # An image on Jamie's domain but not under /uploads/ is site chrome.
        self.assertFalse(journal_images._should_rehost("https://www.thingelstad.com/img/logo.png"))


class LocalNameTests(unittest.TestCase):
    def test_reuses_microblog_hash_basename(self):
        self.assertEqual(
            journal_images._local_name("https://www.thingelstad.com/uploads/2026/428e3db12e.jpg"),
            "428e3db12e.jpg",
        )

    def test_normalizes_jpeg_to_jpg(self):
        self.assertEqual(
            journal_images._local_name("https://www.thingelstad.com/uploads/2026/abc.jpeg"),
            "abc.jpg",
        )

    def test_hashes_unsafe_basename(self):
        name = journal_images._local_name("https://www.thingelstad.com/uploads/2026/some weird name!.png")
        self.assertRegex(name, r"^[0-9a-f]{10}\.png$")


class ResizeTests(unittest.TestCase):
    def test_downscales_jpeg(self):
        big = _tiny_jpeg_bytes()
        out, ext = journal_images._resize(big, ".jpg", 600)
        self.assertEqual(ext, ".jpg")
        self.assertLess(len(out), len(big))
        from PIL import Image
        self.assertEqual(max(Image.open(io.BytesIO(out)).size), 600)

    def test_downscales_png(self):
        big = _tiny_png_bytes()
        out, ext = journal_images._resize(big, ".png", 400)
        self.assertEqual(ext, ".png")
        from PIL import Image
        self.assertEqual(max(Image.open(io.BytesIO(out)).size), 400)

    def test_non_resizable_format_passthrough(self):
        out, ext = journal_images._resize(b"GIF89a...not really", ".gif", 600)
        self.assertEqual((out, ext), (b"GIF89a...not really", ".gif"))


class RehostInMarkdownTests(unittest.TestCase):
    def setUp(self):
        # Stub the alt-fill pass so tests don't reach Anthropic. Tests that
        # care about the alt-fill behaviour patch this themselves.
        self._alt_patch = patch.object(alt_text, "get_or_generate_alt", return_value="")
        self._alt_patch.start()
        # Reset the per-run cap so each test starts fresh.
        alt_text.begin_run()

    def tearDown(self):
        self._alt_patch.stop()

    def test_img_tag_rehosted_emits_native_img(self):
        md = ('Got a card.\n\n'
              '<img src="https://www.thingelstad.com/uploads/2026/428e3db12e.jpg" width="363" height="600" alt="my card">')
        write_mock = MagicMock(side_effect=lambda issue, name, body, content_type=None: {
            "url": f"https://files.thingelstad.com/weekly-thing/{issue}/journal/{name}",
            "size": len(body), "content_type": "image/jpeg"})
        with patch.object(s3, "journal_image_exists", lambda issue, name: False), \
             patch.object(journal_images.requests, "get", return_value=_fake_get(_tiny_jpeg_bytes())), \
             patch.object(s3, "write_journal_image", write_mock):
            out = journal_images.rehost_in_markdown(md, 458)
        # Native <img> form (NOT markdown ![]()) — explicit alt attribute slot.
        self.assertNotIn("![my card](", out)
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/journal/428e3db12e.jpg"',
            out,
        )
        self.assertIn('alt="my card"', out)
        # Source-side width/height attrs are DROPPED — they carry the
        # original upload dimensions and would lie post-resize, breaking
        # aspect ratio in clients that honour HTML attrs over CSS.
        # Responsive sizing is handled by the email CSS instead.
        self.assertNotIn("width=", out)
        self.assertNotIn("height=", out)
        self.assertIn("Got a card.", out)
        # Uploaded under the micro.blog hash basename.
        self.assertEqual(write_mock.call_args.args[1], "428e3db12e.jpg")

    def test_already_in_workspace_skips_download(self):
        md = '<img src="https://www.thingelstad.com/uploads/2026/abc.jpg" alt="">'
        with patch.object(s3, "journal_image_exists", lambda issue, name: True), \
             patch.object(s3, "journal_image_url",
                          lambda issue, name: f"https://files.thingelstad.com/weekly-thing/{issue}/journal/{name}"), \
             patch.object(journal_images.requests, "get") as g, \
             patch.object(s3, "write_journal_image") as w:
            out = journal_images.rehost_in_markdown(md, 458)
        g.assert_not_called()
        w.assert_not_called()
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/journal/abc.jpg"',
            out,
        )
        # alt-fill stubbed → empty alt remains.
        self.assertIn('alt=""', out)

    def test_markdown_image_rewritten_to_img_tag(self):
        md = "Here: ![alt text](https://www.thingelstad.com/uploads/2026/q1.png)"
        with patch.object(s3, "journal_image_exists", lambda i, n: True), \
             patch.object(s3, "journal_image_url", lambda i, n: f"https://files.thingelstad.com/weekly-thing/{i}/journal/{n}"):
            out = journal_images.rehost_in_markdown(md, 458)
        # Markdown source → native <img> output with the alt preserved.
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/journal/q1.png"',
            out,
        )
        self.assertIn('alt="alt text"', out)
        self.assertNotIn("![alt text](", out)

    def test_non_blog_image_url_left_alone(self):
        md = '![](https://m.media-amazon.com/images/x.jpg) and <img src="https://example.com/y.png">'
        out = journal_images.rehost_in_markdown(md, 458)
        # Both URLs preserved verbatim, normalized to <img> form.
        self.assertIn('<img src="https://m.media-amazon.com/images/x.jpg"', out)
        self.assertIn('<img src="https://example.com/y.png"', out)

    def test_rehost_failure_leaves_original_url(self):
        md = '<img src="https://www.thingelstad.com/uploads/2026/z.jpg" alt="">'
        with patch.object(s3, "journal_image_exists", lambda i, n: False), \
             patch.object(journal_images.requests, "get", side_effect=RuntimeError("network down")):
            out = journal_images.rehost_in_markdown(md, 458)
        self.assertIn('<img src="https://www.thingelstad.com/uploads/2026/z.jpg"', out)

    def test_adjacent_imgs_separated_by_blank_line(self):
        md = ('Race day!\n\n'
              '<img src="https://www.thingelstad.com/uploads/2026/a814739f8a.jpg" width="600" height="450" alt="">'
              '<img src="https://www.thingelstad.com/uploads/2026/08388e7462.jpg" width="600" height="450" alt="">')
        with patch.object(s3, "journal_image_exists", lambda i, n: True), \
             patch.object(s3, "journal_image_url", lambda i, n: f"https://files.thingelstad.com/weekly-thing/{i}/journal/{n}"):
            out = journal_images.rehost_in_markdown(md, 458)
        # Two <img> tags on separate paragraphs, not run together.
        self.assertNotIn("/><img", out)
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/journal/a814739f8a.jpg"',
            out,
        )
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/journal/08388e7462.jpg"',
            out,
        )
        # Verify they ended up in separate paragraphs.
        self.assertIn(
            '08388e7462.jpg"',
            out.split('a814739f8a.jpg"', 1)[1].split("\n\n", 1)[1],
        )
        self.assertTrue(out.startswith("Race day!\n\n"))

    def test_no_images_passthrough(self):
        md = "Just text with a [link](http://x.example) and no images."
        self.assertEqual(journal_images.rehost_in_markdown(md, 458), md)

    def test_alt_fill_runs_on_rehosted_empty_alt(self):
        md = '<img src="https://www.thingelstad.com/uploads/2026/abc.jpg" alt="">'
        seen = {}
        def _fake_alt(*, image_key, image_url, context="", caption=None):
            seen.update(image_key=image_key, image_url=image_url, context=context)
            return "A photo of a creek running fast over rocks"
        with patch.object(s3, "journal_image_exists", lambda i, n: True), \
             patch.object(s3, "journal_image_url",
                          lambda i, n: f"https://files.thingelstad.com/weekly-thing/{i}/journal/{n}"), \
             patch.object(alt_text, "get_or_generate_alt", side_effect=_fake_alt):
            out = journal_images.rehost_in_markdown(md, 458)
        self.assertEqual(seen["image_key"], "abc.jpg")  # content-addressed
        self.assertEqual(seen["image_url"],
                         "https://files.thingelstad.com/weekly-thing/458/journal/abc.jpg")
        self.assertIn('alt="A photo of a creek running fast over rocks"', out)

    def test_alt_fill_skipped_when_alt_already_present(self):
        md = '<img src="https://www.thingelstad.com/uploads/2026/abc.jpg" alt="already set">'
        called = MagicMock()
        with patch.object(s3, "journal_image_exists", lambda i, n: True), \
             patch.object(s3, "journal_image_url",
                          lambda i, n: f"https://files.thingelstad.com/weekly-thing/{i}/journal/{n}"), \
             patch.object(alt_text, "get_or_generate_alt", called):
            out = journal_images.rehost_in_markdown(md, 458)
        called.assert_not_called()
        self.assertIn('alt="already set"', out)

    def test_alt_fill_skipped_for_non_rehosted_url(self):
        md = '<img src="https://example.com/x.png">'
        called = MagicMock()
        with patch.object(alt_text, "get_or_generate_alt", called):
            out = journal_images.rehost_in_markdown(md, 458)
        # External URL → no alt-fill (we don't have the bytes locally).
        called.assert_not_called()
        self.assertIn('<img src="https://example.com/x.png"', out)


if __name__ == "__main__":
    unittest.main()
