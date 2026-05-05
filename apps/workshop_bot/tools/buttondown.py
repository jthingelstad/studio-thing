"""Buttondown REST client for workshop bot.

The newsletter publishing pipeline already uses Buttondown
(see ``pipeline/content/fetch_emails.py``); this client carries the
subscriber-event surface Marky needs without dragging in the heavier
content/email pipeline. Auth via ``BUTTONDOWN_API_KEY``.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Iterator, Optional

import requests

API_BASE = "https://api.buttondown.com/v1"

logger = logging.getLogger("workshop.buttondown")


def _headers() -> dict[str, str]:
    key = os.environ.get("BUTTONDOWN_API_KEY")
    if not key:
        raise RuntimeError("BUTTONDOWN_API_KEY is not set")
    return {"Authorization": f"Token {key}"}


def _hash_email(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()[:32]


def _iter_subscribers(
    *,
    page_size: int = 100,
    type_filter: Optional[str] = None,
    ordering: Optional[str] = None,
    max_pages: int = 20,
) -> Iterator[dict[str, Any]]:
    """Yield subscriber records, paginated. Caps at ``max_pages`` for safety."""
    url: Optional[str] = f"{API_BASE}/subscribers"
    params: dict[str, Any] = {"page_size": page_size}
    if type_filter:
        params["type"] = type_filter
    if ordering:
        params["ordering"] = ordering
    pages = 0
    while url and pages < max_pages:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json() or {}
        for row in data.get("results", []) or []:
            yield row
        url = data.get("next")
        params = {}  # next URL already carries pagination params
        pages += 1


def recent_subscribers(
    *,
    limit: int = 25,
    type_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Most recently created subscribers (newest first), trimmed for the tool surface."""
    out: list[dict[str, Any]] = []
    for row in _iter_subscribers(
        page_size=min(limit, 100),
        type_filter=type_filter,
        ordering="-creation_date",
    ):
        out.append(_normalize(row))
        if len(out) >= limit:
            break
    return out


def recent_unsubscribes(*, limit: int = 25) -> list[dict[str, Any]]:
    """Most recently unsubscribed/churned subscribers."""
    out: list[dict[str, Any]] = []
    for row in _iter_subscribers(
        page_size=min(limit, 100),
        type_filter="unsubscribed",
        ordering="-creation_date",
    ):
        out.append(_normalize(row))
        if len(out) >= limit:
            break
    return out


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    """Trim a subscriber record to the fields safe to expose to an LLM.

    Critically, raw email addresses never leave this function — only
    a stable short hash, a coarse domain hint, and the operational
    fields (type, source, dates).
    """
    email = row.get("email_address") or row.get("email") or ""
    domain = email.split("@", 1)[1] if "@" in email else ""
    return {
        "id": row.get("id"),
        "email_hash": _hash_email(email),
        "email_domain": domain.lower(),
        "type": row.get("type"),
        "source": row.get("source"),
        "tags": row.get("tags") or [],
        "created_at": row.get("creation_date") or row.get("created_at"),
        "subscriber_type": row.get("subscriber_type"),
        "metadata": row.get("metadata") or {},
    }


def counts() -> dict[str, int]:
    """Top-level subscriber counts. Cheap — uses page_size=1 like the
    site stats pipeline does."""
    out: dict[str, int] = {}
    for label, params in (
        ("total", {"page_size": 1}),
        ("premium", {"page_size": 1, "type": "premium"}),
        ("unsubscribed", {"page_size": 1, "type": "unsubscribed"}),
    ):
        try:
            resp = requests.get(
                f"{API_BASE}/subscribers", headers=_headers(), params=params, timeout=15
            )
            resp.raise_for_status()
            out[label] = int((resp.json() or {}).get("count", 0))
        except requests.RequestException as exc:
            logger.warning("buttondown counts(%s) failed: %s", label, exc)
            out[label] = -1
    return out
