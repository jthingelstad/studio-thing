"""Compatibility facade for workshop-bot database helpers."""

from __future__ import annotations

from .connection import (
    DEFAULT_DB_PATH,
    REPO,
    SCHEMA_PATH,
    connect,
    db_path,
    run_migrations,
)
from .migrations import (
    MIGRATIONS,
    Migration,
    applied_ids,
    pending,
)
from .store import *

__all__ = [
    "DEFAULT_DB_PATH",
    "REPO",
    "SCHEMA_PATH",
    "MIGRATIONS",
    "Migration",
    "applied_ids",
    "connect",
    "db_path",
    "pending",
    "run_migrations",
]
__all__ += [name for name in globals() if not name.startswith("_")]
