"""Feedbin starred-items RSS poller.

Jamie stars an article in Feedbin and it lands in the
``feedbin-ingest`` job's queue. This module is the read-only side:
fetch the starred feed, parse the items, hand back a list of dicts.
The ingest job decides what to do with them (create Pinboard bookmarks
+ dedup via ``feedbin_starred_seen``).

The feed URL is private — set ``FEEDBIN_STARRED_FEED_URL`` in ``.env``.

The feed shape is RSS 2.0 with ``dc:creator`` on each item:
``<item><title>…</title><link>…</link><description>…</description>
<pubDate>…</pubDate><dc:creator>…</dc:creator>
<guid isPermaLink="false">https://feedbin.me/entries/…</guid></item>``.
We use the GUID as the stable identifier so re-stars don't double-ingest.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger("workshop.feedbin")

_DC = "{http://purl.org/dc/elements/1.1/}"
_TIMEOUT = 20.0
_UA = "WeeklyThing-WorkshopBot/1.0"


class FeedbinError(RuntimeError):
    """Raised on network / parse failures the ingest job should surface."""


def feed_url() -> Optional[str]:
    """Return the configured Feedbin starred-items feed URL, or ``None``
    if the env var isn't set."""
    raw = (os.environ.get("FEEDBIN_STARRED_FEED_URL") or "").strip()
    return raw or None


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def parse_feed(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse the Feedbin starred-items XML into a list of item dicts.

    Each dict carries ``guid``, ``url``, ``title``, ``description``,
    ``pub_date``, ``creator``. Order matches the feed (Feedbin lists
    newest first). Items without a GUID are skipped — we have no stable
    way to dedup them.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise FeedbinError(f"feedbin: XML parse failed: {exc}") from exc

    channel = root.find("channel")
    if channel is None:
        # Some feeds carry items directly under the root. Try both.
        channel = root

    items: list[dict[str, Any]] = []
    for el in channel.findall("item"):
        guid_el = el.find("guid")
        guid = _text(guid_el)
        if not guid:
            continue
        url = _text(el.find("link"))
        if not url:
            continue
        title = _text(el.find("title"))
        description = _text(el.find("description"))
        pub_date = _text(el.find("pubDate"))
        creator = _text(el.find(f"{_DC}creator"))
        items.append({
            "guid": guid,
            "url": url,
            "title": title,
            "description": description,
            "pub_date": pub_date,
            "creator": creator,
        })
    return items


def fetch_starred(*, url: Optional[str] = None, timeout: float = _TIMEOUT) -> list[dict[str, Any]]:
    """Fetch the configured Feedbin starred feed and return parsed items.

    Raises :class:`FeedbinError` if the feed URL isn't set, the request
    fails, or the response isn't well-formed XML. The ingest job catches
    the exception, logs it, and PASSes — a Feedbin hiccup shouldn't fail
    the cron.
    """
    target = (url or feed_url() or "").strip()
    if not target:
        raise FeedbinError("FEEDBIN_STARRED_FEED_URL is not set")
    try:
        resp = requests.get(
            target,
            timeout=timeout,
            headers={"User-Agent": _UA, "Accept": "application/rss+xml,application/xml,text/xml"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FeedbinError(f"feedbin: fetch failed: {exc}") from exc
    return parse_feed(resp.content)
