"""Pinboard REST client.

Wraps the public REST API at ``https://api.pinboard.in/v1``. Auth
via ``PINBOARD_API_TOKEN`` (form: ``user:HEX``).
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter
from typing import Any

import requests

API_BASE = "https://api.pinboard.in/v1"
POPULAR_FEED = "https://feeds.pinboard.in/rss/popular/"

logger = logging.getLogger("workshop.systems.pinboard")


def _token() -> str:
    tok = os.environ.get("PINBOARD_API_TOKEN")
    if not tok:
        raise RuntimeError("PINBOARD_API_TOKEN is not set")
    return tok


def _username() -> str:
    """Pinboard username, parsed from ``PINBOARD_API_TOKEN`` (``user:HEX``)."""
    tok = os.environ.get("PINBOARD_API_TOKEN") or ""
    if ":" in tok:
        return tok.split(":", 1)[0]
    return ""


def bookmark_url(url: str) -> str:
    """Permalink to this user's bookmark of ``url`` on Pinboard.

    Per-user bookmark URL is ``https://pinboard.in/u:{username}/b:{md5(url)}/``.
    Returns empty if username is unknown or url is empty.
    """
    user = _username()
    if not (user and url):
        return ""
    h = hashlib.md5(url.encode("utf-8")).hexdigest()
    return f"https://pinboard.in/u:{user}/b:{h}/"


def recent_posts(count: int = 50, tag: str | None = None) -> list[dict[str, Any]]:
    """Up to ``count`` most recent bookmarks. Pinboard caps ``count`` at 100."""
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
    """Bookmarks marked ``to read`` on Pinboard.

    Pinboard exposes a ``toread`` flag on each bookmark; the
    ``posts/all`` endpoint accepts ``toread=yes`` and returns *only*
    unread items.
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
    """Trim a Pinboard record to the fields Linky cares about."""
    href = post.get("href", "")
    return {
        "url": href,
        "title": post.get("description", ""),  # Pinboard's "description" is the title
        "description": post.get("extended", ""),  # Pinboard's "extended" is the body
        "tags": post.get("tags", ""),
        "added": post.get("time", ""),
        "toread": post.get("toread", "") == "yes",
        "pinboard_url": bookmark_url(href),
    }


def popular(limit: int = 30) -> list[dict[str, Any]]:
    """Pinboard's site-wide popular bookmarks feed (RSS).

    No auth needed — public discovery surface, the same feed Jamie
    scans manually. Returns ``[{title, url, description, posted_by}]``.
    """
    resp = requests.get(
        POPULAR_FEED,
        timeout=20,
        headers={"User-Agent": "WeeklyThing-WorkshopBot/1.0"},
    )
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


def tag_summary(*, limit: int = 200, top: int = 10) -> dict[str, Any]:
    """Tag frequency over the unread pile.

    Fetches up to ``limit`` unread bookmarks and aggregates their
    space-separated ``tags`` field. Returns ``{total_items, top_tags}``
    where ``top_tags`` is the ``top`` most common tags as
    ``[{tag, count}, ...]``.
    """
    posts = all_unread(limit=int(limit))
    counter: Counter[str] = Counter()
    for p in posts:
        for t in (p.get("tags") or "").split():
            counter[t] += 1
    return {
        "total_items": len(posts),
        "top_tags": [
            {"tag": t, "count": n} for t, n in counter.most_common(int(top))
        ],
    }
