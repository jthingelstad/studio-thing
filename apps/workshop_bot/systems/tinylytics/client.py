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


def leaderboard(
    *, prefix: Optional[str] = None, limit: int = 20
) -> list[dict[str, Any]]:
    """All-time top paths for the site.

    No date window — the leaderboard is cached server-side and ignores
    ``start_date``/``end_date``. ``prefix`` is a partial path filter
    (case-insensitive prefix-ish), e.g. ``/archive/``. Each entry has
    ``path``, ``total_hits``, ``unique_hits``, ``percentage``.
    """
    params: dict[str, Any] = {"per_page": min(int(limit), 1000)}
    if prefix:
        params["path"] = prefix
    data = _request("/leaderboard", params=params)
    return data.get("leaderboard") or []


def user_journeys(days: int = 7, limit: int = 20) -> dict[str, Any]:
    """Visitor journey rows over the trailing window.

    Each row has ``visitor_hash``, ``page_count``, ``duration_minutes``,
    ``pages``, ``entry_page``, ``exit_page``, ``referrer``, ``country``,
    ``browser``. Useful for "what do people read after they land from X".
    """
    params: dict[str, Any] = {
        **_date_window(days),
        "per_page": min(int(limit), 1000),
    }
    data = _request("/user_journeys", params=params)
    return {
        "user_journeys": data.get("user_journeys") or [],
        "summary": data.get("summary") or {},
    }


def sources(
    days: int = 30, limit: int = 20, max_pages: int = 10
) -> dict[str, Any]:
    """Aggregate the ``source`` field on raw hits over a trailing window.

    Tinylytics auto-extracts ``?ref=<x>`` and ``?utm_source=<x>`` from
    landing URLs into the per-hit ``source`` field. The API does NOT
    support ``group_by=source`` (returns HTTP 400), so this paginates
    raw hits and aggregates client-side. Each hit costs ~1 request per
    1000 hits in the window.

    This is the right tool for "where did the DenseDiscovery / LinkedIn /
    etc. traffic land this week" — `referrers` answers a different
    question (HTTP Referer header, e.g. linkedin.com).

    Returns ``{days, hits_seen, with_source, by_source, by_path,
    samples}`` where ``by_source`` maps source → count, ``by_path``
    maps path → count for hits that carried a source, and ``samples``
    has up to 5 example URLs for spot-checking.
    """
    window = _date_window(days)
    by_source: dict[str, int] = {}
    by_path: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    seen = 0
    with_source = 0
    for page in range(1, int(max_pages) + 1):
        params: dict[str, Any] = {**window, "per_page": 1000, "page": page}
        data = _request("/hits", params=params)
        hits = data.get("hits") or []
        if not hits:
            break
        for row in hits:
            seen += 1
            src = (row.get("source") or "").strip()
            if not src:
                continue
            with_source += 1
            by_source[src] = by_source.get(src, 0) + 1
            path = row.get("path") or "/"
            by_path[path] = by_path.get(path, 0) + 1
            if len(samples) < 5:
                samples.append(
                    {
                        "source": src,
                        "url": row.get("url"),
                        "path": path,
                        "created_at": row.get("created_at"),
                    }
                )
        pagination = data.get("pagination") or {}
        if int(pagination.get("current_page") or page) >= int(
            pagination.get("total_pages") or page
        ):
            break
    sorted_sources = sorted(by_source.items(), key=lambda kv: -kv[1])
    sorted_paths = sorted(by_path.items(), key=lambda kv: -kv[1])
    return {
        "days": int(days),
        "hits_seen": seen,
        "with_source": with_source,
        "by_source": dict(sorted_sources[: int(limit)]),
        "by_path": dict(sorted_paths[: int(limit)]),
        "samples": samples,
    }


def kudos(days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    """Recent kudos (heart-button taps) over the trailing window.

    Each entry has ``id``, ``uid``, ``path``, ``created_at``. The kudos
    button is wired on per-issue archive pages, so most paths look like
    ``/archive/<n>/``.
    """
    params: dict[str, Any] = {
        **_date_window(days),
        "per_page": min(int(limit), 1000),
    }
    data = _request("/kudos", params=params)
    return data.get("kudos") or []


def insights() -> dict[str, Any]:
    """Latest daily AI insights for the site (subscription-gated).

    Returns ``{insights: [...]}`` where each entry has
    ``insights_for_date``, ``summary``, ``signals`` (page breakouts,
    referrer surges, traffic shifts) and ``recommendations``. Generated
    daily at ~01:00 in the account timezone; needs ≥10 hits in the last
    7 days. Returns the upstream payload unchanged.
    """
    return _request("/insights")


def uptime() -> dict[str, Any]:
    """Uptime monitor + SSL/domain expiry (subscription-gated).

    Returns ``{monitor: {...}, downtimes: [...]}`` with current uptime
    %, last/next check, last status code, SSL expiry, and domain expiry.
    """
    return _request("/uptime")


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
