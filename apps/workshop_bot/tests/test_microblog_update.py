"""microblog.update_post_content + source_for_url — Micropub update path."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

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
        self.assertEqual(kwargs["json"], {
            "action": "update",
            "url": "https://micro.example/2026/05/22/post.html",
            "replace": {"content": ["new body with alt"]},
        })
        self.assertIn("Bearer test-token", kwargs["headers"]["Authorization"])
        self.assertEqual(
            kwargs["headers"]["Content-Type"], "application/json",
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


if __name__ == "__main__":
    unittest.main()
