"""microblog.update_post_content + source_for_url — Micropub update path."""

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

from apps.workshop_bot.tools.content import microblog  # noqa: E402


class _ApiKeyCase(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_key = os.environ.get("MICROBLOG_API_KEY")
        os.environ["MICROBLOG_API_KEY"] = "test-token"

    def tearDown(self) -> None:
        if self._orig_key is None:
            os.environ.pop("MICROBLOG_API_KEY", None)
        else:
            os.environ["MICROBLOG_API_KEY"] = self._orig_key


class SourceForUrlTests(_ApiKeyCase):
    def test_returns_properties_dict(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "type": ["h-entry"],
            "properties": {
                "url": ["https://micro.example/2026/05/22/post.html"],
                "content": ["original body"],
                "category": ["Featured"],
            },
        }
        resp.raise_for_status = MagicMock()
        with patch(
            "apps.workshop_bot.tools.content.microblog.requests.get",
            return_value=resp,
        ) as mock_get:
            props = microblog.source_for_url("https://micro.example/2026/05/22/post.html")
        self.assertEqual(props["content"], ["original body"])
        self.assertEqual(props["category"], ["Featured"])
        # GET ?q=source&url=… with bearer auth.
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["q"], "source")
        self.assertEqual(kwargs["params"]["url"], "https://micro.example/2026/05/22/post.html")
        self.assertIn("Bearer test-token", kwargs["headers"]["Authorization"])

    def test_requires_api_key(self):
        os.environ.pop("MICROBLOG_API_KEY", None)
        with self.assertRaisesRegex(RuntimeError, "MICROBLOG_API_KEY"):
            microblog.source_for_url("https://micro.example/p.html")

    def test_raises_when_properties_missing(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"type": ["h-entry"]}  # no properties
        resp.raise_for_status = MagicMock()
        with patch(
            "apps.workshop_bot.tools.content.microblog.requests.get",
            return_value=resp,
        ):
            with self.assertRaisesRegex(ValueError, "no properties"):
                microblog.source_for_url("https://micro.example/p.html")


