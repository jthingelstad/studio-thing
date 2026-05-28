"""Issue windows + publishing-spine phase/cards (moved from store.py)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from .connection import connect


# ---------- issue windows (operator-set publishing schedule) ----------


def set_issue_window(
    *,
    issue_number: int,
    pub_date: str,
    end_date: str,
    start_date: str,
    day_count: int,
    set_by: Optional[str] = None,
) -> dict[str, Any]:
    """Atomically deactivate any current active window and upsert this
    issue's row as the new active window.

    Returns the resulting active row.
    """
    with connect() as conn:
        # The connection runs in autocommit (isolation_level=None) so
        # explicit BEGIN/COMMIT brackets the two writes into one
        # transaction — keeps the partial-unique-on-is_active index
        # from tripping mid-update.
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE issue_windows SET is_active = 0 WHERE is_active = 1"
            )
            conn.execute(
                "INSERT INTO issue_windows "
                "(issue_number, pub_date, end_date, start_date, day_count, "
                " is_active, set_at, set_by) "
                "VALUES (?, ?, ?, ?, ?, 1, datetime('now'), ?) "
                "ON CONFLICT(issue_number) DO UPDATE SET "
                "  pub_date=excluded.pub_date, "
                "  end_date=excluded.end_date, "
                "  start_date=excluded.start_date, "
                "  day_count=excluded.day_count, "
                "  is_active=1, "
                "  phase='build', "
                "  set_at=datetime('now'), "
                "  set_by=excluded.set_by",
                (issue_number, pub_date, end_date, start_date, day_count, set_by),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return get_active_issue_window() or {}


def get_active_issue_window() -> Optional[dict[str, Any]]:
    """Return the currently active issue window, or None if none set.
    Carries ``phase`` ('build' | 'publish') — the publishing-spine phase."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       phase, set_at, set_by "
            "FROM issue_windows WHERE is_active = 1 LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_issue_window(issue_number: int) -> Optional[dict[str, Any]]:
    """Return one issue window by number (active or not)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, phase, set_at, set_by "
            "FROM issue_windows WHERE issue_number = ?",
            (int(issue_number),),
        ).fetchone()
    return dict(row) if row else None


# ---------- publishing-spine phase + per-phase cards ----------

_ISSUE_PHASES = ("build", "publish")


def set_issue_phase(issue_number: int, phase: str) -> None:
    """Set an issue's publishing-spine phase ('build' | 'publish'). See
    docs/publishing-process.md — `mark built` flips build→publish."""
    if phase not in _ISSUE_PHASES:
        raise ValueError(f"phase must be one of {_ISSUE_PHASES}; got {phase!r}")
    with connect() as conn:
        conn.execute(
            "UPDATE issue_windows SET phase = ? WHERE issue_number = ?",
            (phase, int(issue_number)),
        )


def set_issue_card(issue_number: int, kind: str, *, message_id: int, channel_id: int) -> None:
    """Record (upsert) the persistent card for one phase of an issue, so the
    bot edits the same pinned message + re-finds it across restarts. ``kind``
    is 'build' | 'publish' | 'share'."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO issue_cards (issue_number, kind, message_id, channel_id, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(issue_number, kind) DO UPDATE SET "
            "  message_id = excluded.message_id, "
            "  channel_id = excluded.channel_id, "
            "  updated_at = datetime('now')",
            (int(issue_number), kind, int(message_id), int(channel_id)),
        )


def get_issue_card(issue_number: int, kind: str) -> Optional[dict[str, int]]:
    """Return ``{"message_id", "channel_id"}`` for an issue's phase card, or
    None if none recorded yet."""
    with connect() as conn:
        row = conn.execute(
            "SELECT message_id, channel_id FROM issue_cards "
            "WHERE issue_number = ? AND kind = ?",
            (int(issue_number), kind),
        ).fetchone()
    if not row:
        return None
    return {"message_id": int(row["message_id"]), "channel_id": int(row["channel_id"])}


def clear_issue_cards(issue_number: int, kind: Optional[str] = None) -> None:
    """Forget an issue's phase card(s). Pass ``kind`` to drop one; omit to
    drop all cards for the issue (used at put-to-bed)."""
    with connect() as conn:
        if kind is None:
            conn.execute("DELETE FROM issue_cards WHERE issue_number = ?", (int(issue_number),))
        else:
            conn.execute(
                "DELETE FROM issue_cards WHERE issue_number = ? AND kind = ?",
                (int(issue_number), kind),
            )


def get_latest_issue() -> Optional[dict[str, Any]]:
    """Return the most-recently-published issue (highest number) from the
    `issues` table — i.e. the issue currently in the **Share** phase. None if
    no issue has been filed yet."""
    with connect() as conn:
        row = conn.execute(
            "SELECT number, subject, slug, description, publish_date, absolute_url, "
            "       buttondown_id, audio_url, notable_count, briefly_count, link_count, filed_at "
            "FROM issues ORDER BY number DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def list_issue_windows(*, limit: int = 12) -> list[dict[str, Any]]:
    """Return recent issue windows, newest issue number first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, set_at, set_by "
            "FROM issue_windows ORDER BY issue_number DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


