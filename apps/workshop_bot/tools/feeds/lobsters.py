"""Lobste.rs hottest feed.

A third discovery source for Linky's hourly per-link scan, alongside
Pinboard's popular feed and Jamie's own toread pile. Lobste.rs publishes
``hottest.json`` — the same "hottest stories" view the site's front page
shows, in clean JSON. No auth needed.

Each item is normalised to the dict shape the ``pinboard-scan`` job
expects (``url``, ``title``, ``discussion_url``, plus a few extras the
LLM prompt may surface in the card):

  {
    "url": "https://example.com/article",      # the article URL — the
                                               # one we'd bookmark
    "title": "Article title",
    "discussion_url": "https://lobste.rs/s/abcd1234",  # Lobsters thread
    "tags": ["linux", "performance"],
    "score": 110,
    "comment_count": 15,
    "submitter": "username",
  }

URLs that show up here are deduped against the same
``pinboard_popular_seen`` table the Pinboard popular feed uses — a URL
Jamie has already seen from any popular discovery surface stays out of
the queue forever (or until Jamie clears the table). The avoid-domains
filter is *not* applied here at the source layer; the job applies it
uniformly over both popular feeds.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger("workshop.lobsters")

HOTTEST_URL = "https://lobste.rs/hottest.json"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"


def hottest(*, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch the current Lobste.rs hottest feed. Returns up to ``limit``
    normalised items, in the order Lobste.rs ranks them (hottest first).
    Network / parse errors propagate; the caller (the job) catches and
    degrades to an empty list so a flakey upstream doesn't block other
    sources."""
    resp = requests.get(
        HOTTEST_URL,
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    resp.raise_for_status()
    raw = resp.json() or []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        out.append({
            "url": url,
            "title": (item.get("title") or "").strip(),
            "discussion_url": (item.get("short_id_url") or "").strip(),
            "tags": list(item.get("tags") or []),
            "score": int(item.get("score") or 0),
            "comment_count": int(item.get("comment_count") or 0),
            "submitter": (item.get("submitter_user") or "").strip(),
        })
        if len(out) >= int(limit):
            break
    logger.info("lobsters: hottest -> %d items", len(out))
    return out
