"""Tinylytics REST client.

Wraps the public ``https://tinylytics.app/api/v1/sites/{site_id}/...``
surface. Auth via ``TINYLYTICS_API_KEY`` (Bearer); the numeric site ID
via ``TINYLYTICS_SITE_ID``.

Note: ``TINYLYTICS_SITE_UID`` (hash-style, e.g. ``a2YQr3ZMqkySNYSwz4uF``)
is the public browser-script identifier and is NOT used here — the API
returns 500 if you pass it as the path id.

Reference: ``https://tinylytics.app/docs/api.md``.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Any, Optional

import requests

API_BASE = "https://tinylytics.app/api/v1"
DEFAULT_TIMEOUT = 15
MAX_WINDOW_DAYS = 730  # API hard limit per docs

logger = logging.getLogger("workshop.systems.tinylytics")


def _config() -> tuple[str, str]:
    key = os.environ.get("TINYLYTICS_API_KEY")
    site_id = os.environ.get("TINYLYTICS_SITE_ID")
    if not key or not site_id:
        raise RuntimeError(
            "TINYLYTICS_API_KEY and TINYLYTICS_SITE_ID must both be set"
        )
    return key, site_id


def _request(path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
    key, site_id = _config()
    url = f"{API_BASE}/sites/{site_id}{path}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        params=params or {},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _date_window(days: int) -> dict[str, str]:
    """ISO date strings for the trailing window (UTC)."""
    days = max(1, min(int(days), MAX_WINDOW_DAYS))
    end = _dt.datetime.now(_dt.timezone.utc).date()
    start = end - _dt.timedelta(days=days)
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def total_hits(days: int = 7) -> int:
    """Total hit count over the trailing window."""
    params: dict[str, Any] = {**_date_window(days), "per_page": 1}
    data = _request("/hits", params=params)
    return int(((data or {}).get("pagination") or {}).get("total_count") or 0)


def top_pages(days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    """Top pages by views over the trailing window.

    Each entry has ``path``, ``views``, ``unique_views``.
    """
    params: dict[str, Any] = {
        **_date_window(days),
        "grouped": "true",
        "group_by": "path",
        "per_page": min(int(limit), 1000),
    }
    data = _request("/hits", params=params)
    return data.get("grouped_hits") or []


def referrers(days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    """Top external referrers over the trailing window.

    Each entry has ``referrer`` (may be ``None`` for direct or empty
    string for unknown) and ``hit_count``.
    """
    params: dict[str, Any] = {
        **_date_window(days),
        "grouped": "true",
        "group_by": "referrer",
        "per_page": min(int(limit), 1000),
    }
    data = _request("/hits", params=params)
    return data.get("grouped_hits") or []


def summary(days: int = 7) -> dict[str, Any]:
    """One-call trailing-window summary: total hits + top pages + top referrers.

    Each sub-call is wrapped so a single upstream hiccup doesn't blank
    the whole report.
    """
    out: dict[str, Any] = {"days": int(days)}
    for label, fn in (
        ("total_hits", lambda: total_hits(days)),
        ("top_pages", lambda: top_pages(days, limit=10)),
        ("referrers", lambda: referrers(days, limit=10)),
    ):
        try:
            out[label] = fn()
        except requests.RequestException as exc:
            logger.warning("tinylytics %s failed: %s", label, exc)
            out[label] = {"error": f"{type(exc).__name__}: {exc}"}
        except RuntimeError as exc:
            out[label] = {"error": str(exc)}
    return out
