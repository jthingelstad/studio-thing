"""micro.blog client — Jamie's posts from his public JSON Feed.

Jamie's personal site (``www.thingelstad.com``) is micro.blog-hosted; the
JSON Feed at ``MICROBLOG_FEED_URL`` (default
``https://www.thingelstad.com/feed.json``) is the Journal source — no auth.
We fetch the first page (most recent ~N posts, plenty for a 7-day issue
window) and filter by the post's authored date.

The journal-photo S3 re-hosting that the iOS Shortcuts do today is a
separate concern; ``update-draft`` renders the journal with whatever image
URLs each post carries (micro.blog CDN URLs).

NOTE for the operator: the default feed URL assumes Jamie's micro.blog
hostname is ``www.thingelstad.com``. If that's wrong, set
``MICROBLOG_FEED_URL`` in ``.env``.
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
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"


def feed_url() -> str:
    return (os.environ.get("MICROBLOG_FEED_URL") or DEFAULT_FEED_URL).strip()


def _fetch_feed() -> dict[str, Any]:
    url = feed_url()
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _UA})
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"micro.blog feed at {url} did not return a JSON object")
    return data


# --- lightweight HTML -> markdown for post bodies ---

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
    Good enough for a regenerable draft — create-final is where Eddy
    curates."""
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


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _post_date(item: dict[str, Any]) -> date | None:
    dt = _parse_dt(item.get("date_published") or item.get("date_modified"))
    return dt.date() if dt else None


def posts_in_window(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """micro.blog posts whose authored date falls in
    ``(start_date, end_date]`` (calendar dates, ``YYYY-MM-DD``), oldest
    first.

    Each result: ``{url, title, published (ISO), content_md}``. Raises on a
    transport/parse error — the caller (journal.fill) catches and degrades
    to a placeholder line.
    """
    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    data = _fetch_feed()
    items = data.get("items") or []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        d = _post_date(it)
        if d is None or not (sd < d <= ed):
            continue
        dt = _parse_dt(it.get("date_published") or it.get("date_modified"))
        body = html_to_markdownish(it.get("content_html") or "")
        if not body:
            body = (it.get("content_text") or "").strip()
        out.append(
            {
                "url": str(it.get("url") or ""),
                "title": str(it.get("title") or "").strip(),
                "published": dt.isoformat() if dt else str(it.get("date_published") or ""),
                "content_md": body,
            }
        )
    out.sort(key=lambda r: r.get("published") or "")
    logger.info("microblog: %d posts in window %s..%s", len(out), start_date, end_date)
    return out
