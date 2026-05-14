"""Pinboard REST client.

Wraps the public REST API at ``https://api.pinboard.in/v1``. Auth
via ``PINBOARD_API_TOKEN`` (form: ``user:HEX``).

v2 of the API is still marked DRAFT in its own overview page
(https://www.pinboard.in/api/v2/overview), so we stay on v1. The
endpoint surface here covers most of what v2 promises (suggest,
lookup-by-url, full-tag inventory) using stable v1 calls.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import Counter
from typing import Any
from zoneinfo import ZoneInfo

import requests

# Pinboard's API serialises bookmark `time` in UTC, but the issue window
# (`start_date` / `end_date`) is Jamie's *local* calendar — the day begins
# at 00:00 America/Chicago. A bookmark added at 22:30 CDT lands at
# 03:30 UTC the next day; if we filter by the UTC calendar date it ends
# up in the wrong issue. So we convert every Pinboard timestamp to local
# time before taking `.date()`, matching what `microblog.published_local`
# does for journal posts.
_LOCAL_TZ = ZoneInfo("America/Chicago")

API_BASE = "https://api.pinboard.in/v1"
POPULAR_FEED = "https://feeds.pinboard.in/rss/popular/"

# Documented Pinboard cadence caps (seconds between calls per endpoint
# family). Used for *logging* only — we don't block. See
# https://www.pinboard.in/api/ "Rate Limits".
_CADENCE_SECONDS: dict[str, float] = {
    "all": 5 * 60.0,       # /posts/all — 1 call / 5 min
    "recent": 60.0,        # /posts/recent — 1 call / min
    "standard": 3.0,       # everything else — 1 call / 3 sec
}
_last_request_at: dict[str, float] = {}

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


def _note_cadence(family: str) -> None:
    """Log if we're calling ``family`` faster than the documented cadence."""
    cap = _CADENCE_SECONDS.get(family, _CADENCE_SECONDS["standard"])
    now = time.monotonic()
    last = _last_request_at.get(family)
    if last is not None and (now - last) < cap:
        logger.warning(
            "pinboard: %s called %.1fs after previous call (documented cadence: %.0fs)",
            family, now - last, cap,
        )
    _last_request_at[family] = now


def _get(path: str, params: dict[str, Any], *, family: str = "standard",
         timeout: float = 20.0) -> requests.Response:
    """GET a v1 endpoint, log cadence violations, surface 429 Retry-After."""
    _note_cadence(family)
    resp = requests.get(f"{API_BASE}{path}", params=params, timeout=timeout)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "?")
        logger.warning(
            "pinboard: 429 from %s (Retry-After=%s)", path, retry_after,
        )
    resp.raise_for_status()
    return resp


def recent_posts(count: int = 50, tag: str | None = None) -> list[dict[str, Any]]:
    """Up to ``count`` most recent bookmarks. Pinboard caps ``count`` at 100."""
    params: dict[str, Any] = {
        "auth_token": _token(),
        "format": "json",
        "count": min(max(count, 1), 100),
    }
    if tag:
        params["tag"] = tag
    resp = _get("/posts/recent", params, family="recent")
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
    resp = _get("/posts/all", params, family="all", timeout=30)
    posts: list[dict[str, Any]] = resp.json() or []
    logger.info("pinboard: fetched %d unread posts (tag=%s)", len(posts), tag or "-")
    return posts


def posts_all(
    *,
    fromdt: str | None = None,
    todt: str | None = None,
    tag: str | None = None,
    results: int = 1000,
) -> list[dict[str, Any]]:
    """All bookmarks (read *and* unread), optionally scoped by an
    ISO-UTC date range (Pinboard's ``fromdt``/``todt`` are bound-exclusive)
    and/or a tag. Same heavy endpoint as ``all_unread`` — 1 call / 5 min.
    """
    params: dict[str, Any] = {
        "auth_token": _token(),
        "format": "json",
        "results": min(max(int(results), 1), 1000),
    }
    if fromdt:
        params["fromdt"] = fromdt
    if todt:
        params["todt"] = todt
    if tag:
        params["tag"] = tag
    resp = _get("/posts/all", params, family="all", timeout=30)
    posts: list[dict[str, Any]] = resp.json() or []
    logger.info(
        "pinboard: fetched %d posts (fromdt=%s todt=%s tag=%s)",
        len(posts), fromdt, todt, tag or "-",
    )
    return posts


