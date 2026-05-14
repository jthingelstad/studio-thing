"""Tests for tools/indieweb_news.py — IndieWeb News h-feed HTML parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.feeds import indieweb_news  # noqa: E402


def _page(*entry_html: str) -> str:
    return (
        "<!doctype html><html><body>"
        + "".join(entry_html)
        + "</body></html>"
    )


def _entry(*, title: str, article_url: str, iwn_path: str | None = None) -> str:
    iwn_link = (
        f'<a href="https://news.indieweb.org/en/{iwn_path}">→ IWN</a>'
        if iwn_path else ""
    )
    return f"""<div class="h-entry">
  <div class="title p-name"><a href="{article_url}" class="u-url">{title}</a></div>
  {iwn_link}
</div>"""


def _fake_get(body: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = body
    return resp


class IndieWebNewsTopTests(unittest.TestCase):
    def test_normalises_each_entry(self):
        body = _page(_entry(
            title="On likes, reposts, and bookmarks",
            article_url="https://robida.net/entries/2026/05/10/likes-reposts/",
            iwn_path="robida.net/entries/2026/05/10/likes-reposts/",
        ))
        with patch.object(indieweb_news.requests, "get", return_value=_fake_get(body)):
            out = indieweb_news.top()
        self.assertEqual(len(out), 1)
        item = out[0]
        self.assertEqual(item["url"], "https://robida.net/entries/2026/05/10/likes-reposts/")
        self.assertEqual(item["title"], "On likes, reposts, and bookmarks")
        self.assertEqual(
            item["discussion_url"],
            "https://news.indieweb.org/en/robida.net/entries/2026/05/10/likes-reposts/",
        )
        # IndieWeb News carries no scores / comments / submitter on the listing.
        self.assertEqual(item["score"], 0)
        self.assertEqual(item["comment_count"], 0)
        self.assertEqual(item["submitter"], "")
        self.assertEqual(item["tags"], [])

    def test_entry_without_iwn_link_still_includes_article(self):
        # Some listings don't carry a sibling `news.indieweb.org/en/...`
        # link; the article URL still works.
        body = _page(_entry(
            title="Article without an IWN sibling link",
            article_url="https://example.com/post",
        ))
        with patch.object(indieweb_news.requests, "get", return_value=_fake_get(body)):
            out = indieweb_news.top()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "https://example.com/post")
        self.assertEqual(out[0]["discussion_url"], "")

    def test_skips_entries_without_title_link(self):
        # An h-entry without a `.title.p-name a` is unusable.
        body = _page(
            '<div class="h-entry"><p>No title link.</p></div>',
            _entry(title="OK", article_url="https://x.example/y", iwn_path="x.example/y"),
        )
        with patch.object(indieweb_news.requests, "get", return_value=_fake_get(body)):
            out = indieweb_news.top()
        self.assertEqual([i["url"] for i in out], ["https://x.example/y"])

    def test_skips_entries_with_empty_href_or_title(self):
        body = _page(
            '<div class="h-entry"><div class="title p-name"><a href="">empty href</a></div></div>',
            '<div class="h-entry"><div class="title p-name"><a href="https://x/y"></a></div></div>',
            _entry(title="Good", article_url="https://good.example", iwn_path="good"),
        )
        with patch.object(indieweb_news.requests, "get", return_value=_fake_get(body)):
            out = indieweb_news.top()
        self.assertEqual([i["url"] for i in out], ["https://good.example"])

    def test_honors_limit(self):
        body = _page(*(
            _entry(title=f"Post {i}", article_url=f"https://x.example/{i}",
                   iwn_path=f"x.example/{i}")
            for i in range(30)
        ))
        with patch.object(indieweb_news.requests, "get", return_value=_fake_get(body)):
            out = indieweb_news.top(limit=4)
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0]["url"], "https://x.example/0")

    def test_handles_empty_page(self):
        body = _page()
        with patch.object(indieweb_news.requests, "get", return_value=_fake_get(body)):
            self.assertEqual(indieweb_news.top(), [])


if __name__ == "__main__":
    unittest.main()
