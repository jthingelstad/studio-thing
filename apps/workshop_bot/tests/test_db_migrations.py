"""Consolidated migration framework — :mod:`tools.db.migrations`.

Three migration shapes (column / data / Python) collapsed into one
:class:`Migration` shape backed by a single ``MIGRATIONS`` tuple. These
tests guard the runner contract: idempotency, ordering, the
schema.sql-always-reruns special case, and failure isolation.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.db import connection as conn_mod  # noqa: E402
from apps.workshop_bot.tools.db import migrations as mig  # noqa: E402


class _DBCase(unittest.TestCase):
    """Temp-dir SQLite per test. Clears the module-level migration-state
    caches so each test starts from a known fresh-DB world."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        conn_mod._applied_schema_hash.clear()

    def tearDown(self) -> None:
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()
        conn_mod._applied_schema_hash.clear()


# ---------- runner contract ----------

class RunnerContract(_DBCase):

    def test_fresh_db_applies_every_migration(self):
        report = db.run_migrations()
        applied = set(report.applied)
        # The schema-sql migration applies; every other migration in
        # MIGRATIONS appears in ``applied`` because the DB is brand new.
        for m in db.MIGRATIONS:
            self.assertIn(
                m.id, applied,
                f"fresh DB should apply migration {m.id}",
            )

    def test_rerun_skips_recorded_migrations_except_schema(self):
        # First run applies everything.
        db.run_migrations()
        # Second run on the same DB: only the schema migration should
        # apply (it always reruns). Everything else is skipped.
        conn_mod._applied_schema_hash.clear()  # force the runner to fire
        report = db.run_migrations()
        self.assertEqual(report.applied, (mig.SCHEMA_MIGRATION_ID,),
                         f"only schema migration should re-run; got {report.applied}")
        # All non-schema migrations land in skipped.
        skipped = set(report.skipped)
        for m in db.MIGRATIONS:
            if m.id == mig.SCHEMA_MIGRATION_ID:
                continue
            self.assertIn(m.id, skipped)

    def test_schema_migration_reruns_even_when_recorded(self):
        # Mark only the schema migration as already applied. On the next
        # run, the runner must STILL re-execute it (so new tables added
        # to schema.sql land on the DB).
        with conn_mod._open_raw(conn_mod.db_path()) as conn:
            mig._m_0001_initial_schema(conn)  # create schema_migrations
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)",
                (mig.SCHEMA_MIGRATION_ID,),
            )
        # Inject a spy Migration entry that records calls — the dataclass
        # is frozen so we replace the whole entry rather than patching its
        # .apply attribute.
        calls: list[str] = []
        orig_apply = mig._m_0001_initial_schema

        def spy_apply(c):
            calls.append("schema")
            orig_apply(c)

        spy_entry = mig.Migration(
            id=mig.SCHEMA_MIGRATION_ID,
            description="spy schema migration",
            apply=spy_apply,
        )
        migrations = (spy_entry,) + tuple(
            m for m in db.MIGRATIONS if m.id != mig.SCHEMA_MIGRATION_ID
        )
        mig.run_migrations(
            lambda: conn_mod._open_raw(conn_mod.db_path()),
            migrations=migrations,
        )
        self.assertEqual(calls, ["schema"],
                         "schema migration must always re-run")

    def test_recorded_ids_persist_in_schema_migrations(self):
        db.run_migrations()
        with conn_mod._open_raw(conn_mod.db_path()) as conn:
            rows = {r["id"] for r in conn.execute(
                "SELECT id FROM schema_migrations"
            )}
        for m in db.MIGRATIONS:
            self.assertIn(m.id, rows)

    def test_failed_migration_does_not_record_id(self):
        # A migration that raises must leave the DB unrecorded so the
        # next boot re-attempts. The framework re-raises (matches the
        # existing "fail loud at startup" contract).
        def boom(_conn):
            raise RuntimeError("planned failure")

        bad = mig.Migration(
            id="9999_bad", description="raises during apply", apply=boom,
        )
        migrations = db.MIGRATIONS + (bad,)
        with self.assertRaises(RuntimeError):
            mig.run_migrations(
                lambda: conn_mod._open_raw(conn_mod.db_path()),
                migrations=migrations,
            )
        with conn_mod._open_raw(conn_mod.db_path()) as conn:
            recorded = mig.applied_ids(conn)
        self.assertNotIn(
            "9999_bad", recorded,
            "failed migration must not be recorded",
        )

    def test_pending_excludes_already_applied(self):
        db.run_migrations()
        conn_mod._applied_schema_hash.clear()
        with conn_mod._open_raw(conn_mod.db_path()) as conn:
            pend = mig.pending(conn)
        # Only the schema migration shows as pending (it always does);
        # all others are already applied.
        pending_ids = {m.id for m in pend}
        self.assertEqual(
            pending_ids, {mig.SCHEMA_MIGRATION_ID},
            f"expected only schema-sql pending; got {pending_ids}",
        )


# ---------- migration list integrity ----------

class MigrationListIntegrity(unittest.TestCase):

    def test_ids_unique(self):
        ids = [m.id for m in db.MIGRATIONS]
        self.assertEqual(len(ids), len(set(ids)),
                         f"duplicate migration ids: {ids}")

    def test_ids_sorted_ascending(self):
        ids = [m.id for m in db.MIGRATIONS]
        self.assertEqual(ids, sorted(ids),
                         "migration ids must appear in MIGRATIONS in sorted order")

    def test_every_apply_is_callable(self):
        for m in db.MIGRATIONS:
            self.assertTrue(callable(m.apply),
                            f"{m.id}: apply must be callable")

    def test_descriptions_nonempty(self):
        for m in db.MIGRATIONS:
            self.assertTrue(m.description.strip(),
                            f"{m.id}: description must be non-empty")


# ---------- CLI ----------

class CLI(_DBCase):

    def test_status_lists_all_migrations(self):
        db.run_migrations()
        # Capture stdout while invoking the CLI.
        buf = io.StringIO()
        with patch.object(sys, "stdout", buf):
            rc = mig.main(["status"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("workshop.db", out)
        self.assertIn("applied", out)
        for m in db.MIGRATIONS:
            self.assertIn(m.id, out,
                          f"status output should mention {m.id}")

    def test_pending_returns_zero_after_apply(self):
        db.run_migrations()
        buf = io.StringIO()
        with patch.object(sys, "stdout", buf):
            rc = mig.main(["pending"])
        self.assertEqual(rc, 0)
        self.assertIn("no pending", buf.getvalue())

    def test_apply_subcommand_is_idempotent(self):
        db.run_migrations()
        conn_mod._applied_schema_hash.clear()
        buf = io.StringIO()
        with patch.object(sys, "stdout", buf):
            rc = mig.main(["apply"])
        self.assertEqual(rc, 0)
        # After a fresh apply on an already-migrated DB, only schema
        # migration applies (always-rerun), and nothing else.
        out = buf.getvalue()
        self.assertIn("Applied 1 migration(s)", out)
        self.assertIn(mig.SCHEMA_MIGRATION_ID, out)


if __name__ == "__main__":
    unittest.main()
