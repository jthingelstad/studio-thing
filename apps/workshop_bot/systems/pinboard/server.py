"""PinboardServer — registry-facing tool surface for Pinboard.

Two layers:

- **Job-oriented verbs** — what Linky's prompt reaches for first:
  ``issue_candidates``, ``capture_blurb``, ``popular_unseen``,
  ``mark_seen``, ``estimate_read_length``, ``queue_depth_vs_deadline``,
  ``archive_recall``. They collapse "fetch, filter, merge, write" onto the
  thin v1 calls.
- **Thin API mirrors** — ``recent``, ``unread``, ``popular``,
  ``stored_recent``, ``tag_summary``, ``update_check``, ``lookup_url``,
  ``suggest_tags``, ``archive_tags``, ``bookmark_dates``, ``save``. Still
  available for ad-hoc use.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ...tools import avoid_domains, db, web
from .._base import ToolDef
from . import client

logger = logging.getLogger("workshop.systems.pinboard.server")

# Read-length buckets, by fetched word count.
_SHORT_MAX = 800
_LONG_MIN = 2500


class PinboardServer:
    name = "pinboard"
    # Pinboard is Linky's lane — link curation. Mutating tools (`save`,
    # `capture_blurb`) plus the same-domain query surface live here, so
    # other personas have no business reaching for them.
    restricted_to = {"linky"}

    def list_tools(self) -> list[ToolDef]:
        return [
            # ---------- job-oriented verbs ----------
            ToolDef(
                name="issue_candidates",
                description=(
                    "Bookmarks belonging to the in-flight issue's content "
                    "window. `section`='notable' returns items NOT tagged "
                    "`_brief`; `section`='brief' returns items tagged `_brief` "
                    "(post-capture). Omit `section` to get both, as "
                    "{notable: [...], brief: [...]}. Each item has url, title, "
                    "description, tags, added, pinboard_url, added_date. "
                    "(There is no `_featured` section anymore.)"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "enum": ["notable", "brief"],
                            "description": "optional; omit for both",
                        },
                    },
                },
                handler=_handle_issue_candidates,
            ),
            ToolDef(
                name="capture_blurb",
                description=(
                    "MUTATING — 'this is a Briefly': writes `blurb` as the "
                    "bookmark's description verbatim, adds the `_brief` tag, "
                    "and clears `toread`. Preserves the title and other tags. "
                    "Use after Jamie replies with a one-liner for a toread "
                    "item — his reply IS the blurb. The item then flows into "
                    "the next update-draft Briefly section. Errors if the URL "
                    "isn't bookmarked yet."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "blurb": {"type": "string", "description": "Jamie's reply, verbatim"},
                    },
                    "required": ["url", "blurb"],
                },
                handler=lambda deps, url, blurb, **_kw: client.capture_blurb(str(url), str(blurb)),
            ),
            ToolDef(
                name="popular_unseen",
                description=(
                    "Pinboard's site-wide popular feed, minus (a) anything "
                    "you've already surfaced to Jamie (deduped against "
                    "pinboard_popular_seen) and (b) utility / CDN / social / "
                    "Jamie's-own-domain noise (the same exclusion list the "
                    "archive uses). Returns [{url, title, description, "
                    "posted_by}]. Cap your surfacing at one item per scan — "
                    "better silence than spam."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "feed page size to consider; default 30"},
                    },
                },
                handler=_handle_popular_unseen,
            ),
            ToolDef(
                name="mark_seen",
                description=(
                    "Record that you've shown this popular-feed URL to Jamie, "
                    "so popular_unseen won't surface it again. Call it for "
                    "every popular item you considered this scan — whether or "
                    "not you surfaced it — so the dedup is honest."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "interesting": {
                            "type": "boolean",
                            "description": "optional — your verdict, recorded for later audits",
                        },
                        "note": {"type": "string", "description": "optional one-line rationale"},
                    },
                    "required": ["url"],
                },
                handler=_handle_mark_seen,
            ),
            ToolDef(
                name="estimate_read_length",
                description=(
                    "Fetch a URL and bucket how long it is to read: 'short' "
                    "(<~800 words), 'medium', 'long' (>~2500 words), or "
                    "'unknown' if it can't be fetched (paywall, login, "
                    "binary). Returns {url, bucket, word_count}."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                handler=lambda deps, url, **_kw: _estimate_read_length(str(url)),
            ),
            ToolDef(
                name="queue_depth_vs_deadline",
                description=(
                    "How big is the toread pile vs. how long until publish. "
                    "Returns {toread_count, days_to_pub, per_day_to_clear, "
                    "trend} where trend is 'piling-up' / 'manageable' / "
                    "'clear' / 'no-issue' (no active window). Use to decide "
                    "whether to nudge Jamie about an end-of-week pile."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: _queue_depth_vs_deadline(),
            ),
            ToolDef(
                name="archive_recall",
                description=(
                    "Substring search across Jamie's WHOLE Pinboard archive "
                    "(not just the unread pile — that's tag_summary / unread). "
                    "Use to check 'has Jamie bookmarked this domain / topic "
                    "before?'. Returns up to `k` matching bookmarks, newest "
                    "first."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer", "description": "default 8"},
                    },
                    "required": ["query"],
                },
                handler=lambda deps, query, k=8, **_kw: client.archive_search(str(query), int(k)),
            ),
            # ---------- thin API mirrors (ad-hoc) ----------
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


# ---------- job-oriented handlers ----------

def _handle_issue_candidates(
    deps: Any, section: Optional[str] = None, **_kw: Any
) -> Any:
    window = db.get_active_issue_window()
    if window is None:
        return {"error": "No active issue window. Jamie sets it via /workshop job start-issue."}
    cand = client.issue_window_candidates(window["start_date"], window["end_date"])
    if section in ("notable", "brief"):
        return cand[section]
    return cand


def _handle_popular_unseen(deps: Any, limit: int = 30, **_kw: Any) -> list[dict[str, Any]]:
    feed = [
        it for it in client.popular(limit=int(limit))
        if it.get("url") and not avoid_domains.is_excluded_url(it["url"])
    ]
    return db.filter_unseen_popular(feed)


def _handle_mark_seen(
    deps: Any,
    url: str,
    title: Optional[str] = None,
    interesting: Optional[bool] = None,
    note: Optional[str] = None,
    **_kw: Any,
) -> dict[str, Any]:
    judged = None
    if interesting is not None or note:
        judged = {url: (bool(interesting), note or "")}
    n = db.mark_popular_seen([{"url": url, "title": title}], judged=judged)
    return {"url": url, "recorded": n > 0 or True}


def _estimate_read_length(url: str) -> dict[str, Any]:
    res = web.fetch_text(url, max_chars=200_000)
    text = (res or {}).get("text") or ""
    if not text:
        return {"url": url, "bucket": "unknown", "word_count": 0,
                "error": (res or {}).get("error") or "no readable text"}
    wc = len(text.split())
    if wc < _SHORT_MAX:
        bucket = "short"
    elif wc > _LONG_MIN:
        bucket = "long"
    else:
        bucket = "medium"
    return {"url": url, "bucket": bucket, "word_count": wc}


def _queue_depth_vs_deadline() -> dict[str, Any]:
    try:
        toread = client.all_unread(limit=1000)
        toread_count = len(toread)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"couldn't fetch the toread pile: {type(exc).__name__}: {exc}"}
    window = db.get_active_issue_window()
    if window is None:
        return {"toread_count": toread_count, "days_to_pub": None,
                "per_day_to_clear": None, "trend": "no-issue"}
    from datetime import datetime
    try:
        days = (datetime.strptime(window["pub_date"], "%Y-%m-%d").date() - datetime.now().date()).days
    except (TypeError, ValueError):
        days = None
    per_day = (toread_count / days) if (days and days > 0) else None
    if toread_count == 0:
        trend = "clear"
    elif per_day is None:
        trend = "manageable"
    elif per_day > 6:
        trend = "piling-up"
    else:
        trend = "manageable"
    return {"toread_count": toread_count, "days_to_pub": days,
            "per_day_to_clear": round(per_day, 1) if per_day is not None else None,
            "trend": trend}
