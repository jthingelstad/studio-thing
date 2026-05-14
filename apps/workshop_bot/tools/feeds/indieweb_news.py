"""IndieWeb News feed (HTML / h-feed).

A discovery source for Linky's hourly per-link scan. IndieWeb News
aggregates IndieWeb-aligned posts at ``https://news.indieweb.org/en``
and exposes them as microformats2 ``h-feed`` on the HTML page itself.
There's no direct Atom feed (the page's ``<link rel="alternate">``
points at a third-party granary proxy); we parse the HTML directly
with ``bs4`` — the same library already used for Pinboard's popular
RSS in ``systems/pinboard/client.py``.

IndieWeb News carries no scores, comment counts, or submitter handles
on the listing page, so ``score`` / ``comment_count`` stay at zero and
``submitter`` is empty. Each entry yields:

- The **article URL** — from the ``.title.p-name a`` link, the actual
  post the submitter is highlighting.
- The **discussion URL** — the IndieWeb News submission page itself
  (``https://news.indieweb.org/en/<path>``), a thin wrapper that links
  back to the article and shows the IndieWeb News listing metadata.

Normalised shape (matches the Lobsters / HN / Tildes shape):

  {
    "url": "https://example.com/article",
    "title": "Article title",
    "discussion_url": "https://news.indieweb.org/en/...",
    "score": 0,
    "comment_count": 0,
    "submitter": "",
    "tags": [],
  }
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger("workshop.indieweb_news")

LISTING_URL = "https://news.indieweb.org/en"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"


def top(*, limit: int = 20) -> list[dict[str, Any]]:
    """Fetch the IndieWeb News front page and return up to ``limit``
    normalised entries in listing order (newest first). Network / parse
    errors propagate; the caller (the job) catches and degrades to an
    empty list so a flakey upstream doesn't block other sources."""
    resp = requests.get(
        LISTING_URL,
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "text/html"},
    )
    resp.raise_for_status()
    # Imported lazily so the module loads in environments without bs4
    # (mirrors the pattern in `pinboard.popular`).
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[dict[str, Any]] = []
    for entry in soup.select(".h-entry"):
        if len(out) >= int(limit):
            break
        title_el = entry.select_one(".title.p-name a")
        if title_el is None:
            continue
        article_url = (title_el.get("href") or "").strip()
        title = title_el.get_text(strip=True)
        if not article_url or not title:
            continue
        iwn_link = entry.select_one("a[href^='https://news.indieweb.org/en/']")
        discussion_url = (iwn_link.get("href") if iwn_link is not None else "") or ""
        out.append({
            "url": article_url,
            "title": title,
            "discussion_url": discussion_url.strip(),
            "score": 0,
            "comment_count": 0,
            "submitter": "",
            "tags": [],
        })
    logger.info("indieweb_news: front page -> %d entries", len(out))
    return out
