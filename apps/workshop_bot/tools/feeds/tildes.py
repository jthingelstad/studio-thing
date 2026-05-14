"""Tildes ~tech feed.

A discovery source for Linky's hourly per-link scan, parallel to
Lobsters and Hacker News. Tildes publishes its group feeds as Atom at
``https://tildes.net/~tech/topics.atom`` (`.atom` works; bare `~tech.atom`
404s, and `~tech/topics.rss` is the RSS twin). No auth needed.

Tildes mixes two kinds of entries on a group page:

- **Link posts** — the article URL is embedded as the first non-tildes.net
  ``href`` in the entry's ``<content>``. The Atom entry's ``id`` (and the
  ``<link rel="alternate">``) points at the Tildes discussion page, which
  we surface as ``discussion_url``.
- **Text posts** — Ask-HN-style discussion-only entries. No external URL
  in ``<content>``. Skip them; there's nothing bookmarkable.

Tildes' Atom feed doesn't expose vote counts or comment counts, so
``score`` and ``comment_count`` stay at zero — the per-link prompt's
renderer drops the "signal" line in that case rather than printing
zeros.

Normalised shape (matches Lobsters and HN):

  {
    "url": "https://example.com/article",
    "title": "Article title",
    "discussion_url": "https://tildes.net/~tech/<id>/<slug>",
    "score": 0,
    "comment_count": 0,
    "submitter": "username",
    "tags": [],
  }
"""

from __future__ import annotations

import logging
import re
from typing import Any
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger("workshop.tildes")

TOPICS_URL = "https://tildes.net/~tech/topics.atom"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"

_NS = {"a": "http://www.w3.org/2005/Atom"}
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def _first_external_url(content: str) -> str:
    """Return the first ``href`` in ``content`` that doesn't point at
    tildes.net itself. Empty string if none — the entry is a text post."""
    if not content:
        return ""
    for match in _HREF_RE.finditer(content):
        url = match.group(1).strip()
        if not url:
            continue
        if "tildes.net" in url.lower():
            continue
        return url
    return ""


def top(*, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch the current Tildes ~tech feed and return up to ``limit``
    normalised **link** posts (text posts are dropped). Order matches the
    feed's order (newest first per Tildes' default). Network / parse
    errors propagate; the caller (the job) catches and degrades to an
    empty list so a flakey upstream doesn't block other sources."""
    resp = requests.get(
        TOPICS_URL,
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "application/atom+xml"},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", _NS):
        if len(out) >= int(limit):
            break
        title = (entry.findtext("a:title", "", _NS) or "").strip()
        entry_id = (entry.findtext("a:id", "", _NS) or "").strip()
        # The <content> element holds the post body, including any
        # external link the submitter referenced.
        content = (entry.findtext("a:content", "", _NS) or "").strip()
        article_url = _first_external_url(content)
        if not article_url:
            # Text post — discussion-only, no bookmarkable URL.
            continue
        submitter = (entry.findtext("a:author/a:name", "", _NS) or "").strip()
        out.append({
            "url": article_url,
            "title": title,
            "discussion_url": entry_id,
            "score": 0,
            "comment_count": 0,
            "submitter": submitter,
            "tags": [],
        })
    logger.info("tildes: ~tech.atom -> %d link posts (after dropping text posts)", len(out))
    return out
