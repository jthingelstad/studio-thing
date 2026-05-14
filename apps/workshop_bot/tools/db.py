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
    ("campaigns", "copy", "ALTER TABLE campaigns ADD COLUMN copy TEXT"),
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


# ---------- Thingy conversations (operator's view into reader Q&A) ----------

def insert_thingy_conversation(
    *,
    subscriber_hash: str,
    started_at: str,
    ended_at: str,
    turn_count: int,
    transcript: list[dict[str, Any]],
    turn_request_ids: list[str],
    source_issues: list[str],
    feedback: Optional[str],
    topic: Optional[str],
    assessment_md: Optional[str],
    posted_to_chatter_at: Optional[str] = None,
) -> int:
    """Insert one mirrored conversation; returns its local id."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO thingy_conversations "
            "(subscriber_hash, started_at, ended_at, turn_count, transcript_json, "
            " turn_request_ids_json, source_issues_json, feedback, topic, assessment_md, "
            " posted_to_chatter_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                subscriber_hash, started_at, ended_at, int(turn_count),
                json.dumps(transcript), json.dumps(list(turn_request_ids)),
                json.dumps(list(source_issues)), feedback, topic, assessment_md,
                posted_to_chatter_at,
            ),
        )
        return int(cur.lastrowid)


def mark_thingy_conversation_posted(conv_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE thingy_conversations SET posted_to_chatter_at = datetime('now') "
            "WHERE id = ? AND posted_to_chatter_at IS NULL",
            (conv_id,),
        )


def _hydrate_thingy_conversation(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for col, key in (("transcript_json", "transcript"),
                     ("turn_request_ids_json", "turn_request_ids"),
                     ("source_issues_json", "source_issues")):
        raw = d.pop(col, None)
        try:
            d[key] = json.loads(raw) if raw else []
        except (ValueError, TypeError):
            d[key] = []
    return d


def get_thingy_conversation(conv_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM thingy_conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    return _hydrate_thingy_conversation(row) if row else None


def recent_thingy_conversations(limit: int = 8) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM thingy_conversations ORDER BY ended_at DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_hydrate_thingy_conversation(r) for r in rows]


def latest_thingy_conversation_end() -> Optional[str]:
    """ISO timestamp of the newest mirrored turn — the watch watermark."""
    with connect() as conn:
        row = conn.execute(
            "SELECT MAX(ended_at) AS m FROM thingy_conversations"
        ).fetchone()
    return row["m"] if row and row["m"] else None


def seen_thingy_turn_request_ids() -> set[str]:
    """Every turn request_id already folded into a mirrored conversation."""
    seen: set[str] = set()
    with connect() as conn:
        rows = conn.execute(
            "SELECT turn_request_ids_json FROM thingy_conversations"
        ).fetchall()
    for r in rows:
        try:
            for rid in json.loads(r["turn_request_ids_json"] or "[]"):
                if rid:
                    seen.add(str(rid))
        except (ValueError, TypeError):
            continue
    return seen


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


def insert_campaign(
    *,
    name: str,
    ref: str,
    expected_signups: Optional[int] = None,
    expected_traffic: Optional[int] = None,
    started_at: Optional[str] = None,
    ends_at: Optional[str] = None,
    copy: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """Insert a campaign. Returns False if a campaign with that name
    already exists (ON CONFLICT DO NOTHING)."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO campaigns (name, ref, status, started_at, ends_at, "
            " expected_signups, expected_traffic, copy, notes) "
            "VALUES (?, ?, 'live', COALESCE(?, date('now')), ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO NOTHING",
            (name, ref, started_at, ends_at,
             int(expected_signups) if expected_signups is not None else None,
             int(expected_traffic) if expected_traffic is not None else None, copy, notes),
        )
        return cur.rowcount > 0


def get_campaign(name: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT name, ref, status, started_at, ends_at, expected_signups, "
            "       expected_traffic, copy, notes FROM campaigns WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def active_campaigns() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, ref, status, started_at, ends_at, expected_signups, "
            "       expected_traffic, copy, notes FROM campaigns WHERE status = 'live' "
            "ORDER BY started_at DESC"
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


# Fields a campaign's row may be edited in place (the name is the PK and
# referenced by campaign_metrics, so it's immutable; status flips via
# set_campaign_status / sunset).
CAMPAIGN_EDITABLE = ("ref", "expected_signups", "expected_traffic", "started_at", "ends_at", "copy", "notes")


def update_campaign(name: str, **changes: Any) -> Optional[dict[str, Any]]:
    """Update an existing campaign's editable fields in place. Only keys in
    :data:`CAMPAIGN_EDITABLE` with a non-``None`` value are written (a
    ``None`` means "leave it alone"); ``expected_signups`` /
    ``expected_traffic`` are coerced to int. Returns the updated row, or
    ``None`` if no campaign with that name exists."""
    fields: dict[str, Any] = {}
    for k, v in changes.items():
        if k not in CAMPAIGN_EDITABLE or v is None:
            continue
        if k in ("expected_signups", "expected_traffic"):
            fields[k] = int(v)
        else:
            fields[k] = v
    if get_campaign(name) is None:
        return None
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with connect() as conn:
            conn.execute(f"UPDATE campaigns SET {sets} WHERE name = ?", [*fields.values(), name])
    return get_campaign(name)


def insert_campaign_metric(*, campaign_name: str, signups: Optional[int],
                           traffic: Optional[int]) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO campaign_metrics (campaign_name, signups, traffic) VALUES (?, ?, ?)",
            (campaign_name,
             int(signups) if signups is not None else None,
             int(traffic) if traffic is not None else None),
        )
        return int(cur.lastrowid or 0)


