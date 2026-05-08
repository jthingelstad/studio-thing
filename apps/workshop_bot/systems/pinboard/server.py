"""PinboardServer — registry-facing tool surface for Pinboard."""

from __future__ import annotations

from typing import Any, Optional

from ...tools import db
from .._base import ToolDef
from . import client


class PinboardServer:
    name = "pinboard"

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="recent",
                description=(
                    "Live-fetch the most recent N bookmarks from Pinboard "
                    "and persist them to SQLite. Costs an HTTP round trip — "
                    "use only when the user explicitly wants fresh data."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "default 50, max 100",
                        },
                    },
                },
                handler=_handle_recent,
            ),
            ToolDef(
                name="unread",
                description=(
                    "Live-fetch bookmarks Jamie has marked as `to read` on "
                    "Pinboard. This is the working queue for the next "
                    "issue. Persists to SQLite."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "default 100, max 1000",
                        },
                        "tag": {
                            "type": "string",
                            "description": "optional Pinboard tag filter",
                        },
                    },
                },
                handler=_handle_unread,
            ),
            ToolDef(
                name="popular",
                description=(
                    "Pinboard's site-wide popular bookmarks feed — the "
                    "discovery surface Jamie scans manually. Use to suggest "
                    "items he might not have seen yet, or to ground "
                    "'what's resonating across Pinboard right now'. Returns "
                    "title, url, description, posted_by."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "default 30"},
                    },
                },
                handler=lambda deps, limit=30, **_kw: client.popular(limit=int(limit)),
            ),
            ToolDef(
                name="stored_recent",
                description=(
                    "Read the most recent N bookmarks already stored in "
                    "SQLite (no live API call). Reach for this before "
                    "`pinboard.recent` when freshness isn't critical."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "default 30"},
                    },
                },
                handler=_handle_stored_recent,
            ),
            ToolDef(
                name="tag_summary",
                description=(
                    "Tag frequency across the unread pile. Returns "
                    "{total_items, top_tags: [{tag, count}, ...]}. Use as a "
                    "quick theme preview — what is Jamie reading toward "
                    "this week — without paging through every bookmark."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "max unread items to scan; default 200",
                        },
                        "top": {
                            "type": "integer",
                            "description": "how many tags to return; default 10",
                        },
                    },
                },
                handler=lambda deps, limit=200, top=10, **_kw: client.tag_summary(
                    limit=int(limit), top=int(top)
                ),
            ),
        ]


# ---------- handlers with side effects ----------
#
# `recent` and `unread` write into the link_candidates SQLite table
# (Linky's working set), so they get full handler functions rather than
# inline lambdas.

def _handle_recent(
    deps: Any,
    count: int = 50,
    **_kw: Any,
) -> list[dict[str, Any]]:
    raw = client.recent_posts(count=int(count))
    posts = [client.normalize_post(p) for p in raw]
    for p in posts:
        db.upsert_link_candidate(
            url=p["url"],
            title=p["title"],
            description=p["description"],
            pinboard_tags=p["tags"],
            pinboard_added=p["added"],
        )
    return posts


def _handle_unread(
    deps: Any,
    limit: int = 100,
    tag: Optional[str] = None,
    **_kw: Any,
) -> list[dict[str, Any]]:
    raw = client.all_unread(limit=int(limit), tag=tag)
    posts = [client.normalize_post(p) for p in raw]
    for p in posts:
        db.upsert_link_candidate(
            url=p["url"],
            title=p["title"],
            description=p["description"],
            pinboard_tags=p["tags"],
            pinboard_added=p["added"],
        )
    return posts


def _handle_stored_recent(
    deps: Any,
    limit: int = 30,
    **_kw: Any,
) -> list[dict[str, Any]]:
    rows = db.recent_link_candidates(limit=int(limit))
    for row in rows:
        url = row.get("url") or ""
        if url:
            row["pinboard_url"] = client.bookmark_url(url)
    return rows
