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
        _apply_column_migrations(conn)
    logger.info("workshop.db ready at %s", db_path())


# SQLite has no "ADD COLUMN IF NOT EXISTS". For columns added after the
# initial table creation, run ALTER TABLE and tolerate the "duplicate
# column" error so a fresh DB and a long-lived DB both end up identical.
_COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    # (table, column, full ADD COLUMN clause)
    ("thingy_tokens", "profile", "ALTER TABLE thingy_tokens ADD COLUMN profile TEXT"),
    ("thingy_tokens", "last_welcomed_at",
     "ALTER TABLE thingy_tokens ADD COLUMN last_welcomed_at TEXT"),
)


def _apply_column_migrations(conn: sqlite3.Connection) -> None:
    for table, column, sql in _COLUMN_MIGRATIONS:
        try:
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})")
            }
        except sqlite3.Error:
            continue
        if column in existing:
            continue
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            # Column was added concurrently by another process; ignore.
            pass


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


# ---------- Linky: popular feed dedup + to-read research ----------

def filter_unseen_popular(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only items whose URL isn't yet in pinboard_popular_seen."""
    if not items:
        return []
    urls = [it.get("url", "") for it in items if it.get("url")]
    if not urls:
        return []
    placeholders = ",".join("?" * len(urls))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT url FROM pinboard_popular_seen WHERE url IN ({placeholders})",
            urls,
        ).fetchall()
    seen = {r["url"] for r in rows}
    return [it for it in items if it.get("url") and it["url"] not in seen]


def mark_popular_seen(
    items: list[dict[str, Any]],
    *,
    judged: Optional[dict[str, tuple[bool, str]]] = None,
) -> int:
    """Insert ``items`` into pinboard_popular_seen (no-op on conflict).

    ``judged`` is an optional ``url -> (interesting?, note)`` mapping
    from the LLM filter, persisted alongside the row so future audits
    can see what Linky judged interesting vs not.
    """
    n = 0
    judged = judged or {}
    with connect() as conn:
        for it in items:
            url = it.get("url")
            if not url:
                continue
            interesting_flag: Optional[int] = None
            note: Optional[str] = None
            if url in judged:
                ok, note = judged[url]
                interesting_flag = 1 if ok else 0
            cur = conn.execute(
                "INSERT OR IGNORE INTO pinboard_popular_seen "
                "(url, title, posted_by, judged_interesting, judgment_note) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    url,
                    it.get("title"),
                    it.get("posted_by"),
                    interesting_flag,
                    note,
                ),
            )
            if cur.rowcount:
                n += 1
    return n


def filter_unresearched_urls(urls: list[str]) -> list[str]:
    """Return only URLs not yet present in pinboard_research_done."""
    if not urls:
        return []
    placeholders = ",".join("?" * len(urls))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT url FROM pinboard_research_done WHERE url IN ({placeholders})",
            urls,
        ).fetchall()
    done = {r["url"] for r in rows}
    return [u for u in urls if u not in done]


