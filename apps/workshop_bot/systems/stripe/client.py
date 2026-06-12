"""Stripe REST client — read-only donation surface.

Auth via ``STRIPE_API_KEY`` (already required by the build pipeline;
the same key is reused here). The PII rule for the workshop bot is
enforced inside this module: donor name + email never reach the model
in raw form — only a stable short hash and an email-domain hint.

Donations come through a Stripe Payment Link
(``support.json``'s ``stripe_donate_url``). Whether the Payment Link
sets ``ref`` on Checkout Session metadata — and therefore whether
that ``ref`` propagates onto the resulting charges — depends on
Stripe Dashboard configuration; ``donations_by_ref`` returns empty
until that wiring is in place.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
from collections import Counter, defaultdict
from typing import Any, Iterator, Optional

import stripe

logger = logging.getLogger("workshop.systems.stripe")


# ---------- auth + helpers ----------

def _configure() -> None:
    """Set ``stripe.api_key`` from env. Raises if unset."""
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise RuntimeError("STRIPE_API_KEY is not set")
    stripe.api_key = key


def _hash(value: Any) -> str:
    return hashlib.sha256((str(value or "")).strip().lower().encode("utf-8")).hexdigest()[:32]


def _email_domain(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[1].lower()


def _epoch_to_iso(secs: Optional[int]) -> Optional[str]:
    if secs is None:
        return None
    return _dt.datetime.fromtimestamp(int(secs), tz=_dt.timezone.utc).isoformat()


def _normalize_charge(charge: Any) -> dict[str, Any]:
    """Return the LLM-safe shape for one Stripe Charge.

    Donor name + email are hashed; email domain is exposed as a coarse
    cohort hint. ``metadata`` is passed through verbatim — by spec,
    donors don't put PII there; ``ref`` is the field we look for.
    """
    bd = charge.get("billing_details") or {}
    email = bd.get("email")
    name = bd.get("name")
    metadata = charge.get("metadata") or {}
    return {
        "id": charge.get("id"),
        "amount_cents": charge.get("amount"),
        "amount_usd": (charge.get("amount") or 0) / 100,
        "currency": charge.get("currency"),
        "created_at": _epoch_to_iso(charge.get("created")),
        "status": charge.get("status"),
        "paid": charge.get("paid"),
        "donor_hash": _hash(email or name or ""),
        "donor_domain": _email_domain(email),
        "ref_tag": metadata.get("ref") or metadata.get("ref_tag"),
        "metadata": dict(metadata),
        "payment_intent": charge.get("payment_intent"),
    }


def _iter_charges(
    *,
    created_gte: Optional[int] = None,
    page_size: int = 100,
    max_pages: int = 20,
    succeeded_only: bool = True,
) -> Iterator[dict[str, Any]]:
    """Yield charge records (newest first) up to ``max_pages``.

    Filters to ``status == 'succeeded'`` by default — donations only.
    """
    _configure()
    params: dict[str, Any] = {"limit": min(int(page_size), 100)}
    if created_gte is not None:
        params["created"] = {"gte": int(created_gte)}
    pages = 0
    starting_after: Optional[str] = None
    while pages < max_pages:
        if starting_after:
            params["starting_after"] = starting_after
        page = stripe.Charge.list(**params)
        data = page.get("data") or []
        for raw in data:
            if succeeded_only and (raw.get("status") != "succeeded" or not raw.get("paid")):
                continue
            yield raw
        if not page.get("has_more"):
            return
        if not data:
            return
        starting_after = data[-1].get("id")
        pages += 1


# ---------- tool surfaces ----------

def balance() -> dict[str, Any]:
    """Available + pending balance (USD only) in dollars."""
    _configure()
    bal = stripe.Balance.retrieve()
    available_cents = sum(
        int(e.get("amount") or 0)
        for e in (bal.get("available") or [])
        if e.get("currency") == "usd"
    )
    pending_cents = sum(
        int(e.get("amount") or 0)
        for e in (bal.get("pending") or [])
        if e.get("currency") == "usd"
    )
    return {
        "available_usd": available_cents / 100,
        "pending_usd": pending_cents / 100,
        "total_usd": (available_cents + pending_cents) / 100,
    }


def recent_donations(*, limit: int = 25) -> list[dict[str, Any]]:
    """Last N successful charges, normalized.

    Donor name + email are hashed; raw PII never appears in the result.
    """
    out: list[dict[str, Any]] = []
    for raw in _iter_charges(page_size=min(int(limit), 100)):
        out.append(_normalize_charge(raw))
        if len(out) >= int(limit):
            break
    return out


def donations_by_month(*, months: int = 12) -> dict[str, Any]:
    """Trailing N months of donations, aggregated by month.

    Returns ``{months: [{month: 'YYYY-MM', count, total_usd}]}``.
    """
    months = max(int(months), 1)
    cutoff = _dt.datetime.now(_dt.timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ) - _dt.timedelta(days=31 * (months - 1))
    cutoff = cutoff.replace(day=1)
    counts: dict[str, int] = defaultdict(int)
    cents: dict[str, int] = defaultdict(int)
    for raw in _iter_charges(created_gte=int(cutoff.timestamp())):
        created = raw.get("created")
        if created is None:
            continue
        when = _dt.datetime.fromtimestamp(int(created), tz=_dt.timezone.utc)
        key = f"{when.year:04d}-{when.month:02d}"
        counts[key] += 1
        cents[key] += int(raw.get("amount") or 0)
    months_sorted = sorted(counts.keys())
    return {
        "months": [
            {
                "month": m,
                "count": counts[m],
                "total_usd": cents[m] / 100,
            }
            for m in months_sorted
        ],
    }


def donations_by_ref(*, days: int = 90) -> dict[str, Any]:
    """Aggregate donations by ``metadata.ref`` over the trailing window.

    Returns ``{days, total_count, total_usd, by_ref: {ref: {count, total_usd}}}``.
    Charges without a ``ref`` (or ``ref_tag``) are bucketed under
    ``"(no-ref)"`` so the model can see the size of the unattributed
    cohort. Returns empty buckets if the donate flow doesn't currently
    set ``ref`` on charge metadata.
    """
    days = max(int(days), 1)
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    counter: Counter[str] = Counter()
    cents_by_ref: dict[str, int] = defaultdict(int)
    total_count = 0
    total_cents = 0
    for raw in _iter_charges(created_gte=int(cutoff.timestamp())):
        metadata = raw.get("metadata") or {}
        ref = metadata.get("ref") or metadata.get("ref_tag") or "(no-ref)"
        counter[ref] += 1
        cents_by_ref[ref] += int(raw.get("amount") or 0)
        total_count += 1
        total_cents += int(raw.get("amount") or 0)
    by_ref = {
        ref: {"count": counter[ref], "total_usd": cents_by_ref[ref] / 100}
        for ref in counter
    }
    return {
        "days": days,
        "total_count": total_count,
        "total_usd": total_cents / 100,
        "by_ref": by_ref,
    }


def year_to_date() -> dict[str, Any]:
    """Current-calendar-year donation totals + the configured nonprofit.

    Reads ``apps/site/_data/support.json`` for the current nonprofit
    label so the model can produce a single coherent reply without a
    second tool round-trip.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    year_start = _dt.datetime(now.year, 1, 1, tzinfo=_dt.timezone.utc)
    count = 0
    cents = 0
    for raw in _iter_charges(created_gte=int(year_start.timestamp())):
        count += 1
        cents += int(raw.get("amount") or 0)
    avg = (cents / count / 100) if count else 0.0
    return {
        "year": now.year,
        "count": count,
        "total_usd": cents / 100,
        "average_usd": round(avg, 2),
        "current_nonprofit": _current_nonprofit_short_name(),
    }


# ---------- support.json passthrough ----------

_SUPPORT_PATH = (
    "apps/site/_data/support.json"  # relative to repo root; resolved below
)


def _current_nonprofit_short_name() -> Optional[str]:
    import json
    from pathlib import Path

    repo = Path(__file__).resolve().parents[4]
    path = repo / _SUPPORT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cur = (data or {}).get("current") or {}
    return cur.get("short_name") or cur.get("nonprofit")
