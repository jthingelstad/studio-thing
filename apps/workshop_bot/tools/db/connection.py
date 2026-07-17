"""SQLite connection + migration entry points for the workshop bot.

The migration list itself — and the ``schema_migrations`` machinery —
lives in :mod:`apps.workshop_bot.tools.db.migrations`. This module owns
the connection lifecycle (``connect`` / ``_open_raw``), the schema-hash
auto-migrate gate (``_ensure_migrated``), and the one-time
``currently.json``→DB backfill hook.

Anyone who needs a connection should use :func:`connect`; first-use in a
process auto-applies pending migrations, schema-content edits trigger a
re-run on the next connect, and steady-state cost is one cheap
``SELECT id FROM schema_migrations`` plus a sha256 of schema.sql.
"""

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


# Per-process cache of "we've already migrated this db_path against this
# schema.sql content". Re-runs only fire when the hash drifts (operator
# edits schema.sql in a running bot) or when a different db_path is used
# (tests with WORKSHOP_DB_PATH pointing at a temp file).
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


def run_migrations() -> "_MigrationReport":
    """Apply all pending schema/data migrations and the one-time S3
    backfill. Returns a small :class:`_MigrationReport` summarising
    what landed — callers usually ignore the return (e.g.
    ``bot.py`` uses the values for its startup card)."""
    # Local import — :mod:`migrations` imports things lazily from us in
    # the CLI path, so top-level cycle is fine, but the lazy form keeps
    # the dependency direction explicit.
    from . import migrations as _migrations

    path = db_path()
    schema_content = SCHEMA_PATH.read_bytes() if SCHEMA_PATH.exists() else b""
    report = _migrations.run_migrations(
        lambda: _open_raw(path),
        schema_path=SCHEMA_PATH if SCHEMA_PATH.exists() else None,
    )
    _applied_schema_hash[path] = hashlib.sha256(schema_content).hexdigest()
    logger.info(
        "workshop.db ready at %s (%d applied this run, %d skipped)",
        path,
        len(report.applied),
        len(report.skipped),
    )
    return _MigrationReport(
        path=path,
        applied=report.applied,
        skipped=report.skipped,
        schema_hash=report.schema_hash,
        total=report.total,
    )


# Tiny wrapper carrying the path so callers (bot.py's startup card)
# don't need to import the deeper migrations module.
from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class _MigrationReport:
    path: Path
    applied: tuple[str, ...]
    skipped: tuple[str, ...]
    schema_hash: str
    total: int

    @property
    def latest_id(self) -> Optional[str]:
        if self.applied:
            return self.applied[-1]
        if self.skipped:
            return self.skipped[-1]
        return None

    @property
    def short_hash(self) -> str:
        return self.schema_hash[:8] if self.schema_hash else ""


# (The one-time ``currently.json`` → DB backfill bridge that ran here died
# with the iOS-Shortcuts pipeline — nothing can produce that file anymore.)
