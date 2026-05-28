"""Goals (Patty's milestones) + campaigns (Marky's ad-placement ledger) (moved from store.py)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from .connection import connect


# ---------- goals (Patty's milestone progression) ----------


def get_active_goal() -> Optional[dict[str, Any]]:
    """The current goal — the row with ``achieved_at IS NULL`` — or None."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, target_kind, target_value, started_at, achieved_at, notes "
            "FROM goals WHERE achieved_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def recent_achieved_goals(limit: int = 3) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, target_kind, target_value, started_at, achieved_at, notes "
            "FROM goals WHERE achieved_at IS NOT NULL ORDER BY achieved_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_goal(*, target_kind: str, target_value: int, started_at: Optional[str] = None,
                notes: Optional[str] = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO goals (target_kind, target_value, started_at, notes) "
            "VALUES (?, ?, COALESCE(?, date('now')), ?)",
            (target_kind, int(target_value), started_at, notes),
        )
        return int(cur.lastrowid or 0)


def mark_goal_achieved(
    goal_id: int, *, achieved_at: Optional[str] = None, notes: Optional[str] = None
) -> bool:
    sets = ["achieved_at = COALESCE(?, date('now'))"]
    params: list[Any] = [achieved_at]
    if notes is not None:
        sets.append("notes = ?")
        params.append(notes)
    params.append(int(goal_id))
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE goals SET {', '.join(sets)} WHERE id = ? AND achieved_at IS NULL",
            params,
        )
        return cur.rowcount > 0


# ---------- campaigns (Marky's ad-placement ledger) ----------


_CAMPAIGN_COLUMNS = (
    "id, name, ref, url, platform, status, started_at, "
    "actual_signups, cost, copy, notes"
)


def insert_campaign(
    *,
    name: str,
    ref: str,
    url: Optional[str] = None,
    platform: Optional[str] = None,
    cost: Optional[float] = None,
    started_at: Optional[str] = None,
    copy: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """Insert a campaign. Returns False if a campaign with that name
    already exists (ON CONFLICT DO NOTHING). Status starts as 'live';
    flip to 'sunset' via :func:`set_campaign_status`. ``actual_signups``
    starts NULL — daily-metrics fills it on first poll."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO campaigns (name, ref, url, platform, status, "
            " started_at, cost, copy, notes) "
            "VALUES (?, ?, ?, ?, 'live', COALESCE(?, date('now')), ?, ?, ?) "
            "ON CONFLICT(name) DO NOTHING",
            (
                name,
                ref,
                url,
                platform,
                started_at,
                float(cost) if cost is not None else None,
                copy,
                notes,
            ),
        )
        return cur.rowcount > 0


def get_campaign(name: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def active_campaigns() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns "
            "WHERE status = 'live' ORDER BY started_at DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def active_campaigns_with_age() -> list[dict[str, Any]]:
    """Active campaigns annotated with ``days_running`` — used by
    ``build_marky_context``."""
    from datetime import datetime as _dt

    out: list[dict[str, Any]] = []
    today = _dt.now().date()
    for c in active_campaigns():
        days = None
        try:
            d = _dt.strptime(str(c.get("started_at"))[:10], "%Y-%m-%d").date()
            days = (today - d).days
        except (TypeError, ValueError):
            pass
        out.append({**c, "days_running": days})
    return out


def set_campaign_status(name: str, status: str) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE campaigns SET status = ? WHERE name = ?", (status, name))
        return cur.rowcount > 0


def set_campaign_copy(name: str, copy: Optional[str]) -> bool:
    """Set (or clear, with ``None``) the promo copy for a campaign.
    Returns False if no campaign with that name exists."""
    with connect() as conn:
        cur = conn.execute("UPDATE campaigns SET copy = ? WHERE name = ?", (copy, name))
        return cur.rowcount > 0


# Fields a campaign's row may be edited in place. ``name`` is immutable
# (FK target for campaign_metrics); ``id`` is the PK; ``status`` flips
# via set_campaign_status / campaign-sunset; ``actual_signups`` is
# bookkeeping (daily-metrics + set_actual_signups own writes).
CAMPAIGN_EDITABLE = ("ref", "url", "platform", "cost", "started_at", "copy", "notes")


def update_campaign(name: str, **changes: Any) -> Optional[dict[str, Any]]:
    """Update an existing campaign's editable fields in place. Only keys
    in :data:`CAMPAIGN_EDITABLE` with a non-``None`` value are written
    (``None`` means "leave it alone"); ``cost`` is coerced to float.
    Returns the updated row, or ``None`` if no campaign with that name
    exists."""
    fields: dict[str, Any] = {}
    for k, v in changes.items():
        if k not in CAMPAIGN_EDITABLE or v is None:
            continue
        if k == "cost":
            fields[k] = float(v)
        else:
            fields[k] = v
    if get_campaign(name) is None:
        return None
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with connect() as conn:
            conn.execute(f"UPDATE campaigns SET {sets} WHERE name = ?", [*fields.values(), name])
    return get_campaign(name)


def set_actual_signups(name: str, signups: int) -> bool:
    """Write the current attribution-realised signups count for a
    campaign. ``daily-metrics`` calls this after each poll; Marky can
    also call it via the ``campaigns__set_actual_signups`` agent tool
    for manual corrections or ad-hoc updates. Returns False if no
    campaign with that name exists."""
    n = int(signups)
    with connect() as conn:
        cur = conn.execute(
            "UPDATE campaigns SET actual_signups = ? WHERE name = ?",
            (n, name),
        )
        return cur.rowcount > 0


def insert_campaign_metric(*, campaign_name: str, signups: Optional[int]) -> int:
    """Append a metric row for the trajectory log. Traffic was dropped
    in migration 0013; signups is the KPI."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO campaign_metrics (campaign_name, signups) VALUES (?, ?)",
            (campaign_name,
             int(signups) if signups is not None else None),
        )
        return int(cur.lastrowid or 0)


def latest_campaign_metric(campaign_name: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, campaign_name, ran_at, signups FROM campaign_metrics "
            "WHERE campaign_name = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (campaign_name,),
        ).fetchone()
    return dict(row) if row else None


def list_campaigns(status: Optional[str] = None) -> list[dict[str, Any]]:
    """All campaigns ordered newest first. Optional ``status`` filter
    (``'live'`` / ``'sunset'`` / etc.); ``None`` returns every row.
    ``active_campaigns`` is the live-only fast path used by the daily
    poller; this is the read for ledgers + ad-hoc lookups."""
    sql = f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns"
    params: tuple[Any, ...] = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY started_at DESC, id DESC"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def recent_campaign_metrics(campaign_name: str, limit: int = 30) -> list[dict[str, Any]]:
    """Recent metric rows for one campaign, newest first. ``limit`` caps
    the trajectory length so a long-running campaign's poll history
    doesn't blow the caller's context window."""
    n = max(1, min(int(limit), 365))
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, campaign_name, ran_at, signups FROM campaign_metrics "
            "WHERE campaign_name = ? ORDER BY ran_at DESC, id DESC LIMIT ?",
            (campaign_name, n),
        ).fetchall()
    return [dict(r) for r in rows]


