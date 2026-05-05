"""SQLite wrapper for the workshop bot.

Connections are short-lived (per-call) — sqlite3 connections aren't safe to
share across asyncio tasks, and the workload is tiny enough that the
per-call overhead doesn't matter.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

REPO = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO / "apps" / "workshop_bot" / "data" / "workshop.db"
SCHEMA_PATH = REPO / "apps" / "workshop_bot" / "db" / "schema.sql"

logger = logging.getLogger("workshop.db")


def db_path() -> Path:
    raw = os.environ.get("WORKSHOP_DB_PATH")
    if raw:
        return Path(raw) if Path(raw).is_absolute() else REPO / raw
    return DEFAULT_DB_PATH


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def run_migrations() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
    logger.info("workshop.db ready at %s", db_path())


def insert_agent_output(
    agent_name: str,
    output_type: str,
    content: str,
    metadata: Optional[dict[str, Any]] = None,
    related_issue: Optional[int] = None,
    status: str = "ready",
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO agent_outputs "
            "(agent_name, output_type, content, metadata, status, related_issue) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                agent_name,
                output_type,
                content,
                json.dumps(metadata) if metadata else None,
                status,
                related_issue,
            ),
        )
        return int(cur.lastrowid or 0)


def upsert_link_candidate(
    url: str,
    title: Optional[str],
    description: Optional[str],
    pinboard_tags: Optional[str],
    pinboard_added: Optional[str],
    linky_summary: Optional[str] = None,
    linky_themes: Optional[list[str]] = None,
    archive_resonance: Optional[str] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO link_candidates "
            "(url, title, description, pinboard_tags, pinboard_added, "
            " linky_summary, linky_themes, archive_resonance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET "
            "  title=excluded.title, "
            "  description=excluded.description, "
            "  pinboard_tags=excluded.pinboard_tags, "
            "  pinboard_added=excluded.pinboard_added, "
            "  linky_summary=COALESCE(excluded.linky_summary, link_candidates.linky_summary), "
            "  linky_themes=COALESCE(excluded.linky_themes, link_candidates.linky_themes), "
            "  archive_resonance=COALESCE(excluded.archive_resonance, link_candidates.archive_resonance)",
            (
                url,
                title,
                description,
                pinboard_tags,
                pinboard_added,
                linky_summary,
                json.dumps(linky_themes) if linky_themes else None,
                archive_resonance,
            ),
        )
        return int(cur.lastrowid or 0)


def recent_link_candidates(limit: int = 30) -> list[dict[str, Any]]:
    """Return the most recently added/updated link_candidates rows."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT url, title, description, pinboard_tags, pinboard_added, "
            "       linky_summary, linky_themes, status "
            "FROM link_candidates "
            "ORDER BY COALESCE(pinboard_added, created_at) DESC "
            "LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- agent memory ----------

NOTE_KINDS = ("preference", "observation", "todo", "context", "theme")


def insert_agent_note(
    *,
    agent_name: str,
    kind: str,
    content: str,
    key: Optional[str] = None,
    related_issue: Optional[int] = None,
    expires_at: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO agent_notes "
            "(agent_name, kind, key, content, related_issue, expires_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                agent_name,
                kind,
                key,
                content,
                related_issue,
                expires_at,
                json.dumps(metadata) if metadata else None,
            ),
        )
        return int(cur.lastrowid or 0)


def query_agent_notes(
    *,
    agent_name: Optional[str] = None,
    kind: Optional[str] = None,
    query: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return notes ordered newest-first. Filter by agent, kind, or text match."""
    sql_parts = [
        "SELECT id, agent_name, kind, key, content, related_issue, status, "
        "       created_at, expires_at "
        "FROM agent_notes WHERE 1=1"
    ]
    params: list[Any] = []
    if agent_name:
        sql_parts.append("AND agent_name = ?")
        params.append(agent_name)
    if kind:
        sql_parts.append("AND kind = ?")
        params.append(kind)
    if not include_resolved:
        sql_parts.append("AND status = 'active'")
    if query:
        sql_parts.append("AND (content LIKE ? OR key LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
    sql_parts.append(
        "AND (expires_at IS NULL OR expires_at > datetime('now')) "
        "ORDER BY created_at DESC LIMIT ?"
    )
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()
    return [dict(r) for r in rows]


def update_agent_note_status(note_id: int, status: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE agent_notes SET status = ? WHERE id = ?",
            (status, note_id),
        )
        return cur.rowcount > 0


# ---------- subscriber events (Marky) ----------

def upsert_subscriber_event(
    *,
    external_id: str,
    email_hash: str,
    event_type: str,
    event_date: str,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Returns True if this is a new (external_id, event_type) pair."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscriber_events_seen "
            "(external_id, email_hash, event_type, event_date, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                external_id,
                email_hash,
                event_type,
                event_date,
                json.dumps(metadata) if metadata else None,
            ),
        )
        return cur.rowcount > 0


def recent_subscriber_events(
    *, limit: int = 30, event_type: Optional[str] = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT external_id, email_hash, event_type, event_date, created_at "
        "FROM subscriber_events_seen"
    )
    params: list[Any] = []
    if event_type:
        sql += " WHERE event_type = ?"
        params.append(event_type)
    sql += " ORDER BY event_date DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


class AgentRun:
    """Context manager that opens an agent_runs row and closes it with the result."""

    def __init__(self, agent_name: str, trigger: str) -> None:
        self.agent_name = agent_name
        self.trigger = trigger
        self.run_id: Optional[int] = None
        self._t0 = 0.0
        self.records_written = 0
        self.error: Optional[str] = None

    def __enter__(self) -> "AgentRun":
        self._t0 = time.monotonic()
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs (agent_name, trigger, status) "
                "VALUES (?, ?, 'pending')",
                (self.agent_name, self.trigger),
            )
            self.run_id = int(cur.lastrowid or 0)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = int((time.monotonic() - self._t0) * 1000)
        if exc is not None:
            status = "error"
            self.error = f"{exc_type.__name__}: {exc}" if self.error is None else self.error
        else:
            status = "success"
        with connect() as conn:
            conn.execute(
                "UPDATE agent_runs SET status=?, duration_ms=?, error=?, "
                "records_written=?, ended_at=datetime('now') WHERE id=?",
                (status, duration_ms, self.error, self.records_written, self.run_id),
            )
        # Don't suppress exceptions
