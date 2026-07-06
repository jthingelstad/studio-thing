"""The productions registry db helpers + the newsletter backfill/concurrency."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.content import issue  # noqa: E402
from apps.workshop_bot.tools.db import migrations as M  # noqa: E402
from apps.workshop_bot.tools.db.connection import connect  # noqa: E402


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmpdir.cleanup()


class CreateAndReadTests(_DBCase):
    def test_create_newsletter_issue_id_scheme(self):
        row = db.create_production(production_type="newsletter", title="WT360", seq=360)
        self.assertEqual(row["id"], "WT360")
        self.assertEqual(row["phase"], "planned")
        self.assertEqual(row["source"], "weekly.thingelstad.com")

    def test_seq_autoincrements_for_newsletter_rows_when_not_explicit(self):
        db.create_production(production_type="newsletter", title="a1", seq=360)
        row = db.create_production(production_type="newsletter", title="a2")
        self.assertEqual(row["id"], "WT361")

    def test_details_round_trip_as_dict(self):
        a = db.create_production(production_type="newsletter", title="WT360", seq=360,
                                 details={"slug": "x", "outline": "1,2,3"})
        got = db.get_production("WT360")
        self.assertEqual(got["details"], {"slug": "x", "outline": "1,2,3"})
        self.assertEqual(a["details"], got["details"])

    def test_list_filters(self):
        db.create_production(production_type="newsletter", title="WT360", seq=360, phase="build")
        db.create_production(production_type="newsletter", title="WT361", seq=361)
        self.assertEqual(len(db.list_productions(production_type="newsletter")), 2)
        self.assertEqual(len(db.list_productions(phase="build")), 1)
        self.assertEqual(len(db.list_productions(status="active")), 2)
        self.assertEqual(len(db.list_productions(status="done")), 0)

    def test_retired_types_rejected(self):
        for production_type in ("article", "podcast", "project", "zine"):
            with self.subTest(production_type=production_type):
                with self.assertRaises(ValueError):
                    db.create_production(production_type=production_type, title="x")

    def test_unique_type_seq_collision(self):
        db.create_production(production_type="newsletter", title="a", seq=360)
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_production(production_type="newsletter", title="b", seq=360)


class UpdateTests(_DBCase):
    def test_update_only_passed_fields_and_bumps_updated_at(self):
        db.create_production(production_type="newsletter", title="orig", seq=360)
        before = db.get_production("WT360")
        db.update_production("WT360", title="renamed", updated_by="web:jamie")
        after = db.get_production("WT360")
        self.assertEqual(after["title"], "renamed")
        self.assertEqual(after["updated_by"], "web:jamie")
        self.assertGreaterEqual(after["updated_at"], before["updated_at"])

    def test_set_phase_validates_per_type(self):
        db.create_production(production_type="newsletter", title="a", seq=360)
        db.set_production_phase("WT360", "build")
        self.assertEqual(db.get_production("WT360")["phase"], "build")
        with self.assertRaises(ValueError):
            db.set_production_phase("WT360", "record")  # retired podcast phase

    def test_set_phase_unknown_production(self):
        with self.assertRaises(ValueError):
            db.set_production_phase("WT999", "build")

    def test_status_validated_on_update_and_create(self):
        db.create_production(production_type="newsletter", title="a", seq=360)
        db.update_production("WT360", status="paused")
        self.assertEqual(db.get_production("WT360")["status"], "paused")
        with self.assertRaises(ValueError):
            db.update_production("WT360", status="snoozed")
        with self.assertRaises(ValueError):
            db.create_production(production_type="newsletter", title="b", seq=361, status="nope")


class BackfillTests(_DBCase):
    def _seed_issue(self, n, subject, pub):
        with connect() as conn:
            conn.execute(
                "INSERT INTO issues (number, subject, publish_date, era) VALUES (?, ?, ?, 'buttondown')",
                (n, subject, pub),
            )

    def test_backfill_published_issues_as_share_done(self):
        self._seed_issue(349, "WT349 — Test", "2026-06-21")
        self._seed_issue(348, "", "2026-06-14")  # empty subject -> synthesized title
        with connect() as conn:
            M._m_0016_backfill_newsletter_productions(conn)
        rows = {r["id"]: r for r in db.list_productions(production_type="newsletter")}
        self.assertEqual(rows["WT349"]["phase"], "share")
        self.assertEqual(rows["WT349"]["status"], "done")
        self.assertEqual(rows["WT349"]["title"], "WT349 — Test")
        self.assertEqual(rows["WT348"]["title"], "Weekly Thing 348")

    def test_backfill_is_idempotent(self):
        self._seed_issue(349, "WT349", "2026-06-21")
        with connect() as conn:
            M._m_0016_backfill_newsletter_productions(conn)
            M._m_0016_backfill_newsletter_productions(conn)
        self.assertEqual(len(db.list_productions(production_type="newsletter")), 1)


class NewsletterConcurrencyTests(_DBCase):
    def _open(self, n, pub):
        w = issue.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="t")

    def test_multiple_windows_active_and_mirrored_to_productions(self):
        self._open(351, "2026-06-27")
        self._open(352, "2026-07-04")
        actives = db.list_active_issue_windows()
        self.assertEqual({w["issue_number"] for w in actives}, {351, 352})
        # both mirrored into the productions registry as active newsletters
        nl = {p["id"] for p in db.list_productions(production_type="newsletter", status="active")}
        self.assertEqual(nl, {"WT351", "WT352"})

    def test_phase_change_mirrors_into_registry(self):
        self._open(351, "2026-06-27")
        db.set_issue_phase(351, "publish")
        self.assertEqual(db.get_production("WT351")["phase"], "publish")
        self.assertEqual(db.get_active_issue_window(351)["phase"], "publish")

    def test_explicit_target_resolves_specific_window(self):
        self._open(351, "2026-06-27")
        self._open(352, "2026-07-04")
        self.assertEqual(db.get_active_issue_window(351)["issue_number"], 351)
        # arg-less resolves the most-recently-set (legacy behaviour)
        self.assertEqual(db.get_active_issue_window()["issue_number"], 352)


if __name__ == "__main__":
    unittest.main()
