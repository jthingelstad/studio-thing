"""Buttondown REST client.

Canonical implementation for the Buttondown system module — wraps the
public REST API at ``https://api.buttondown.com/v1`` with auth via
``BUTTONDOWN_API_KEY``. The PII rule for the workshop bot is enforced
here: raw email addresses never leave this module — only a stable
short hash and a coarse domain hint.

The legacy ``apps/workshop_bot/tools/buttondown.py`` is a thin re-export
shim so any existing call sites keep working during the redesign
phasing.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
from collections import Counter
from typing import Any, Iterator, Optional

import requests

API_BASE = "https://api.buttondown.com/v1"

logger = logging.getLogger("workshop.systems.buttondown")


# ---------- low-level HTTP ----------

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
        params = {}
        pages += 1


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    """Trim a subscriber record to the LLM-safe shape.

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


# ---------- subscriber surfaces ----------

def recent_subscribers(
    *,
    limit: int = 25,
    type_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
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


def counts() -> dict[str, int]:
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


def subscriber_sources(*, days: int = 30, max_pages: int = 20) -> dict[str, Any]:
    """Aggregate ``source`` attribution counts over a trailing window.

    Iterates the most recent subscribers (newest first) and aggregates
    the ``source`` field per record. Stops when records fall outside
    the trailing window or after ``max_pages`` fetches, whichever comes
    first.
    """
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=int(days))
    counter: Counter[str] = Counter()
    seen = 0
    for row in _iter_subscribers(
        page_size=100,
        ordering="-creation_date",
        max_pages=max_pages,
    ):
        created = _parse_dt(row.get("creation_date"))
        if created is not None and created < cutoff:
            break
        source = (row.get("source") or "unknown") or "unknown"
        counter[source] += 1
        seen += 1
    return {
        "days": int(days),
        "subscribers_seen": seen,
        "by_source": dict(counter.most_common()),
    }


def subscriber_growth(*, days: int = 30, max_pages: int = 20) -> dict[str, Any]:
    """Net subscriber delta over the trailing window plus a cohort-by-source breakdown.

    Counts new subscribers and unsubscribes whose date falls within
    ``days`` of now. Returns ``{added, churned, net, by_source}``.
    """
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=int(days))
    added = 0
    by_source: Counter[str] = Counter()
    for row in _iter_subscribers(
        page_size=100,
        ordering="-creation_date",
        max_pages=max_pages,
    ):
        created = _parse_dt(row.get("creation_date"))
        if created is not None and created < cutoff:
            break
        added += 1
        by_source[(row.get("source") or "unknown") or "unknown"] += 1
    churned = 0
    for row in _iter_subscribers(
        page_size=100,
        type_filter="unsubscribed",
        ordering="-creation_date",
        max_pages=max_pages,
    ):
        when = _parse_dt(
            row.get("unsubscription_date")
            or row.get("churn_date")
            or row.get("creation_date")
        )
        if when is not None and when < cutoff:
            break
        churned += 1
    return {
        "days": int(days),
        "added": added,
        "churned": churned,
        "net": added - churned,
        "by_source": dict(by_source.most_common()),
    }


# ---------- email surfaces ----------

_EMAIL_LIST_FIELDS = (
    "id",
    "subject",
    "publish_date",
    "creation_date",
    "status",
    "email_type",
    "absolute_url",
    "slug",
)


def list_recent_emails(*, limit: int = 25) -> list[dict[str, Any]]:
    """Most recent sent emails — id, subject, send timestamps, recipients,
    opens, clicks, unsubscriptions. No body."""
    params = {"page_size": min(int(limit), 100), "ordering": "-publish_date"}
    resp = requests.get(
        f"{API_BASE}/emails", headers=_headers(), params=params, timeout=20
    )
    resp.raise_for_status()
    data = resp.json() or {}
    out: list[dict[str, Any]] = []
    for row in (data.get("results") or [])[: int(limit)]:
        out.append(_email_summary(row))
    return out


def email_engagement(*, email_id: str) -> dict[str, Any]:
    """Per-email engagement counters for one sent email.

    Note: Buttondown's public API does NOT expose a per-link breakdown
    of clicks; ``clicks`` is a single integer over the whole email. The
    return shape is the analytics dict (recipients, deliveries, opens,
    clicks, unsubscriptions, subscriptions, replies, plus bookkeeping)
    plus the email's subject + publish date for context.
    """
    if not email_id or not isinstance(email_id, str):
        return {"error": "email_id is required"}
    resp = requests.get(
        f"{API_BASE}/emails/{email_id}", headers=_headers(), timeout=15
    )
    if resp.status_code == 404:
        return {"error": f"no email with id {email_id!r}"}
    resp.raise_for_status()
    email = resp.json() or {}
    analytics = email.get("analytics") or {}
    return {
        "email_id": email.get("id"),
        "subject": email.get("subject"),
        "publish_date": email.get("publish_date"),
        "status": email.get("status"),
        "engagement": analytics,
        "note": (
            "Buttondown does not expose a per-link click breakdown; "
            "`engagement.clicks` is the total click count for the issue."
        ),
    }


def _email_summary(row: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {f: row.get(f) for f in _EMAIL_LIST_FIELDS}
    a = row.get("analytics") or {}
    if isinstance(a, dict) and a:
        summary["engagement"] = {
            "recipients": a.get("recipients"),
            "deliveries": a.get("deliveries"),
            "opens": a.get("opens"),
            "clicks": a.get("clicks"),
            "unsubscriptions": a.get("unsubscriptions"),
            "subscriptions": a.get("subscriptions"),
            "replies": a.get("replies"),
        }
    return summary


# ---------- helpers ----------

def _parse_dt(raw: Any) -> Optional[_dt.datetime]:
    if not raw:
        return None
    if isinstance(raw, _dt.datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=_dt.timezone.utc)
    s = str(raw)
    # Buttondown emits ISO with trailing Z; fromisoformat in 3.11+ handles Z.
    try:
        dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt
