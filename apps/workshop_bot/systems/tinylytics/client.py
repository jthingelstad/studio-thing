"""Tinylytics REST client.

Wraps the public ``https://tinylytics.app/api/v2/sites/{site_uid}/...``
surface. Auth via ``TINYLYTICS_API_KEY``; site UID via
``TINYLYTICS_SITE_UID``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

API_BASE = "https://tinylytics.app/api/v2"
DEFAULT_TIMEOUT = 15

logger = logging.getLogger("workshop.systems.tinylytics")


def _config() -> tuple[str, str]:
    key = os.environ.get("TINYLYTICS_API_KEY")
    uid = os.environ.get("TINYLYTICS_SITE_UID")
    if not key or not uid:
        raise RuntimeError(
            "TINYLYTICS_API_KEY and TINYLYTICS_SITE_UID must both be set"
        )
    return key, uid


def _request(path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
    key, uid = _config()
    url = f"{API_BASE}/sites/{uid}{path}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        params=params or {},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def stats(days: int = 7) -> dict[str, Any]:
    return _request("/stats", params={"days": days})


def top_pages(days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    data = _request("/pages", params={"days": days, "limit": limit})
    return data if isinstance(data, list) else (data.get("pages") or [])


def referrers(days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    data = _request("/referrers", params={"days": days, "limit": limit})
    return data if isinstance(data, list) else (data.get("referrers") or [])


def events(days: int = 7, limit: int = 50) -> list[dict[str, Any]]:
    data = _request("/events", params={"days": days, "limit": limit})
    return data if isinstance(data, list) else (data.get("events") or [])


def safe_summary(days: int = 7) -> dict[str, Any]:
    """Best-effort one-call summary that won't fail the whole agent run if
    one endpoint shape changes upstream.
    """
    out: dict[str, Any] = {"days": days}
    for label, fn in (
        ("stats", stats),
        ("top_pages", top_pages),
        ("referrers", referrers),
        ("events", events),
    ):
        try:
            out[label] = fn(days)
        except requests.RequestException as exc:
            logger.warning("tinylytics %s failed: %s", label, exc)
            out[label] = {"error": f"{type(exc).__name__}: {exc}"}
        except RuntimeError as exc:
            out[label] = {"error": str(exc)}
    return out


def ref_traffic(*, tag: str, days: int = 14) -> dict[str, Any]:
    """Aggregate page hits attributed to a ``?ref=<tag>`` URL.

    Wraps ``top_pages`` and filters entries whose path contains
    ``ref=<tag>`` (substring match). Sums hits across matching paths
    and returns the per-path breakdown so a campaign owner can see
    which destinations the tag drove traffic to.
    """
    if not isinstance(tag, str) or not tag.strip():
        return {"error": "tag is required"}
    needle = f"ref={tag.strip()}"
    try:
        pages = top_pages(days=days, limit=200)
    except Exception as exc:  # noqa: BLE001 — surface upstream failures cleanly
        return {"error": f"{type(exc).__name__}: {exc}"}
    hits_total = 0
    matches: list[dict[str, Any]] = []
    for entry in pages or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path") or entry.get("url") or entry.get("page") or ""
        if needle not in path:
            continue
        hits = entry.get("hits") or entry.get("count") or entry.get("views") or 0
        try:
            hits = int(hits)
        except (TypeError, ValueError):
            hits = 0
        matches.append({"path": path, "hits": hits})
        hits_total += hits
    return {
        "tag": tag.strip(),
        "days": days,
        "hits": hits_total,
        "paths": matches,
    }
