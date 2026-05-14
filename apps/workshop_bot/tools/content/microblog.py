"""micro.blog client — Jamie's posts for the issue's Journal section.

Uses the Micropub source query (`GET {MICROBLOG_MICROPUB_URL}?q=source`,
``Authorization: Bearer {MICROBLOG_API_KEY}``), which returns posts as
mf2-JSON with ``properties.content`` carrying the **native markdown Jamie
wrote** (a string for markdown-authored posts — the common case — or an
``{html: …}`` / ``{markdown: …}`` dict otherwise). No round-trip through
rendered HTML. ``MICROBLOG_API_KEY`` is required — there is no fallback;
if micro.blog is unreachable, ``journal.fill`` degrades to a placeholder
line.

micro.blog embeds photo uploads as ``<img src="https://www.thingelstad.com/uploads/…">``
HTML tags inside the markdown; those references are rehosted (downloaded,
resized for email, copied into the issue workspace) by ``tools.journal_images``
at ``update-draft`` time — not here.

``posts_in_window`` returns the in-window posts (``q=source`` is capped at
~100 recent posts, far more than any week needs), oldest first.
"""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger("workshop.microblog")

DEFAULT_MICROPUB_URL = "https://micro.blog/micropub"
# The Weekly Thing's issue cadence is Jamie's local day; a post's "issue
# date" is the date in this zone (which is also what micro.blog bakes into
# the post URL slug — that's the primary signal we use).
_LOCAL_TZ = ZoneInfo("America/Chicago")
_URL_DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"


def micropub_url() -> str:
    return (os.environ.get("MICROBLOG_MICROPUB_URL") or DEFAULT_MICROPUB_URL).strip()


def _api_key() -> str:
    return (os.environ.get("MICROBLOG_API_KEY") or "").strip()


# --- date parsing / windowing ---

def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def published_local(raw: Any) -> datetime | None:
    """Parse a ``published`` timestamp and convert it to Jamie's local zone
    (``America/Chicago``). micro.blog emits ``published`` in UTC; everything
    reader-facing (the Journal date/time labels, windowing) wants it local.
    A naive (tz-less) value is returned unchanged."""
    dt = _parse_dt(raw)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_LOCAL_TZ)
    return dt


def _post_date(post: dict) -> date | None:
    """The post's "issue date" — Jamie's local date. micro.blog's URL slug
    (``/YYYY/MM/DD/…``) is that date verbatim; fall back to converting the
    ``published`` timestamp into the local zone."""
    m = _URL_DATE_RE.search(str(post.get("url") or ""))
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    dt = published_local(post.get("published"))
    return dt.date() if dt else None


def _first(props: dict, *keys: str):
    """First value of the first present mf2 property in ``keys``."""
    for k in keys:
        v = props.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if v not in (None, "", [], {}):
            return v
    return None


# --- HTML → markdown-ish, only for {html:…}-content posts (rare) ---

_TAG_RE = re.compile(r"<[^>]+>")
_A_RE = re.compile(
    r'<a\b[^>]*?href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE
)
_BLOCK_END_RE = re.compile(r"</(p|div|li|blockquote|h[1-6]|ul|ol)>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


_IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
_IMG_SRC_RE = re.compile(r'src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_IMG_ALT_RE = re.compile(r'alt\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _img_to_md(tag: str) -> str:
    src_m = _IMG_SRC_RE.search(tag)
    if not src_m:
        return ""
    alt_m = _IMG_ALT_RE.search(tag)
    return f"![{(alt_m.group(1).strip() if alt_m else '')}]({src_m.group(1).strip()})"


def html_to_markdownish(content_html: str) -> str:
    """Best-effort HTML → markdown for an HTML-authored micro.blog post:
    keeps links, turns ``<img>`` into ``![alt](src)`` (tools.journal_images
    rehosts the src later), drops other tags, collapses block tags to
    paragraph breaks. Only used on the ``{html:…}``-content path."""
    if not content_html:
        return ""
    s = content_html
    s = _A_RE.sub(lambda m: f"[{_TAG_RE.sub('', m.group(2)).strip()}]({m.group(1).strip()})", s)
    s = _IMG_TAG_RE.sub(lambda m: _img_to_md(m.group(0)), s)
    s = _BR_RE.sub("\n", s)
    s = _BLOCK_END_RE.sub("\n\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _content_to_markdown(content: Any) -> str:
    """Coerce an mf2 ``content`` value to markdown. micro.blog returns the
    raw markdown *string* for markdown-authored posts (with ``<img>`` tags
    embedded — left intact here); an ``{html:…}`` / ``{markdown:…}`` dict
    otherwise."""
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


# --- the source query ---

def _source_posts() -> list[dict[str, Any]]:
    """All posts from the Micropub ``q=source`` query, as
    ``[{url, title, published, content_md}]``. Skips drafts. Raises on a
    missing key or any transport/parse error."""
    token = _api_key()
    if not token:
        raise RuntimeError("MICROBLOG_API_KEY is required (no fallback)")
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
        raise ValueError("micro.blog Micropub q=source returned no `items`")
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        props = it.get("properties") or {}
        status = _first(props, "post-status")
        if status and str(status).lower() not in ("published", "publish"):
            continue  # drafts etc.
        out.append({
            "url": str(_first(props, "url") or "").strip(),
            "title": str(_first(props, "name") or "").strip(),
            "published": str(_first(props, "published", "publish-date") or ""),
            "content_md": _content_to_markdown(props.get("content")),
        })
    logger.info("microblog: q=source -> %d published posts", len(out))
    return out


def posts_in_window(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """micro.blog posts whose authored date falls in ``(start_date, end_date]``
    (calendar dates, ``YYYY-MM-DD``), oldest first. Each result:
    ``{url, title, published (ISO), content_md}`` — ``content_md`` is the
    native markdown Jamie wrote (with photo ``<img>`` tags still embedded;
    those are rehosted at update-draft time). Raises if the Micropub call
    fails — ``journal.fill`` catches that and degrades to a placeholder line.
    """
    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    posts = []
    for p in _source_posts():
        d = _post_date(p)
        if d is not None and sd < d <= ed:
            posts.append(p)
    posts.sort(key=lambda r: r.get("published") or "")
    logger.info("microblog: %d posts in window %s..%s", len(posts), start_date, end_date)
    return posts
