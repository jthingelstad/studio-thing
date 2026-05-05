"""Minimal Pinboard REST client.

Auth token comes from PINBOARD_API_TOKEN. The token is in the form
"username:HEX" — Pinboard accepts it as ?auth_token=… on every endpoint.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

API_BASE = "https://api.pinboard.in/v1"

logger = logging.getLogger("workshop.pinboard")


def _token() -> str:
    tok = os.environ.get("PINBOARD_API_TOKEN")
    if not tok:
        raise RuntimeError("PINBOARD_API_TOKEN is not set")
    return tok


def recent_posts(count: int = 50, tag: str | None = None) -> list[dict[str, Any]]:
    """Return up to `count` most recent bookmarks. Pinboard caps `count` at 100."""
    params: dict[str, Any] = {
        "auth_token": _token(),
        "format": "json",
        "count": min(max(count, 1), 100),
    }
    if tag:
        params["tag"] = tag
    resp = requests.get(f"{API_BASE}/posts/recent", params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    posts: list[dict[str, Any]] = data.get("posts", []) or []
    logger.info("pinboard: fetched %d recent posts (tag=%s)", len(posts), tag or "-")
    return posts


def all_unread(
    *,
    limit: int = 100,
    tag: str | None = None,
    fromdt: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch bookmarks Jamie has marked as ``to read`` on Pinboard.

    Pinboard exposes a ``toread`` flag on each bookmark; the ``posts/all``
    endpoint accepts ``toread=yes`` and returns *only* unread items.
    """
    params: dict[str, Any] = {
        "auth_token": _token(),
        "format": "json",
        "toread": "yes",
        "results": min(max(limit, 1), 1000),
    }
    if tag:
        params["tag"] = tag
    if fromdt:
        params["fromdt"] = fromdt
    resp = requests.get(f"{API_BASE}/posts/all", params=params, timeout=30)
    resp.raise_for_status()
    posts: list[dict[str, Any]] = resp.json() or []
    logger.info("pinboard: fetched %d unread posts (tag=%s)", len(posts), tag or "-")
    return posts


def normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    """Trim Pinboard's record to the fields Linky cares about."""
    return {
        "url": post.get("href", ""),
        "title": post.get("description", ""),  # Pinboard's "description" is the title
        "description": post.get("extended", ""),  # Pinboard's "extended" is the body
        "tags": post.get("tags", ""),
        "added": post.get("time", ""),
        "toread": post.get("toread", "") == "yes",
    }


# ---- Pinboard's popular feed ----

POPULAR_FEED = "https://feeds.pinboard.in/rss/popular/"


def popular(limit: int = 30) -> list[dict[str, Any]]:
    """Pinboard's site-wide popular bookmarks feed (RSS).

    No auth needed — this is the public discovery surface, the same feed
    Jamie scans manually. Returns ``[{title, url, description, posted_by}]``.
    """
    resp = requests.get(POPULAR_FEED, timeout=20, headers={"User-Agent": "WeeklyThing-WorkshopBot/1.0"})
    resp.raise_for_status()
    # Imported lazily so the module loads in environments without bs4.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "xml")
    items = soup.find_all("item")
    out: list[dict[str, Any]] = []
    for item in items[:limit]:
        title = (item.title.text if item.title else "").strip()
        link = (item.link.text if item.link else "").strip()
        desc = (item.description.text if item.description else "").strip()
        creator = item.find("dc:creator")
        posted_by = creator.text.strip() if creator is not None else ""
        out.append(
            {
                "url": link,
                "title": title,
                "description": desc,
                "posted_by": posted_by,
            }
        )
    logger.info("pinboard.popular: %d items from %s", len(out), POPULAR_FEED)
    return out