def mark_url_researched(
    *,
    url: str,
    title: Optional[str],
    summary: str,
    confidence: Optional[str] = None,
    fit_note: Optional[str] = None,
) -> bool:
    """Insert a research record. Returns True if newly inserted."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pinboard_research_done "
            "(url, title, summary, confidence, fit_note) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, title, summary, confidence, fit_note),
        )
        return cur.rowcount > 0


# ---------- Thingy bridge ----------

def get_thingy_token(discord_user_id: str) -> Optional[dict[str, Any]]:
    """Cached session token + profile for a Discord user, if any."""
    with connect() as conn:
        row = conn.execute(
            "SELECT discord_user_id, token, expires_at, issued_at, profile, "
            "       last_welcomed_at "
            "FROM thingy_tokens WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
    if row is None:
        return None
    out = dict(row)
    raw_profile = out.get("profile")
    if isinstance(raw_profile, str) and raw_profile:
        try:
            out["profile"] = json.loads(raw_profile)
        except json.JSONDecodeError:
            out["profile"] = None
    return out


def upsert_thingy_token(
    *,
    discord_user_id: str,
    token: str,
    expires_at: int,
    profile: Optional[dict[str, Any]] = None,
) -> None:
    """Insert/refresh a token row, optionally storing the auth response's
    `profile` snapshot. ``last_welcomed_at`` is preserved across upserts."""
    profile_json = json.dumps(profile) if profile is not None else None
    with connect() as conn:
        conn.execute(
            "INSERT INTO thingy_tokens "
            "(discord_user_id, token, expires_at, profile) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(discord_user_id) DO UPDATE SET "
            "  token = excluded.token, "
            "  expires_at = excluded.expires_at, "
            "  issued_at = datetime('now'), "
            "  profile = COALESCE(excluded.profile, thingy_tokens.profile)",
            (discord_user_id, token, int(expires_at), profile_json),
        )


def mark_thingy_welcomed(discord_user_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE thingy_tokens SET last_welcomed_at = datetime('now') "
            "WHERE discord_user_id = ?",
            (discord_user_id,),
        )


def insert_thingy_request(
    *,
    discord_user_id: str,
    discord_message_id: str,
    question: str,
    status: str = "pending",
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO thingy_requests "
            "(discord_user_id, discord_message_id, question, status) "
            "VALUES (?, ?, ?, ?)",
            (discord_user_id, discord_message_id, question, status),
        )
        return int(cur.lastrowid or 0)


def update_thingy_request(
    request_row_id: int,
    *,
    status: Optional[str] = None,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
    request_id: Optional[str] = None,
    bot_response_message_id: Optional[str] = None,
) -> None:
    fields: list[str] = []
    params: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if error is not None:
        fields.append("error = ?")
        params.append(error)
    if duration_ms is not None:
        fields.append("duration_ms = ?")
        params.append(int(duration_ms))
    if request_id is not None:
        fields.append("request_id = ?")
        params.append(request_id)
    if bot_response_message_id is not None:
        fields.append("bot_response_message_id = ?")
        params.append(bot_response_message_id)
    if not fields:
        return
    params.append(request_row_id)
    with connect() as conn:
        conn.execute(
            f"UPDATE thingy_requests SET {', '.join(fields)} WHERE id = ?",
            params,
        )


def lookup_thingy_request_by_response(
    bot_response_message_id: str,
) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, discord_user_id, discord_message_id, "
            "       bot_response_message_id, request_id, question, status "
            "FROM thingy_requests "
            "WHERE bot_response_message_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (bot_response_message_id,),
        ).fetchone()
    return dict(row) if row else None


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
    """Return the currently active issue window, or None if none set."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       set_at, set_by "
            "FROM issue_windows WHERE is_active = 1 LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_issue_window(issue_number: int) -> Optional[dict[str, Any]]:
    """Return one issue window by number (active or not)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, set_at, set_by "
            "FROM issue_windows WHERE issue_number = ?",
            (int(issue_number),),
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


# ---------- job locks (single-asset serialization for the jobs pipeline) ----------


def _pid_alive(pid: int) -> bool:
    """True if ``pid`` looks like a live process. A nonexistent pid is
    dead; a permission error means the process exists but isn't ours to
    signal (won't happen in a single-user deployment, but treat as live)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def acquire_job_lock(*, asset: str, job: str, pid: int) -> Optional[dict[str, Any]]:
    """Try to lock ``asset`` for ``job``.

    Returns ``None`` on success. If the asset is already held by a *live*
    process, returns that lock row as a dict (the caller surfaces an
    "already running" message). A lock held by a dead pid is stale —
    deleted and re-acquired. (workshop_bot is single-process, so a live
    holder is genuinely another running job; a dead holder is a leftover
    from a prior crashed instance, since a restart gets a new pid.)
    """
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT asset, job, started_at, pid FROM job_locks WHERE asset = ?",
                (asset,),
            ).fetchone()
            if row is not None:
                if _pid_alive(row["pid"]):
                    conn.execute("ROLLBACK")
                    return dict(row)
                conn.execute("DELETE FROM job_locks WHERE asset = ?", (asset,))
            conn.execute(
                "INSERT INTO job_locks (asset, job, started_at, pid) "
                "VALUES (?, ?, datetime('now'), ?)",
                (asset, job, int(pid)),
            )
            conn.execute("COMMIT")
            return None
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_job_lock(asset: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM job_locks WHERE asset = ?", (asset,))
        return cur.rowcount > 0


def list_job_locks() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT asset, job, started_at, pid FROM job_locks ORDER BY started_at"
        ).fetchall()
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