class UpdatePostContentTests(_ApiKeyCase):
    def test_sends_micropub_update_payload(self):
        resp = MagicMock()
        resp.status_code = 200
        with patch(
            "apps.workshop_bot.tools.content.microblog.requests.post",
            return_value=resp,
        ) as mock_post:
            microblog.update_post_content(
                "https://micro.example/2026/05/22/post.html",
                "new body with alt",
            )
        _, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["json"],
            {
                "action": "update",
                "url": "https://micro.example/2026/05/22/post.html",
                "replace": {"content": ["new body with alt"]},
            },
        )
        self.assertIn("Bearer test-token", kwargs["headers"]["Authorization"])
        self.assertEqual(
            kwargs["headers"]["Content-Type"],
            "application/json",
        )

    def test_raises_on_http_error(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "boom"
        with patch(
            "apps.workshop_bot.tools.content.microblog.requests.post",
            return_value=resp,
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                microblog.update_post_content("https://micro.example/p.html", "x")

    def test_requires_api_key(self):
        os.environ.pop("MICROBLOG_API_KEY", None)
        with self.assertRaisesRegex(RuntimeError, "MICROBLOG_API_KEY"):
            microblog.update_post_content("https://micro.example/p.html", "x")

    def test_accepts_204_no_content(self):
        # micro.blog has historically returned 204 for update success.
        resp = MagicMock()
        resp.status_code = 204
        with patch(
            "apps.workshop_bot.tools.content.microblog.requests.post",
            return_value=resp,
        ):
            microblog.update_post_content("https://micro.example/p.html", "x")


class FillMissingAltsTests(_ApiKeyCase):
    def _patched_update(self):
        """Patch update_post_content so tests don't hit the network. Returns
        the MagicMock so callers can inspect call_args."""
        return patch(
            "apps.workshop_bot.tools.content.microblog.update_post_content",
            MagicMock(return_value=None),
        )

    def test_fills_html_img_empty_alt_and_writes_back(self):
        posts = [
            {
                "url": "https://micro.example/2026/05/22/p.html",
                "title": "Race day",
                "content_md": (
                    "Race day!\n\n"
                    '<img src="https://www.thingelstad.com/uploads/2026/abc.jpg" alt="">'
                ),
            }
        ]
        vision = MagicMock(side_effect=lambda **kwargs: "Runners crossing the finish line at dusk")
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(len(filled), 1)
        self.assertEqual(filled[0]["post_url"], "https://micro.example/2026/05/22/p.html")
        self.assertEqual(filled[0]["post_title"], "Race day")
        self.assertEqual(filled[0]["image_src"], "https://www.thingelstad.com/uploads/2026/abc.jpg")
        self.assertIn("Runners crossing", filled[0]["alt"])
        # Post mutated in place.
        self.assertIn('alt="Runners crossing the finish line at dusk"', posts[0]["content_md"])
        # Vision call got the right context.
        vision.assert_called_once()
        _, kwargs = vision.call_args
        self.assertEqual(kwargs["image_url"], "https://www.thingelstad.com/uploads/2026/abc.jpg")
        self.assertEqual(kwargs["caption"], "Race day")
        # Wrote back once per post (not per image).
        mock_update.assert_called_once()
        write_url, write_body = mock_update.call_args.args
        self.assertEqual(write_url, "https://micro.example/2026/05/22/p.html")
        self.assertIn('alt="Runners crossing the finish line at dusk"', write_body)

    def test_fills_markdown_image_empty_alt(self):
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "",
                "content_md": "See ![](https://example.com/x.png) here.",
            }
        ]
        vision = MagicMock(return_value="a screenshot of a terminal")
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(len(filled), 1)
        self.assertIn(
            "![a screenshot of a terminal](https://example.com/x.png)", posts[0]["content_md"]
        )
        mock_update.assert_called_once()

    def test_skips_images_with_existing_alt(self):
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "x",
                "content_md": (
                    '<img src="https://example.com/a.jpg" alt="already set">\n'
                    "![also done](https://example.com/b.jpg)"
                ),
            }
        ]
        vision = MagicMock(return_value="should not be called")
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(filled, [])
        vision.assert_not_called()
        mock_update.assert_not_called()

    def test_does_not_write_back_when_vision_returns_empty(self):
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "x",
                "content_md": '<img src="https://example.com/a.jpg" alt="">',
            }
        ]
        vision = MagicMock(return_value="")  # cap exhausted / vision failed
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(filled, [])
        mock_update.assert_not_called()
        # Source unchanged.
        self.assertIn('alt=""', posts[0]["content_md"])

    def test_writes_back_once_per_post_with_multiple_images(self):
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "Gallery",
                "content_md": (
                    '<img src="https://example.com/a.jpg" alt="">'
                    '<img src="https://example.com/b.jpg" alt="">'
                ),
            }
        ]
        vision = MagicMock(side_effect=lambda *, image_url, **_: f"alt for {image_url[-5:]}")
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(len(filled), 2)
        mock_update.assert_called_once()
        # Order in `filled` matches reading order in the source (a then b).
        self.assertEqual(filled[0]["image_src"], "https://example.com/a.jpg")
        self.assertEqual(filled[1]["image_src"], "https://example.com/b.jpg")

    def test_writeback_failure_reverts_in_memory(self):
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "x",
                "content_md": '<img src="https://example.com/a.jpg" alt="">',
            }
        ]
        original_md = posts[0]["content_md"]
        vision = MagicMock(return_value="a generated alt")
        with patch(
            "apps.workshop_bot.tools.content.microblog.update_post_content",
            side_effect=RuntimeError("Micropub server 503"),
        ):
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        # Nothing reported as filled (write didn't persist).
        self.assertEqual(filled, [])
        # In-memory copy reverted so we don't render an alt that doesn't
        # actually exist on the live post — next sync will re-vision.
        self.assertEqual(posts[0]["content_md"], original_md)

    def test_write_back_false_does_not_call_micropub(self):
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "x",
                "content_md": '<img src="https://example.com/a.jpg" alt="">',
            }
        ]
        vision = MagicMock(return_value="alt")
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(
                posts,
                vision_call=vision,
                write_back=False,
            )
        mock_update.assert_not_called()
        self.assertEqual(len(filled), 1)
        # In-memory still updated so a caller can preview the result.
        self.assertIn('alt="alt"', posts[0]["content_md"])

    def test_apostrophe_in_existing_alt_treated_as_filled(self):
        # Regression: the old `["\']([^"\']*)["\']` regex captured up to
        # the first apostrophe, so alt="Hand holding a s'more …" looked
        # to fill_missing_alts like alt="Hand holding a s" (non-empty, no
        # action) but the broken truncation was real downstream. Verify
        # the quote-aware regex sees the full value AND classifies it as
        # filled (no vision, no write-back).
        posts = [
            {
                "url": "https://micro.example/p.html",
                "title": "S'mores",
                "content_md": (
                    '<img src="https://example.com/x.jpg" '
                    'alt="Hand holding a s\'more over a campfire">'
                ),
            }
        ]
        vision = MagicMock(return_value="should not be called")
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(filled, [])
        vision.assert_not_called()
        mock_update.assert_not_called()

    def test_post_without_url_or_content_skipped(self):
        posts = [
            {"url": "", "title": "x", "content_md": '<img src="a" alt="">'},
            {"url": "https://micro.example/p", "title": "y", "content_md": ""},
        ]
        vision = MagicMock()
        with self._patched_update() as mock_update:
            filled = microblog.fill_missing_alts(posts, vision_call=vision)
        self.assertEqual(filled, [])
        vision.assert_not_called()
        mock_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
