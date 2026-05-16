"""SQLite connection and migration helpers for the workshop bot."""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parents[4]
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
    ("campaigns", "copy", "ALTER TABLE campaigns ADD COLUMN copy TEXT"),
    (
        "pinboard_popular_seen",
        "verdict_source",
        "ALTER TABLE pinboard_popular_seen ADD COLUMN verdict_source TEXT",
    ),
    # LLM accounting on agent_runs — captured per-run from agent_loop's
    # `response.usage`. Long-lived DBs pre-this-migration carry NULLs;
    # new rows after restart record real values.
    ("agent_runs", "model", "ALTER TABLE agent_runs ADD COLUMN model TEXT"),
    (
        "agent_runs",
        "input_tokens",
        "ALTER TABLE agent_runs ADD COLUMN input_tokens INTEGER",
    ),
    (
        "agent_runs",
        "output_tokens",
        "ALTER TABLE agent_runs ADD COLUMN output_tokens INTEGER",
    ),
    (
        "agent_runs",
        "cache_read_tokens",
        "ALTER TABLE agent_runs ADD COLUMN cache_read_tokens INTEGER",
    ),
    (
        "agent_runs",
        "cache_create_tokens",
        "ALTER TABLE agent_runs ADD COLUMN cache_create_tokens INTEGER",
    ),
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
