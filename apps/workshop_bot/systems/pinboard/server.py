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
            ToolDef(
                name="update_check",
                description=(
                    "Cheap freshness gate — returns the ISO timestamp of "
                    "Jamie's most recent bookmark mutation. Call this "
                    "before `pinboard.unread` if you've fetched recently "
                    "and want to skip the expensive call when nothing has "
                    "changed."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: {"update_time": client.posts_update()},
            ),
            ToolDef(
                name="lookup_url",
                description=(
                    "Did Jamie already save this URL? Returns the bookmark "
                    "if found, empty list otherwise. Use against popular-"
                    "feed candidates BEFORE recommending or saving — keeps "
                    "you from suggesting things already in his archive."
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
                    "Tag suggestions for a URL — both site-wide popular "
                    "tags and Jamie's personal recommended tags. Returns "
                    "{popular: [...], recommended: [...]}. Useful when "
                    "proposing a save from the popular feed so the tags "
                    "match Jamie's existing taxonomy."
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
                    "Full tag inventory across Jamie's WHOLE archive (not "
                    "just the unread pile — use `tag_summary` for that). "
                    "Returns the top N tags by count. Reach for this when "
                    "asking 'is theme X new for him or has he been "
                    "collecting it for years?'."
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
                    "Returns {YYYY-MM-DD: count, ...}. Optional `tag` "
                    "filter scopes to one tag's history. A reading-rhythm "
                    "signal — when did the saving rate spike, when did it "
                    "go quiet."
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
                    "Defaults: toread=true (lands in his review queue), "
                    "shared=true, replace=false (will NOT overwrite an "
                    "existing bookmark). Always call `lookup_url` first to "
                    "avoid duplicate-save errors. Only call when Jamie "
                    "asks you to save it, OR when scanning the popular "
                    "feed turns up something so on-theme it would be a "
                    "miss not to drop in his queue. When in doubt, ask "
                    "first."
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