def latest_campaign_metric(campaign_name: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, campaign_name, ran_at, signups, traffic FROM campaign_metrics "
            "WHERE campaign_name = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (campaign_name,),
        ).fetchone()
    return dict(row) if row else None


# ---------- draft digests (Eddy's delta context for update-draft) ----------


def insert_draft_digest(
    *,
    issue: int,
    word_count: int,
    notable_count: int,
    brief_count: int,
    journal_count: int,
    intro_present: bool,
    currently_present: bool,
    haiku_present: bool,
    cover_present: bool,
    source_hash: Optional[str] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO draft_digests "
            "(issue, word_count, notable_count, brief_count, journal_count, "
            " intro_present, currently_present, haiku_present, cover_present, source_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(issue), int(word_count), int(notable_count), int(brief_count),
                int(journal_count),
                1 if intro_present else 0, 1 if currently_present else 0,
                1 if haiku_present else 0, 1 if cover_present else 0, source_hash,
            ),
        )
        return int(cur.lastrowid or 0)


def latest_draft_digest(issue: int) -> Optional[dict[str, Any]]:
    """Most recent digest row for ``issue`` — i.e. the prior update-draft
    run's snapshot, used to compute the delta for the current run."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, issue, ran_at, word_count, notable_count, brief_count, "
            "       journal_count, intro_present, currently_present, haiku_present, "
            "       cover_present, source_hash "
            "FROM draft_digests WHERE issue = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (int(issue),),
        ).fetchone()
    return dict(row) if row else None


# ---------- Linky research cards (one row per posted #research message) ----------


RESEARCH_SOURCES = (
    "popular", "toread", "lobsters", "hackernews", "tildes", "indieweb_news",
)


def record_research_message(
    *, discord_message_id: str, url: str, source: str, title: Optional[str] = None,
) -> None:
    """Persist that Linky posted a per-link research card to #research,
    so a future reply to that message can be routed back to the URL.
    ``title`` is captured so a popular/lobsters reply that auto-creates
    a bookmark has something more useful than the URL as the title.
    ``source`` is one of :data:`RESEARCH_SOURCES`."""
    if not discord_message_id or not url or source not in RESEARCH_SOURCES:
        return
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO linky_research_messages "
            "(discord_message_id, url, source, title) VALUES (?, ?, ?, ?)",
            (str(discord_message_id), str(url), source, title),
        )


def lookup_research_message(discord_message_id: str) -> Optional[dict[str, Any]]:
    """Return the row for ``discord_message_id`` (the message Jamie's reply
    references), or ``None`` if it isn't one of Linky's cards."""
    if not discord_message_id:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT discord_message_id, url, source, title, posted_at "
            "FROM linky_research_messages WHERE discord_message_id = ?",
            (str(discord_message_id),),
        ).fetchone()
    return dict(row) if row else None


# ---------- image alt-text cache (journal + cover, vision-generated) ----------


def get_cached_alt(image_key: str) -> Optional[str]:
    """Return the cached alt for ``image_key``, or ``None`` if not cached.
    Empty string is a *miss* — we only cache successful generations."""
    if not image_key:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT alt FROM image_alt_cache WHERE image_key = ?", (image_key,)
        ).fetchone()
    if row is None:
        return None
    alt = row["alt"]
    return alt if alt else None


def cache_alt(*, image_key: str, alt: str, source: str = "vision") -> None:
    """Persist a generated/manual alt. A ``manual`` row wins over a prior
    ``vision`` one (so an operator's ``cover.json.alt`` can override)."""
    if not image_key or not isinstance(alt, str) or not alt.strip():
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO image_alt_cache (image_key, alt, source) VALUES (?, ?, ?) "
            "ON CONFLICT(image_key) DO UPDATE SET "
            "  alt = excluded.alt, source = excluded.source, "
            "  generated_at = datetime('now')",
            (image_key, alt.strip(), source),
        )


def recent_agent_runs(limit: int = 8) -> list[dict[str, Any]]:
    """Most recent agent_runs rows, newest first — for the ``/workshop
    status`` snapshot ("what's the bot done lately / did anything fail")."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, agent_name, trigger, status, duration_ms, error, "
            "       records_written, started_at, ended_at "
            "FROM agent_runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
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