BRIEF_TAG = "_brief"


def _local_added_date(time_raw: str):
    """Pinboard's UTC ``time`` string → America/Chicago calendar date, or
    ``None`` if unparseable. The day-boundary fix: a bookmark added at
    22:30 CDT is local-date ``today`` even though its UTC timestamp lands
    at 03:30 UTC the next day, so the window filter has to read the
    *local* date, not the UTC one."""
    from datetime import datetime as _dt

    if not time_raw:
        return None
    try:
        dt = _dt.fromisoformat(str(time_raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_LOCAL_TZ)
    return dt.date()


def issue_window_candidates(start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    """Bookmarks added in the issue window ``(start_date, end_date]``
    (calendar dates in **America/Chicago**, ``YYYY-MM-DD``), partitioned
    into:

    - ``notable`` — items not tagged ``_brief``
    - ``brief``   — items tagged ``_brief``

    Only *public, read* bookmarks are included: anything still flagged
    ``toread`` (Jamie hasn't worked through it yet) or marked private
    (``shared=no``) is skipped — those aren't ready to ship.

    Each item is a :func:`normalize_post` record plus ``added_date``
    (the local calendar date the bookmark was added); oldest first
    within each list. (Earlier issues used a separate ``_featured`` tag
    for a Featured section that's been retired — that tag is no longer
    recognized.)

    Pinboard serialises ``time`` in UTC; every timestamp is converted to
    America/Chicago via :func:`_local_added_date` before the window
    check so a bookmark saved at 22:30 CT (i.e. 03:30 UTC the next day)
    lands in the right issue. The ``fromdt``/``todt`` fetch window is
    widened a day on each side so the local-date filter never trims
    something the API already returned.
    """
    from datetime import datetime as _dt, timedelta as _td

    sd = _dt.strptime(start_date, "%Y-%m-%d").date()
    ed = _dt.strptime(end_date, "%Y-%m-%d").date()
    fromdt = f"{(sd - _td(days=0)).isoformat()}T00:00:00Z"
    todt = f"{(ed + _td(days=2)).isoformat()}T00:00:00Z"
    raw = posts_all(fromdt=fromdt, todt=todt)
    notable: list[dict[str, Any]] = []
    brief: list[dict[str, Any]] = []
    for post in raw:
        d = _local_added_date(str(post.get("time") or ""))
        if d is None:
            continue
        if not (sd < d <= ed):
            continue
        if post.get("toread") == "yes" or post.get("shared") == "no":
            continue
        norm = normalize_post(post)
        norm["added_date"] = d.isoformat()
        tags = set((post.get("tags") or "").split())
        (brief if BRIEF_TAG in tags else notable).append(norm)
    notable.sort(key=lambda r: r.get("added", ""))
    brief.sort(key=lambda r: r.get("added", ""))
    logger.info(
        "pinboard: issue window %s..%s -> %d notable, %d brief",
        start_date, end_date, len(notable), len(brief),
    )
    return {"notable": notable, "brief": brief}


def bookmark_blank(url: str, *, fallback_title: str | None = None) -> dict[str, Any]:
    """Save ``url`` as ``toread=yes shared=yes`` with a blank description
    if it isn't bookmarked yet; if it is, leave the existing record
    alone and report ``created=False``. The persona's ✅ / 👍 save
    handler uses this — symmetric with :func:`set_description` (reply
    path) and :func:`tag_as_brief` (⭐ path); all three live here so
    the fetch-merge-write pattern is in one place.

    Returns ``{result_code, pinboard_url, created}``. ``created`` is
    True when ``posts_add`` actually wrote a new bookmark, False when
    the URL was already in Jamie's Pinboard (in which case
    ``result_code`` is ``"item already exists"`` and we leave the
    existing description / tags / toread / shared untouched).
    """
    existing = posts_get(url)
    posts = existing.get("posts") or []
    if posts:
        logger.info("pinboard: bookmark_blank url=%s (already bookmarked)", url)
        return {
            "result_code": "item already exists",
            "pinboard_url": bookmark_url(url),
            "created": False,
        }
    title = (fallback_title or url).strip() or url
    res = posts_add(
        url=url, title=title, description="", tags="",
        toread=True, shared=True, replace=False,
    )
    logger.info("pinboard: bookmark_blank url=%s created=True", url)
    return {
        "result_code": res.get("result_code"),
        "pinboard_url": res.get("pinboard_url") or bookmark_url(url),
        "created": res.get("result_code") == "done",
    }


def tag_as_brief(url: str, *, fallback_title: str | None = None) -> dict[str, Any]:
    """Atomic 'add the `_brief` tag, keep everything else.' Used by
    Linky's reaction listener — Jamie reacts ⭐ to one of Linky's
    `#research` cards and that URL gets flagged as a Briefly candidate
    on Pinboard. Preserves the existing title, description, ``toread``,
    and ``shared`` flags; the tag list is split, deduped, ``_brief``
    appended (if absent), and rejoined.

    If the URL isn't bookmarked yet (a discovery-source reaction), the
    new bookmark gets created as ``toread=yes shared=yes`` with
    ``tags="_brief"``, empty description, and ``fallback_title`` (or
    the URL).

    Returns ``{result_code, pinboard_url, created, tags}`` where ``tags``
    is the final tag string written to Pinboard.
    """
    existing = posts_get(url)
    posts = existing.get("posts") or []
    if not posts:
        title = (fallback_title or url).strip() or url
        res = posts_add(
            url=url, title=title, description="", tags=BRIEF_TAG,
            toread=True, shared=True, replace=False,
        )
        logger.info("pinboard: tag_as_brief url=%s created=True", url)
        return {
            "result_code": res.get("result_code"),
            "pinboard_url": res.get("pinboard_url") or bookmark_url(url),
            "created": True,
            "tags": BRIEF_TAG,
        }
    post = posts[0]
    title = post.get("description", "") or url  # Pinboard's "description" is the title
    existing_desc = post.get("extended", "")     # Pinboard's "extended" is the body
    tags = [t for t in (post.get("tags") or "").split() if t]
    if BRIEF_TAG not in tags:
        tags.append(BRIEF_TAG)
    tag_str = " ".join(tags)
    shared = (post.get("shared", "yes") != "no")
    toread = (post.get("toread", "no") == "yes")
    res = posts_add(
        url=url, title=title, description=str(existing_desc or ""),
        tags=tag_str, toread=toread, shared=shared, replace=True,
    )
    logger.info("pinboard: tag_as_brief url=%s tags=%s result=%s",
                url, tag_str, res.get("result_code"))
    return {
        "result_code": res.get("result_code"),
        "pinboard_url": res.get("pinboard_url") or bookmark_url(url),
        "created": False,
        "tags": tag_str,
    }


def set_description(url: str, description: str, *, fallback_title: str | None = None) -> dict[str, Any]:
    """Atomic 'overwrite the description, keep everything else.' Used by
    Linky's reply listener — Jamie replies to one of Linky's #research
    cards in Discord and the reply text becomes the Pinboard bookmark's
    description verbatim. Preserves the existing title, tags, ``toread``,
    and ``shared`` flags.

    If the URL isn't bookmarked yet (the popular-feed case), it gets
    created as ``toread=yes shared=yes`` with this description and
    ``fallback_title`` (or the URL, if no title was passed). That mirrors
    the same "I want this — start the commentary" gesture Jamie makes for
    toread items.

    Returns ``{result_code, pinboard_url, created, replaced}``.
    """
    existing = posts_get(url)
    posts = existing.get("posts") or []
    if not posts:
        # New bookmark — popular-feed reply case.
        title = (fallback_title or url).strip() or url
        res = posts_add(
            url=url,
            title=title,
            description=str(description or ""),
            tags="",
            toread=True,
            shared=True,
            replace=False,
        )
        logger.info("pinboard: set_description url=%s created=True", url)
        return {
            "result_code": res.get("result_code"),
            "pinboard_url": res.get("pinboard_url") or bookmark_url(url),
            "created": True,
            "replaced": False,
        }
    post = posts[0]
    title = post.get("description", "") or url  # Pinboard's "description" is the title
    tags = [t for t in (post.get("tags") or "").split() if t]  # preserve verbatim
    shared = (post.get("shared", "yes") != "no")
    toread = (post.get("toread", "no") == "yes")
    res = posts_add(
        url=url,
        title=title,
        description=str(description or ""),
        tags=" ".join(tags),
        toread=toread,
        shared=shared,
        replace=True,
    )
    logger.info("pinboard: set_description url=%s replaced=%s", url, res.get("result_code"))
    return {
        "result_code": res.get("result_code"),
        "pinboard_url": res.get("pinboard_url") or bookmark_url(url),
        "created": False,
        "replaced": res.get("result_code") == "done",
    }


def toread_public_unresearched(*, limit: int = 25) -> list[dict[str, Any]]:
    """Jamie's public toread bookmarks that Linky hasn't researched yet —
    the input list for the hourly per-link scan's toread lane. Newest
    first. Filters at three layers:

    - ``toread=yes`` (Pinboard's flag — Jamie hasn't worked through it)
    - ``shared=yes`` (public; private bookmarks aren't candidates)
    - not in ``pinboard_research_done`` (Linky already posted a card)
    """
    from ...tools import db as _db

    raw = all_unread(limit=int(limit) * 4)  # over-fetch to absorb the filter cuts
    public = [
        p for p in raw
        if p.get("shared", "yes") != "no"
        and (p.get("href") or p.get("url"))
    ]
    urls = [(p.get("href") or p.get("url")) for p in public]
    unresearched = set(_db.filter_unresearched_urls(urls))
    out = [
        normalize_post(p)
        for p in public
        if (p.get("href") or p.get("url")) in unresearched
    ]
    return out[: int(limit)]


def capture_blurb(url: str, blurb: str) -> dict[str, Any]:
    """Atomic 'capture this for Briefly': writes ``blurb`` as the bookmark's
    description, adds the ``_brief`` tag, and clears ``toread``. Preserves
    the existing title and any other tags. Pinboard has no patch endpoint,
    so this is fetch → merge → ``posts/add`` with ``replace=yes``.

    Returns ``{result_code, pinboard_url, tags, replaced}``. If the bookmark
    isn't in Jamie's Pinboard yet, returns ``{error: "not bookmarked"}`` —
    Linky only captures items already in the queue.
    """
    existing = posts_get(url)
    posts = existing.get("posts") or []
    if not posts:
        return {"error": f"{url} isn't bookmarked on Pinboard yet — nothing to capture"}
    post = posts[0]
    title = post.get("description", "") or url  # Pinboard's "description" is the title
    tags = [t for t in (post.get("tags") or "").split() if t and t != "toread"]
    if BRIEF_TAG not in tags:
        tags.append(BRIEF_TAG)
    shared = (post.get("shared", "yes") != "no")
    res = posts_add(
        url=url,
        title=title,
        description=str(blurb or ""),
        tags=" ".join(tags),
        toread=False,
        shared=shared,
        replace=True,
    )
    logger.info("pinboard: capture_blurb url=%s tags=%s result=%s", url, tags, res.get("result_code"))
    return {
        "result_code": res.get("result_code"),
        "pinboard_url": res.get("pinboard_url") or bookmark_url(url),
        "tags": tags,
        "replaced": res.get("result_code") == "done",
    }


def archive_search(query: str, k: int = 8, *, scan: int = 1000) -> list[dict[str, Any]]:
    """Substring search across Jamie's *whole* Pinboard archive (not just
    the unread pile). Fetches up to ``scan`` bookmarks via ``/posts/all``
    and filters on title / description / tags. Returns up to ``k``
    :func:`normalize_post` records, newest first."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    raw = posts_all(results=int(scan))
    hits: list[dict[str, Any]] = []
    for post in raw:
        hay = " ".join(
            str(post.get(f, "") or "") for f in ("description", "extended", "tags", "href")
        ).lower()
        if needle in hay:
            hits.append(normalize_post(post))
            if len(hits) >= int(k):
                break
    return hits


def posts_update() -> str:
    """Most recent bookmark mutation timestamp (ISO-8601, UTC).

    Cheap freshness gate — call this before paying the 5-minute toll on
    ``/posts/all`` to confirm the unread queue actually changed since
    the last fetch.
    """
    params = {"auth_token": _token(), "format": "json"}
    resp = _get("/posts/update", params)
    data = resp.json() or {}
    return str(data.get("update_time", ""))


def posts_get(url: str) -> dict[str, Any]:
    """Lookup an exact URL in Jamie's bookmarks.

    Returns the raw Pinboard payload: ``{date, user, posts: [...]}``.
    ``posts`` is empty if Jamie hasn't saved this URL. ``meta=yes`` so
    callers see the change-detection signature.
    """
    params = {
        "auth_token": _token(),
        "format": "json",
        "url": url,
        "meta": "yes",
    }
    resp = _get("/posts/get", params)
    return resp.json() or {}


def posts_suggest(url: str) -> dict[str, list[str]]:
    """Tag suggestions for ``url`` — both site-wide popular and personal recs.

    Returns ``{popular: [...], recommended: [...]}``. Pinboard returns a
    list of two single-key dicts; we flatten to the conventional shape.
    """
    params = {"auth_token": _token(), "format": "json", "url": url}
    resp = _get("/posts/suggest", params)
    raw = resp.json() or []
    out: dict[str, list[str]] = {"popular": [], "recommended": []}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        for key in ("popular", "recommended"):
            if key in entry:
                value = entry[key] or []
                if isinstance(value, list):
                    out[key] = [str(t) for t in value]
    return out


def posts_dates(tag: str | None = None) -> dict[str, int]:
    """Bookmark counts per day across the whole archive.

    Returns ``{YYYY-MM-DD: count, ...}``. Cheap rhythm signal.

    Note: Pinboard's ``/posts/dates`` returns an empty body when called
    with ``format=json`` (long-standing API quirk). We request XML and
    parse it, since the shape is trivial.
    """
    params: dict[str, Any] = {"auth_token": _token()}
    if tag:
        params["tag"] = tag
    resp = _get("/posts/dates", params)
    # Imported lazily to keep bs4 a soft dep.
    from xml.etree import ElementTree as ET
    root = ET.fromstring(resp.text)
    return {
        elem.attrib["date"]: int(elem.attrib.get("count", "0"))
        for elem in root.findall("date")
    }


def tags_get() -> list[dict[str, Any]]:
    """Full tag inventory across every bookmark.

    Returns ``[{tag, count}, ...]`` sorted by count descending. Distinct
    from ``tag_summary``, which only scans the unread pile.
    """
    params = {"auth_token": _token(), "format": "json"}
    resp = _get("/tags/get", params)
    data = resp.json() or {}
    items = [
        {"tag": str(tag), "count": int(count)}
        for tag, count in data.items()
    ]
    items.sort(key=lambda r: r["count"], reverse=True)
    return items


def posts_add(
    url: str,
    title: str,
    *,
    description: str = "",
    tags: str = "",
    toread: bool = True,
    shared: bool = True,
    replace: bool = False,
) -> dict[str, Any]:
    """Save ``url`` to Jamie's Pinboard. Mutating.

    Defaults are conservative: ``replace=no`` so we never silently
    overwrite an existing bookmark, and ``toread=yes`` so saves land in
    Jamie's unread review queue rather than the public feed of read
    items.

    Returns ``{result_code, pinboard_url}``. ``result_code`` is "done"
    on success or e.g. "item already exists" on a duplicate-with-replace=no.
    """
    params: dict[str, Any] = {
        "auth_token": _token(),
        "format": "json",
        "url": url,
        "description": title,  # Pinboard's "description" is the title
        "extended": description,
        "tags": tags,
        "toread": "yes" if toread else "no",
        "shared": "yes" if shared else "no",
        "replace": "yes" if replace else "no",
    }
    resp = _get("/posts/add", params)
    data = resp.json() or {}
    result_code = str(data.get("result_code", ""))
    logger.info(
        "pinboard: posts/add url=%s result=%s replace=%s toread=%s",
        url, result_code, replace, toread,
    )
    return {
        "result_code": result_code,
        "pinboard_url": bookmark_url(url),
    }


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
        "shared": post.get("shared", "") == "yes",
        "hash": post.get("hash", ""),
        "meta": post.get("meta", ""),
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
    logger.info("pinboard__popular: %d items from %s", len(out), POPULAR_FEED)
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
