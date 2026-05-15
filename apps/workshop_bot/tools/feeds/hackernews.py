"""Hacker News front-page feed (via Algolia).

A fourth discovery source for Linky's hourly per-link scan, alongside
Pinboard popular, Lobste.rs hottest, and Jamie's own toread pile.
Hacker News doesn't publish a JSON front-page feed directly, but the
Algolia search index it ships exposes ``tags=front_page`` — the same
stories currently showing on the front page, ranked the same way. No
auth needed.

Each item is normalised to the same dict shape ``pinboard-scan`` uses
for Lobste.rs items (URL + title + a discussion link + a few signals
for the LLM prompt):

  {
    "url": "https://example.com/article",        # the article URL — the
                                                 # one we'd bookmark
    "title": "Article title",
    "discussion_url": "https://news.ycombinator.com/item?id=48087887",
    "score": 412,
    "comment_count": 187,
    "submitter": "username",
  }

Ask HN / Show HN posts that have no external URL (i.e. the "story" is
the comment thread itself) are skipped — they aren't *links* Linky can
research and there's nothing to bookmark.

URLs surfaced here are deduped against the same ``pinboard_popular_seen``
table the other two discovery feeds use — a URL Jamie has been shown
from any popular surface stays out of the queue, even if multiple feeds
trend it on the same day.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("workshop.hackernews")

# Algolia's HN search index. `tags=front_page` returns the stories
# currently on news.ycombinator.com's front page (the same set you'd
# scroll through on the site, ranked the same way).
SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"

# HN front-page items routinely clear 100 points within hours of
# submission; lower-third items (30-80) are mostly noise from Linky's
# perspective. This filter drops the bottom of the front page before
# the per-link LLM call runs — the single biggest volume reduction
# available without dropping HN entirely. Tunable via env for live
# tuning without a redeploy.
_DEFAULT_MIN_SCORE = 100


def _min_score() -> int:
    raw = (os.environ.get("WORKSHOP_HN_MIN_SCORE") or "").strip()
    if not raw:
        return _DEFAULT_MIN_SCORE
    try:
        v = int(raw)
        return v if v >= 0 else _DEFAULT_MIN_SCORE
    except ValueError:
        return _DEFAULT_MIN_SCORE


def _item_url(object_id: str) -> str:
    return f"https://news.ycombinator.com/item?id={object_id}"


def top(*, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch the current Hacker News front page via Algolia. Returns up
    to ``limit`` normalised items in front-page order, filtered to
    items with ``score >= WORKSHOP_HN_MIN_SCORE`` (default 100). Network
    / parse errors propagate; the caller (the job) catches and degrades
    to an empty list so a flakey upstream doesn't block the other
    sources."""
    # Pull a bigger window so the score filter can do its work even
    # when the front page is heavy on rising items. The caller's
    # ``limit`` caps the returned set.
    fetch_n = max(int(limit), 30)
    params = {"tags": "front_page", "hitsPerPage": fetch_n}
    resp = requests.get(
        SEARCH_URL,
        params=params,
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json() or {}
    hits = data.get("hits") or []
    floor = _min_score()
    out: list[dict[str, Any]] = []
    dropped_low_score = 0
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        url = (hit.get("url") or "").strip()
        if not url:
            # Ask HN / Show HN without an external URL — discussion-only.
            continue
        score = int(hit.get("points") or 0)
        if score < floor:
            dropped_low_score += 1
            continue
        object_id = str(hit.get("objectID") or "").strip()
        out.append({
            "url": url,
            "title": (hit.get("title") or "").strip(),
            "discussion_url": _item_url(object_id) if object_id else "",
            "score": score,
            "comment_count": int(hit.get("num_comments") or 0),
            "submitter": (hit.get("author") or "").strip(),
        })
        if len(out) >= int(limit):
            break
    logger.info("hackernews: front_page -> %d items (dropped %d below score %d)",
                len(out), dropped_low_score, floor)
    return out
