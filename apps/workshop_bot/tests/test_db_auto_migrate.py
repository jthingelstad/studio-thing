"""Auto-migration on ``db.connect()``.

The bot's daemon process holds an open db connection for hours / days at
a time; if ``schema.sql`` gains a new table mid-flight (a fresh pull
without a restart), the next job that touches the new table used to
crash with ``no such table``. The fix: ``connect()`` hashes ``schema.sql``
on entry and re-runs migrations when the content changed. These tests
exercise that path against a temp DB so we never need to touch the real
``workshop.db``.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.db import connection as conn_mod  # noqa: E402


class AutoMigrateOnConnect(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        # Reset per-test so we exercise first-connect cleanly.
        conn_mod._applied_schema_hash.clear()

    def tearDown(self) -> None:
        if self._orig_db is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_db
        self._tmp.cleanup()
        conn_mod._applied_schema_hash.clear()

    def test_first_connect_runs_migrations(self):
        # No prior ``run_migrations()`` call — ``connect()`` alone must
        # leave the DB usable. (Previously you had to call run_migrations()
        # by hand or the next CREATE-dependent query would crash.)
        with db.connect() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        # Pick one table that's only present after the schema script runs.
        self.assertIn("issue_items", tables)
        self.assertIn("schema_migrations", tables)

    def test_steady_state_skips_redundant_migrations(self):
        # First connect runs them. Second connect must see the hash cached
        # and not call ``run_migrations`` again — track via a counter.
        call_count = {"n": 0}
        orig = conn_mod.run_migrations

        def spy() -> None:
            call_count["n"] += 1
            orig()

        conn_mod.run_migrations = spy  # type: ignore[assignment]
        try:
            with db.connect() as _:
                pass
            with db.connect() as _:
                pass
            with db.connect() as _:
                pass
        finally:
            conn_mod.run_migrations = orig  # type: ignore[assignment]
        self.assertEqual(call_count["n"], 1)

    def test_schema_content_change_triggers_rerun(self):
        # Simulate ``schema.sql`` being edited mid-process: change the
        # in-memory hash so ``_ensure_migrated`` sees a mismatch and
        # re-applies. The migrations are idempotent so this is safe.
        with db.connect() as _:
            pass
        # Pretend a different schema was loaded last time we ran.
        path = conn_mod.db_path()
        conn_mod._applied_schema_hash[path] = "stale-hash-from-prior-version"
        call_count = {"n": 0}
        orig = conn_mod.run_migrations

        def spy() -> None:
            call_count["n"] += 1
            orig()

        conn_mod.run_migrations = spy  # type: ignore[assignment]
        try:
            with db.connect() as _:
                pass
        finally:
            conn_mod.run_migrations = orig  # type: ignore[assignment]
        self.assertEqual(call_count["n"], 1)


if __name__ == "__main__":
    unittest.main()
