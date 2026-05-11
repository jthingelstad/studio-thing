"""micro.blog client — Jamie's posts for the issue's Journal section.

Two paths, in order of preference:

1. **Micropub source query** (`GET {MICROBLOG_MICROPUB_URL}?q=source`,
   ``Authorization: Bearer {MICROBLOG_API_KEY}``) — returns posts as
   mf2-JSON, with ``properties.content`` carrying the **native markdown
   Jamie wrote** for markdown-authored posts (the common case). This is
   the one we want: no markdown → HTML → markdown round-trip.
2. **Public JSON Feed** (`MICROBLOG_FEED_URL`, default
   ``https://www.thingelstad.com/feed.json``) — fallback when there's no
   API key or the Micropub call fails. Its ``content_html`` is the
   *rendered* HTML, so we run a best-effort HTML → markdown-ish pass.

``posts_in_window`` filters either source by the post's authored date.

NOTE for the operator: the JSON-feed default assumes Jamie's micro.blog
hostname is ``www.thingelstad.com``; the Micropub default is the
micro.blog hosted endpoint. Set ``MICROBLOG_FEED_URL`` /
``MICROBLOG_MICROPUB_URL`` if either is wrong.
"""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import date, datetime
from typing import Any

import requests

logger = logging.getLogger("workshop.microblog")

DEFAULT_FEED_URL = "https://www.thingelstad.com/feed.json"
DEFAULT_MICROPUB_URL = "https://micro.blog/micropub"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"


def feed_url() -> str:
    return (os.environ.get("MICROBLOG_FEED_URL") or DEFAULT_FEED_URL).strip()


def micropub_url() -> str:
    return (os.environ.get("MICROBLOG_MICROPUB_URL") or DEFAULT_MICROPUB_URL).strip()


def _api_key() -> str:
    return (os.environ.get("MICROBLOG_API_KEY") or "").strip()


# --- date parsing ---

def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _in_window(published_iso: str, sd: date, ed: date) -> bool:
    dt = _parse_dt(published_iso)
    if dt is None:
        return False
    return sd < dt.date() <= ed


def _first(props: dict, *keys: str):
    """First value of the first present mf2 property in ``keys``."""
    for k in keys:
        v = props.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if v not in (None, "", [], {}):
            return v
    return None


# --- HTML → markdown-ish (JSON-feed fallback, and Micropub {html:...} content) ---

_TAG_RE = re.compile(r"<[^>]+>")
_A_RE = re.compile(
    r'<a\b[^>]*?href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE
)
_IMG_RE = re.compile(r'<img\b[^>]*?src=["\']([^"\']*)["\'][^>]*?/?>', re.IGNORECASE)
_BLOCK_END_RE = re.compile(r"</(p|div|li|blockquote|h[1-6]|ul|ol)>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def html_to_markdownish(content_html: str) -> str:
    """Best-effort HTML → markdown for micro.blog post bodies: keeps links
    and images, collapses block tags to paragraph breaks, drops the rest.
    Only used on the JSON-feed fallback path (or HTML-authored posts)."""
    if not content_html:
        return ""
    s = content_html
    s = _A_RE.sub(lambda m: f"[{_TAG_RE.sub('', m.group(2)).strip()}]({m.group(1).strip()})", s)
    s = _IMG_RE.sub(lambda m: f"\n\n![]({m.group(1).strip()})\n\n", s)
    s = _BR_RE.sub("\n", s)
    s = _BLOCK_END_RE.sub("\n\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _content_to_markdown(content: Any) -> str:
    """Coerce an mf2 ``content`` value to markdown. micro.blog returns the
    raw markdown *string* for markdown-authored posts; an ``{html: ...}``
    (or ``{markdown: ...}``) dict otherwise."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if isinstance(content.get("markdown"), str):
            return content["markdown"].strip()
        if isinstance(content.get("html"), str):
            return html_to_markdownish(content["html"])
        if isinstance(content.get("value"), str):
            return content["value"].strip()
        return ""
    if isinstance(content, list) and content:
        return _content_to_markdown(content[0])
    return ""


# --- the two source paths ---

def _micropub_source_posts() -> list[dict[str, Any]]:
    """All posts from the Micropub ``q=source`` query, as
    ``[{url, title, published, content_md}]``. Raises on transport/parse
    errors and on missing auth — the caller falls back to the JSON feed."""
    token = _api_key()
    if not token:
        raise RuntimeError("MICROBLOG_API_KEY not set")
    resp = requests.get(
        micropub_url(),
        params={"q": "source"},
        headers={"Authorization": f"Bearer {token}", "User-Agent": _UA},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items") if isinstance(data, dict) else None
    if items is None:
        raise ValueError("Micropub q=source returned no `items`")
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        props = it.get("properties") or {}
        status = _first(props, "post-status")
        if status and str(status).lower() not in ("published", "publish"):
            continue  # drafts etc.
        content_md = _content_to_markdown(props.get("content"))
        published = _first(props, "published", "publish-date") or ""
        out.append({
            "url": str(_first(props, "url") or "").strip(),
            "title": str(_first(props, "name") or "").strip(),
            "published": str(published),
            "content_md": content_md,
        })
    logger.info("microblog: Micropub q=source -> %d posts", len(out))
    return out


def _jsonfeed_posts() -> list[dict[str, Any]]:
    """All posts from the public JSON Feed, as ``[{url, title, published,
    content_md}]`` (content from ``content_html`` via html_to_markdownish,
    or ``content_text`` if there's no HTML)."""
    resp = requests.get(feed_url(), timeout=_TIMEOUT, headers={"User-Agent": _UA})
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"micro.blog feed at {feed_url()} did not return a JSON object")
    out: list[dict[str, Any]] = []
    for it in data.get("items") or []:
        if not isinstance(it, dict):
            continue
        body = html_to_markdownish(it.get("content_html") or "") or (it.get("content_text") or "").strip()
        out.append({
            "url": str(it.get("url") or "").strip(),
            "title": str(it.get("title") or "").strip(),
            "published": str(it.get("date_published") or it.get("date_modified") or ""),
            "content_md": body,
        })
    logger.info("microblog: JSON feed -> %d posts", len(out))
    return out


def posts_in_window(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """micro.blog posts whose authored date falls in
    ``(start_date, end_date]`` (calendar dates, ``YYYY-MM-DD``), oldest
    first. Each result: ``{url, title, published (ISO), content_md}``.

    Prefers the Micropub source query (native markdown) when
    ``MICROBLOG_API_KEY`` is set; falls back to the public JSON Feed
    (HTML → markdown-ish) otherwise or on failure. Raises only if *both*
    paths fail — ``journal.fill`` catches that and degrades to a
    placeholder line.
    """
    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    ed = datetime.strptime(end_date, "%Y-%m-%d").date()

    posts: list[dict[str, Any]] | None = None
    if _api_key():
        try:
            posts = _micropub_source_posts()
        except Exception as exc:  # noqa: BLE001
            logger.warning("microblog: Micropub source failed (%s) — falling back to JSON feed", exc)
            posts = None
    if posts is None:
        posts = _jsonfeed_posts()

    windowed = [p for p in posts if _in_window(p.get("published", ""), sd, ed)]
    windowed.sort(key=lambda r: r.get("published") or "")
    logger.info("microblog: %d posts in window %s..%s", len(windowed), start_date, end_date)
    return windowed
