"""Latest-published-issue lookup from ``weekly.thingelstad.com/feed.xml``.

Marky's jobs derive their context from the public RSS/Atom feed — the
most recently *published* issue, independent of the in-flight one. The
``rss-check`` scheduled job uses this to detect a new ship and auto-fire
``promotion-prep``. The feed is the trigger only; the content Marky works
on is the issue's ``buttondown.md`` in the S3 workspace.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger("workshop.rss")

DEFAULT_FEED_URL = "https://weekly.thingelstad.com/feed.xml"
_ATOM = "{http://www.w3.org/2005/Atom}"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"

_ARCHIVE_RE = re.compile(r"/archive/(\d+)/?")
_TITLE_NUM_RE = re.compile(r"weekly thing\s+#?(\d+)", re.IGNORECASE)


def feed_url() -> str:
    return (os.environ.get("WEEKLY_THING_FEED_URL") or DEFAULT_FEED_URL).strip()


def _issue_number(*candidates: Optional[str]) -> Optional[int]:
    for c in candidates:
        if not c:
            continue
        m = _ARCHIVE_RE.search(str(c))
        if m:
            return int(m.group(1))
    for c in candidates:
        if not c:
            continue
        m = _TITLE_NUM_RE.search(str(c))
        if m:
            return int(m.group(1))
    return None


def _entry_text(entry, *local_names: str) -> Optional[str]:
    for ln in local_names:
        el = entry.find(f"{_ATOM}{ln}")
        if el is not None and el.text:
            return el.text
    return None


def latest_published_issue() -> Optional[dict[str, Any]]:
    """``{number, url, title, ship_date}`` for the highest-numbered entry
    in the Atom feed, or None if the feed has no parseable issue entries.
    Raises on a transport/parse error — callers degrade."""
    resp = requests.get(feed_url(), timeout=_TIMEOUT, headers={"User-Agent": _UA})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    best: Optional[dict[str, Any]] = None
    for entry in root.findall(f"{_ATOM}entry"):
        link_el = entry.find(f"{_ATOM}link")
        href = link_el.get("href") if link_el is not None else None
        eid = _entry_text(entry, "id")
        title = _entry_text(entry, "title")
        n = _issue_number(href, eid, title)
        if n is None:
            continue
        updated = _entry_text(entry, "updated", "published")
        if best is None or n > best["number"]:
            best = {
                "number": n,
                "url": href or eid,
                "title": (title or "").strip(),
                "ship_date": ((updated or "")[:10] or None),
            }
    logger.info("rss: latest published issue = %s", best.get("number") if best else None)
    return best
