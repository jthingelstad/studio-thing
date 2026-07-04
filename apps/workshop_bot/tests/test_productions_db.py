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
    def test_create_each_type_and_id_scheme(self):
        a = db.create_production(production_type="article", title="On focus")
        p = db.create_production(production_type="podcast", title="Ep 1")
        j = db.create_production(production_type="project", title="50 supporters")
        self.assertEqual(a["id"], "ART1")
        self.assertEqual(p["id"], "POD1")
        self.assertEqual(j["id"], "PRJ1")
        self.assertEqual(a["phase"], "idea")   # default = phases[0]
        self.assertEqual(j["phase"], "open")

    def test_seq_autoincrements_per_type_independently(self):
        db.create_production(production_type="article", title="a1")
        db.create_production(production_type="podcast", title="p1")
        a2 = db.create_production(production_type="article", title="a2")
        self.assertEqual(a2["id"], "ART2")  # podcast row didn't bump the article seq

    def test_details_round_trip_as_dict(self):
        a = db.create_production(production_type="article", title="x",
                                 details={"slug": "x", "outline": "1,2,3"})
        got = db.get_production("ART1")
        self.assertEqual(got["details"], {"slug": "x", "outline": "1,2,3"})
        self.assertEqual(a["details"], got["details"])

    def test_list_filters(self):
        db.create_production(production_type="article", title="a", phase="draft")
        db.create_production(production_type="podcast", title="p")
        self.assertEqual(len(db.list_productions(production_type="article")), 1)
        self.assertEqual(len(db.list_productions(phase="draft")), 1)
        self.assertEqual(len(db.list_productions(status="active")), 2)
        self.assertEqual(len(db.list_productions(status="done")), 0)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            db.create_production(production_type="zine", title="x")

    def test_unique_type_seq_collision(self):
        db.create_production(production_type="article", title="a", seq=5)
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_production(production_type="article", title="b", seq=5)


class UpdateTests(_DBCase):
    def test_update_only_passed_fields_and_bumps_updated_at(self):
        db.create_production(production_type="article", title="orig")
        before = db.get_production("ART1")
        db.update_production("ART1", title="renamed", updated_by="web:jamie")
        after = db.get_production("ART1")
        self.assertEqual(after["title"], "renamed")
        self.assertEqual(after["updated_by"], "web:jamie")
        self.assertGreaterEqual(after["updated_at"], before["updated_at"])

    def test_set_phase_validates_per_type(self):
        db.create_production(production_type="article", title="a")
        db.set_production_phase("ART1", "draft")
        self.assertEqual(db.get_production("ART1")["phase"], "draft")
        with self.assertRaises(ValueError):
            db.set_production_phase("ART1", "record")  # podcast phase, not article

    def test_set_phase_unknown_production(self):
        with self.assertRaises(ValueError):
            db.set_production_phase("ART999", "draft")

    def test_status_validated_on_update_and_create(self):
        db.create_production(production_type="article", title="a")
        db.update_production("ART1", status="paused")
        self.assertEqual(db.get_production("ART1")["status"], "paused")
        with self.assertRaises(ValueError):
            db.update_production("ART1", status="snoozed")
        with self.assertRaises(ValueError):
            db.create_production(production_type="article", title="b", status="nope")


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
