"""The demote-import-articles script: import-created articles → seeds, archived."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402

from apps.workshop_bot.scripts import demote_import_articles  # noqa: E402
from apps.workshop_bot.tools import content_store, db  # noqa: E402


class DemoteImportArticlesTests(unittest.TestCase):
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

    def _import_article(self, title, uuid, body, tags=None):
        row = db.create_production(
            production_type="article", title=title, phase="draft",
            details={"drafts_uuid": uuid, "source": "drafts", "tags": tags},
            created_by="import")
        content_store.set(row["id"], "body.md", body, by="import")
        return row

    def test_demotes_import_articles_and_archives(self):
        self._import_article("Crypto 101", "u-1", "# Crypto 101\n\nBody text.",
                             tags=["blog", "stage::draft"])
        db.create_production(production_type="article", title="Real work",
                             created_by="jamie")  # hand-created: untouched
        r = demote_import_articles.run(dry_run=False)
        self.assertEqual(r["counts"]["demoted"], 1)
        seeds = db.seed_list()
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0]["title"], "Crypto 101")
        self.assertEqual(seeds[0]["source"], "drafts:u-1")
        self.assertIn("Body text.", seeds[0]["body"])
        self.assertEqual(seeds[0]["tags"], "stage::draft")  # 'blog' dropped
        self.assertEqual(db.get_production("ART1")["status"], "archived")
        self.assertEqual(db.get_production("ART2")["status"], "active")

    def test_idempotent_rerun_and_import_skip(self):
        self._import_article("One", "u-1", "body one")
        demote_import_articles.run(dry_run=False)
        r2 = demote_import_articles.run(dry_run=False)
        self.assertEqual(r2["counts"]["demoted"], 0)
        self.assertEqual(len(db.seed_list()), 1)  # no duplicate seed
        # The archived production still carries drafts_uuid, so a re-run of
        # import_drafts.py would also skip it (both ledgers hold).
        det = db.get_production("ART1")["details"]
        self.assertEqual(det["drafts_uuid"], "u-1")

    def test_dry_run_writes_nothing(self):
        self._import_article("One", "u-1", "body")
        r = demote_import_articles.run(dry_run=True)
        self.assertEqual(r["counts"]["demoted"], 1)
        self.assertEqual(db.seed_list(), [])
        self.assertEqual(db.get_production("ART1")["status"], "active")


if __name__ == "__main__":
    unittest.main()
