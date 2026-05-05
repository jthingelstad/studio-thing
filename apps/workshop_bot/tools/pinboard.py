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


def normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    """Trim Pinboard's record to the fields Linky cares about."""
    return {
        "url": post.get("href", ""),
        "title": post.get("description", ""),  # Pinboard's "description" is the title
        "description": post.get("extended", ""),  # Pinboard's "extended" is the body
        "tags": post.get("tags", ""),
        "added": post.get("time", ""),
    }
