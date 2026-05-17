"""SQLite connection and migration helpers for the workshop bot."""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

REPO = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = REPO / "apps" / "workshop_bot" / "data" / "workshop.db"
SCHEMA_PATH = REPO / "apps" / "workshop_bot" / "db" / "schema.sql"

logger = logging.getLogger("workshop.db")


def db_path() -> Path:
    raw = os.environ.get("WORKSHOP_DB_PATH")
    if raw:
        return Path(raw) if Path(raw).is_absolute() else REPO / raw
    return DEFAULT_DB_PATH


# Migration state per db_path. The value is the schema.sql hash that was
# applied — re-running is skipped only when the file content hasn't changed
# since. A long-running bot picks up a schema.sql edit on the next connect
# without needing a daemon restart; standalone CLI tools (exercise harness,
# ad-hoc scripts) migrate on their first connect, period.
_applied_schema_hash: dict[Path, str] = {}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_migrated(path)
    with _open_raw(path) as conn:
        yield conn


@contextmanager
def _open_raw(path: Path) -> Iterator[sqlite3.Connection]:
    """Raw connection — used by :func:`run_migrations` so the migration
    pass itself doesn't re-trigger the auto-migration check."""
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def _schema_hash() -> Optional[str]:
    try:
        return hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
    except OSError:
        # SCHEMA_PATH missing in some test contexts; treat as "no auto-run".
        return None


def _ensure_migrated(path: Path) -> None:
    """Apply :func:`run_migrations` for ``path`` the first time we see it
    *and* every time ``schema.sql`` content changes mid-process.

    Schema DDL is idempotent (``CREATE TABLE IF NOT EXISTS`` throughout),
    so re-applying after a content change is safe. The hash check keeps
    the steady-state cost to one cheap file-stat-plus-sha per connect —
    no DDL replay when nothing has changed.
    """
    current = _schema_hash()
    if current is not None and _applied_schema_hash.get(path) == current:
        return
    try:
        run_migrations()
    except Exception:
        _applied_schema_hash.pop(path, None)
        raise


def run_migrations() -> None:
    path = db_path()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _open_raw(path) as conn:
        conn.executescript(schema)
        _record_migration(conn, "0001_schema_sql")
        _apply_column_migrations(conn)
        _apply_data_migrations(conn)
    _applied_schema_hash[path] = hashlib.sha256(schema.encode("utf-8")).hexdigest()
    _bootstrap_currently_from_s3()
    logger.info("workshop.db ready at %s", path)


def _bootstrap_currently_from_s3() -> None:
    """One-time bridge: when the active in-flight issue has any legacy
    ``currently.json`` in S3 but no ``currently_entries`` rows yet, seed
    the rows so the new DB-backed renderer sees the existing values.
    Idempotent — once entries exist, subsequent boots no-op. Failures
    are swallowed (logged) so DB init never fails on an S3 hiccup."""
    try:
        from .store import currently_backfill_from_s3, get_active_issue_window
    except Exception:  # noqa: BLE001
        return
    try:
        window = get_active_issue_window()
    except Exception:  # noqa: BLE001
        return
    if not window:
        return
    try:
        inserted = currently_backfill_from_s3(int(window["issue_number"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("currently backfill from S3 failed: %s", exc)
        return
    if inserted:
        logger.info(
            "currently backfill: seeded %d entries for WT%d from currently.json",
            inserted, int(window["issue_number"]),
        )


# SQLite has no "ADD COLUMN IF NOT EXISTS". For columns added after the
# initial table creation, run ALTER TABLE and tolerate the "duplicate
# column" error so a fresh DB and a long-lived DB both end up identical.
_COLUMN_MIGRATIONS: tuple[tuple[str, str, str, str], ...] = (
    # (migration id, table, column, full ADD COLUMN clause)
    (
        "0002_campaigns_copy",
        "campaigns",
        "copy",
        "ALTER TABLE campaigns ADD COLUMN copy TEXT",
    ),
    (
        "0003_pinboard_popular_seen_verdict_source",
        "pinboard_popular_seen",
        "verdict_source",
        "ALTER TABLE pinboard_popular_seen ADD COLUMN verdict_source TEXT",
    ),
    # LLM accounting on agent_runs — captured per-run from agent_loop's
    # `response.usage`. Long-lived DBs pre-this-migration carry NULLs;
    # new rows after restart record real values.
    (
        "0004_agent_runs_model",
        "agent_runs",
        "model",
        "ALTER TABLE agent_runs ADD COLUMN model TEXT",
    ),
    (
        "0005_agent_runs_input_tokens",
        "agent_runs",
        "input_tokens",
        "ALTER TABLE agent_runs ADD COLUMN input_tokens INTEGER",
    ),
    (
        "0006_agent_runs_output_tokens",
        "agent_runs",
        "output_tokens",
        "ALTER TABLE agent_runs ADD COLUMN output_tokens INTEGER",
    ),
    (
        "0007_agent_runs_cache_read_tokens",
        "agent_runs",
        "cache_read_tokens",
        "ALTER TABLE agent_runs ADD COLUMN cache_read_tokens INTEGER",
    ),
    (
        "0008_agent_runs_cache_create_tokens",
        "agent_runs",
        "cache_create_tokens",
        "ALTER TABLE agent_runs ADD COLUMN cache_create_tokens INTEGER",
    ),
)


def _record_migration(conn: sqlite3.Connection, migration_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)",
        (migration_id,),
    )


def _migration_recorded(conn: sqlite3.Connection, migration_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE id = ?",
        (migration_id,),
    ).fetchone()
    return row is not None


_DATA_MIGRATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "0009_retire_non_pinboard_discovery_feeds",
        (
            "DELETE FROM popular_seen_sightings "
            "WHERE source NOT IN ('popular', 'toread')",
            "DELETE FROM linky_research_messages "
            "WHERE source NOT IN ('popular', 'toread')",
            "UPDATE pinboard_popular_seen SET verdict_source = NULL "
            "WHERE verdict_source IS NOT NULL "
            "AND verdict_source NOT IN ('popular', 'toread')",
        ),
    ),
)


def _apply_data_migrations(conn: sqlite3.Connection) -> None:
    for migration_id, statements in _DATA_MIGRATIONS:
        if _migration_recorded(conn, migration_id):
            continue
        for sql in statements:
            conn.execute(sql)
        _record_migration(conn, migration_id)


def _apply_column_migrations(conn: sqlite3.Connection) -> None:
    for migration_id, table, column, sql in _COLUMN_MIGRATIONS:
        try:
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})")
            }
        except sqlite3.Error:
            continue
        if column in existing:
            _record_migration(conn, migration_id)
            continue
        try:
            conn.execute(sql)
            _record_migration(conn, migration_id)
        except sqlite3.OperationalError:
            # Column was added concurrently by another process; ignore.
            _record_migration(conn, migration_id)
