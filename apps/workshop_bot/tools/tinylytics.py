"""Tinylytics REST client for Marky's engagement reporting.

Tinylytics' public API surface for site-owner reads is:

  GET https://tinylytics.app/api/v2/sites/{site_uid}/...

Authenticated with an ``Authorization: Bearer {api_key}`` header. The
exact endpoint shapes are documented at https://tinylytics.app/api —
this client wraps the most common reads and falls back gracefully
when an endpoint isn't recognized so a single rename upstream doesn't
stop the daily Marky job from running.

Set:
  TINYLYTICS_API_KEY   — full-access API key
  TINYLYTICS_SITE_UID  — the site UID (already in `.env.example`)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

API_BASE = "https://tinylytics.app/api/v2"
DEFAULT_TIMEOUT = 15

logger = logging.getLogger("workshop.tinylytics")


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
    """High-level site stats for the trailing ``days`` window."""
    return _request("/stats", params={"days": days})


def top_pages(days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    """Highest-traffic pages over the trailing window."""
    data = _request("/pages", params={"days": days, "limit": limit})
    return data if isinstance(data, list) else (data.get("pages") or [])


def referrers(days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    """Top external referrers over the trailing window."""
    data = _request("/referrers", params={"days": days, "limit": limit})
    return data if isinstance(data, list) else (data.get("referrers") or [])


def events(days: int = 7, limit: int = 50) -> list[dict[str, Any]]:
    """Recent custom events (e.g. ``support.donate``, ``support.membership``)."""
    data = _request("/events", params={"days": days, "limit": limit})
    return data if isinstance(data, list) else (data.get("events") or [])


def safe_summary(days: int = 7) -> dict[str, Any]:
    """Best-effort one-call summary that won't fail the whole agent run if
    one endpoint shape changes upstream.
    """
    out: dict[str, Any] = {"days": days}
    for label, fn in (("stats", stats), ("top_pages", top_pages), ("referrers", referrers), ("events", events)):
        try:
            out[label] = fn(days)
        except requests.RequestException as exc:
            logger.warning("tinylytics %s failed: %s", label, exc)
            out[label] = {"error": f"{type(exc).__name__}: {exc}"}
        except RuntimeError as exc:
            out[label] = {"error": str(exc)}
    return out
