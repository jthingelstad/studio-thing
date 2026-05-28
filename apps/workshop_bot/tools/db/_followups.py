"""Follow-ups — agent/Jamie commitments, the targeted heartbeat (moved from store.py)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from .connection import connect


# ---------- follow-ups (agent commitments — the targeted heartbeat) ----------

FOLLOW_UP_PERSONAS = ("eddy", "linky", "marky", "patty")
FOLLOW_UP_KINDS = ("time", "issue")


def insert_follow_up(
    *,
    persona: str,
    trigger_kind: str,
    note: str,
    due_at: Optional[str] = None,
    trigger_issue: Optional[int] = None,
    channel_env: Optional[str] = None,
    created_by: Optional[str] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO follow_ups "
            "(persona, channel_env, trigger_kind, due_at, trigger_issue, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (persona, channel_env, trigger_kind, due_at,
             int(trigger_issue) if trigger_issue is not None else None, note, created_by),
        )
        return int(cur.lastrowid or 0)


def open_follow_ups(*, persona: Optional[str] = None) -> list[dict[str, Any]]:
    """Pending (not fired, not cancelled) follow-ups, oldest first."""
    sql = (
        "SELECT id, persona, channel_env, trigger_kind, due_at, trigger_issue, note, "
        "       created_by, created_at "
        "FROM follow_ups WHERE fired_at IS NULL AND cancelled_at IS NULL"
    )
    params: list[Any] = []
    if persona:
        sql += " AND persona = ?"
        params.append(persona)
    sql += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_follow_up(follow_up_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (int(follow_up_id),)).fetchone()
    return dict(row) if row else None


def due_follow_ups(*, now_iso: str, active_issue: Optional[int]) -> list[dict[str, Any]]:
    """Open follow-ups that are due now: time-based ones whose ``due_at`` has
    passed, plus issue-based ones once the active in-flight issue has reached
    their ``trigger_issue``. Oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, persona, channel_env, trigger_kind, due_at, trigger_issue, note, "
            "       created_by, created_at "
            "FROM follow_ups "
            "WHERE fired_at IS NULL AND cancelled_at IS NULL AND ("
            "  (trigger_kind = 'time' AND due_at IS NOT NULL AND due_at <= ?) OR "
            "  (trigger_kind = 'issue' AND trigger_issue IS NOT NULL AND ? IS NOT NULL AND trigger_issue <= ?)"
            ") ORDER BY created_at",
            (now_iso, active_issue, active_issue if active_issue is not None else -1),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_follow_up_fired(follow_up_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE follow_ups SET fired_at = datetime('now') "
            "WHERE id = ? AND fired_at IS NULL AND cancelled_at IS NULL",
            (int(follow_up_id),),
        )
        return cur.rowcount > 0


def cancel_follow_up(follow_up_id: int, *, persona: Optional[str] = None) -> bool:
    """Cancel an open follow-up. If ``persona`` is given, only cancels it when
    it belongs to that persona (so an agent can't cancel another's)."""
    sql = "UPDATE follow_ups SET cancelled_at = datetime('now') WHERE id = ? AND fired_at IS NULL AND cancelled_at IS NULL"
    params: list[Any] = [int(follow_up_id)]
    if persona:
        sql += " AND persona = ?"
        params.append(persona)
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount > 0


