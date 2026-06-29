"""The seeds garden — db layer + the seeds__* / graduation tools."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402

from apps.workshop_bot.tools import content_store, db  # noqa: E402
from apps.workshop_bot.tools.llm import local_tools as lt  # noqa: E402


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()


class SeedsDbTests(_DBCase):
    def test_add_list_update(self):
        s = db.seed_add("An idea worth keeping", title="Idea")
        self.assertEqual(db.seed_get(s["id"])["body"], "An idea worth keeping")
        db.seed_update(s["id"], tags="ai,writing", status="open")
        self.assertEqual(db.seed_list()[0]["tags"], "ai,writing")

    def test_cluster_groups_and_assigns(self):
        a = db.seed_add("a")
        b = db.seed_add("b")
        cl = db.seed_cluster_create("pair", note="they go together",
                                    suggested_type="article", seed_ids=[a["id"], b["id"]])
        got = db.seed_cluster_get(cl["id"])
        self.assertEqual({s["id"] for s in got["seeds"]}, {a["id"], b["id"]})
        self.assertEqual(db.seed_get(a["id"])["status"], "clustered")


class SeedsToolsTests(_DBCase):
    def test_graduate_carries_seeds_into_a_production(self):
        s1 = lt.t_seeds_add(None, "idea one", title="One")
        s2 = lt.t_seeds_add(None, "idea two")
        cl = lt.t_seeds_cluster(None, [s1["seed_id"], s2["seed_id"]], "cluster",
                                note="a direction", suggested_type="article")
        g = lt.t_seeds_graduate(None, "article", "My Essay", cluster_id=cl["cluster_id"])
        self.assertTrue(g["ok"])
        pid = g["production_id"]
        self.assertEqual(db.get_production(pid)["production_type"], "article")
        seeds_md = content_store.get(pid, "seeds.md")
        self.assertIn("idea one", seeds_md)
        self.assertIn("a direction", seeds_md)
        # body.md is NOT written — Jamie writes the prose.
        self.assertIsNone(content_store.get(pid, "body.md"))
        self.assertEqual([s["status"] for s in db.seed_list()], ["graduated", "graduated"])

    def test_graduate_by_seed_ids(self):
        s = lt.t_seeds_add(None, "solo idea")
        g = lt.t_seeds_graduate(None, "article", "Solo", seed_ids=[s["seed_id"]])
        self.assertTrue(g["ok"])

    def test_graduate_requires_seeds(self):
        self.assertIn("error", lt.t_seeds_graduate(None, "article", "x"))


if __name__ == "__main__":
    unittest.main()
