"""Tests for tools/tildes.py — Tildes ~tech atom feed parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.feeds import tildes  # noqa: E402


def _atom_payload(entries: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>~tech</title>
{entries}
</feed>"""


def _link_entry(*, title: str, tildes_id: str, article_url: str, author: str = "tester") -> str:
    return f"""<entry>
  <id>{tildes_id}</id>
  <title>{title}</title>
  <author><name>{author}</name></author>
  <link rel="alternate" href="{tildes_id}" />
  <content type="html">&lt;p&gt;Check out &lt;a href="{article_url}"&gt;the article&lt;/a&gt;.&lt;/p&gt;</content>
</entry>"""


def _text_entry(*, title: str, tildes_id: str, body: str, author: str = "tester") -> str:
    return f"""<entry>
  <id>{tildes_id}</id>
  <title>{title}</title>
  <author><name>{author}</name></author>
  <link rel="alternate" href="{tildes_id}" />
  <content type="html">&lt;p&gt;{body}&lt;/p&gt;</content>
</entry>"""


def _fake_get(body: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = body
    return resp


class TildesTopTests(unittest.TestCase):
    def test_normalises_link_post(self):
        body = _atom_payload(_link_entry(
            title="Tiny robot drones learn to navigate like honeybees",
            tildes_id="https://tildes.net/~tech/1u6a/tiny_robot_drones",
            article_url="https://www.scientificamerican.com/article/tiny-robot-drones/",
            author="zanlib",
        ))
        with patch.object(tildes.requests, "get", return_value=_fake_get(body)):
            out = tildes.top()
        self.assertEqual(len(out), 1)
        item = out[0]
        self.assertEqual(item["url"], "https://www.scientificamerican.com/article/tiny-robot-drones/")
        self.assertEqual(item["title"], "Tiny robot drones learn to navigate like honeybees")
        self.assertEqual(item["discussion_url"], "https://tildes.net/~tech/1u6a/tiny_robot_drones")
        self.assertEqual(item["submitter"], "zanlib")
        # No vote/comment data on Tildes' atom feed.
        self.assertEqual(item["score"], 0)
        self.assertEqual(item["comment_count"], 0)
        self.assertEqual(item["tags"], [])

    def test_skips_text_posts(self):
        # Text post: only tildes.net hrefs (or none) in the content body.
        body = _atom_payload(
            _text_entry(
                title="Smartphone recommendations?",
                tildes_id="https://tildes.net/~tech/1u6d/smartphone_recommendations",
                body="I've been rocking a Sony Xperia 1 IV...",
            )
            + _link_entry(
                title="Real article",
                tildes_id="https://tildes.net/~tech/x/real",
                article_url="https://example.com/article",
            )
        )
        with patch.object(tildes.requests, "get", return_value=_fake_get(body)):
            out = tildes.top()
        self.assertEqual([i["url"] for i in out], ["https://example.com/article"])

    def test_skips_entries_with_only_tildes_internal_links(self):
        # Entry references another tildes.net post but no external URL.
        # Should still count as a text post (no bookmarkable article).
        body = _atom_payload(_text_entry(
            title="Discussion thread",
            tildes_id="https://tildes.net/~tech/x/disc",
            body='See &lt;a href="https://tildes.net/~tech/other"&gt;the other thread&lt;/a&gt;',
        ))
        with patch.object(tildes.requests, "get", return_value=_fake_get(body)):
            out = tildes.top()
        self.assertEqual(out, [])

    def test_picks_first_external_url_when_multiple(self):
        # If a link post's body references several external URLs, only
        # the first one becomes the article URL (the post's primary
        # link).
        body = _atom_payload("""<entry>
  <id>https://tildes.net/~tech/x/multi</id>
  <title>A post that mentions several sites</title>
  <author><name>user</name></author>
  <content type="html">
    &lt;p&gt;Main: &lt;a href="https://primary.example/article"&gt;here&lt;/a&gt;.
    Also see &lt;a href="https://secondary.example/x"&gt;this&lt;/a&gt;.&lt;/p&gt;
  </content>
</entry>""")
        with patch.object(tildes.requests, "get", return_value=_fake_get(body)):
            out = tildes.top()
        self.assertEqual(out[0]["url"], "https://primary.example/article")

    def test_honors_limit(self):
        entries = "".join(
            _link_entry(
                title=f"Post {i}",
                tildes_id=f"https://tildes.net/~tech/x{i}/post_{i}",
                article_url=f"https://example.com/{i}",
            )
            for i in range(40)
        )
        body = _atom_payload(entries)
        with patch.object(tildes.requests, "get", return_value=_fake_get(body)):
            out = tildes.top(limit=5)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["url"], "https://example.com/0")

    def test_handles_empty_feed(self):
        body = _atom_payload("")
        with patch.object(tildes.requests, "get", return_value=_fake_get(body)):
            self.assertEqual(tildes.top(), [])


if __name__ == "__main__":
    unittest.main()
