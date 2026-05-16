"""Compatibility facade for workshop-bot database helpers."""

from __future__ import annotations

from .connection import (
    DEFAULT_DB_PATH,
    REPO,
    SCHEMA_PATH,
    _COLUMN_MIGRATIONS,
    connect,
    db_path,
    run_migrations,
)
from .store import *

__all__ = [
    "DEFAULT_DB_PATH",
    "REPO",
    "SCHEMA_PATH",
    "_COLUMN_MIGRATIONS",
    "connect",
    "db_path",
    "run_migrations",
]
__all__ += [name for name in globals() if not name.startswith("_")]
