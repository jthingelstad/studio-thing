"""PinboardServer — registry-facing tool surface for Pinboard."""

from __future__ import annotations

from typing import Any, Optional

from ...tools import db
from .._base import ToolDef
from . import client


class PinboardServer:
    name = "pinboard"
    # Pinboard is Linky's lane — link curation. Mutating tools (`save`)
    # plus the same-domain query surface live here, so other personas
    # have no business reaching for them.
    restricted_to = {"linky"}

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="recent",
                description=(
                    "Live-fetch the N most recent bookmarks from Pinboard. "
                    "Persists to SQLite. Costs an HTTP round trip."
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
                    "Live-fetch bookmarks marked `to read` on Pinboard. "
                    "Persists to SQLite."
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
                    "Pinboard's site-wide popular bookmarks feed. Returns "
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
                    "Read the N most recent bookmarks already stored in "
                    "SQLite (no live API call)."
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
                    "{total_items, top_tags}."
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
            ToolDef(
                name="update_check",
                description=(
                    "ISO timestamp of the most recent Pinboard mutation. "
                    "Cheap freshness gate."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: {"update_time": client.posts_update()},
            ),
            ToolDef(
                name="lookup_url",
                description=(
                    "Look up a URL in Jamie's Pinboard. Returns the "
                    "bookmark if saved, empty list otherwise."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "exact URL to look up"},
                    },
                    "required": ["url"],
                },
                handler=lambda deps, url, **_kw: client.posts_get(url=str(url)),
            ),
            ToolDef(
                name="suggest_tags",
                description=(
                    "Pinboard's tag suggestions for a URL. Returns "
                    "{popular, recommended}."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
                handler=lambda deps, url, **_kw: client.posts_suggest(url=str(url)),
            ),
            ToolDef(
                name="archive_tags",
                description=(
                    "Top N tags across Jamie's whole Pinboard archive "
                    "(not just unread — that's `tag_summary`)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "top": {
                            "type": "integer",
                            "description": "how many tags to return; default 50",
                        },
                    },
                },
                handler=_handle_archive_tags,
            ),
            ToolDef(
                name="bookmark_dates",
                description=(
                    "Bookmark counts per day across the whole archive. "
                    "Returns {YYYY-MM-DD: count}. Optional `tag` scopes to "
                    "one tag's history."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "description": "optional Pinboard tag filter",
                        },
                    },
                },
                handler=lambda deps, tag=None, **_kw: client.posts_dates(
                    tag=tag if tag else None,
                ),
            ),
            ToolDef(
                name="save",
                description=(
                    "MUTATING — saves a bookmark to Jamie's Pinboard. "
                    "Defaults: toread=true, shared=true, replace=false (will "
                    "NOT overwrite). Always call `lookup_url` first to avoid "
                    "duplicate-save errors."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string", "description": "max 255 chars"},
                        "description": {
                            "type": "string",
                            "description": "longer body / commentary, optional",
                        },
                        "tags": {
                            "type": "string",
                            "description": (
                                "space-separated, max 100 tags, no commas "
                                "or whitespace within a tag"
                            ),
                        },
                        "toread": {
                            "type": "boolean",
                            "description": "default true — lands in unread queue",
                        },
                        "shared": {
                            "type": "boolean",
                            "description": "default true — public on Pinboard",
                        },
                    },
                    "required": ["url", "title"],
                },
                handler=_handle_save,
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


def _handle_archive_tags(
    deps: Any,
    top: int = 50,
    **_kw: Any,
) -> list[dict[str, Any]]:
    return client.tags_get()[: int(top)]


def _handle_save(
    deps: Any,
    url: str,
    title: str,
    description: str = "",
    tags: str = "",
    toread: bool = True,
    shared: bool = True,
    **_kw: Any,
) -> dict[str, Any]:
    return client.posts_add(
        url=str(url),
        title=str(title),
        description=str(description or ""),
        tags=str(tags or ""),
        toread=bool(toread),
        shared=bool(shared),
        replace=False,
    )
