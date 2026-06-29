"""The bridge agent tools — productions__* / production_content__* / tasks__* —
and the production_tasks state-engine helpers."""

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
from apps.workshop_bot.tools.llm import local_tools as lt  # noqa: E402
from apps.workshop_bot.tools.llm._specs import SPECS  # noqa: E402


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


class SpecConsistencyTests(unittest.TestCase):
    def test_every_func_has_a_spec(self):
        self.assertEqual([n for n in lt.FUNCS if n not in SPECS], [])

    def test_new_bridge_tools_registered(self):
        for name in ("productions__list", "productions__get", "productions__create",
                     "productions__set_phase", "production_content__read",
                     "production_content__write", "production_content__list",
                     "tasks__list", "tasks__add", "tasks__update", "tasks__complete"):
            self.assertIn(name, lt.FUNCS)
            self.assertIn(name, SPECS)


class ProductionsToolTests(_DBCase):
    def test_create_list_get_content_setphase(self):
        r = lt.t_productions_create(None, "article", "On Focus")
        self.assertTrue(r["ok"])
        self.assertEqual(r["id"], "ART1")
        lt.t_production_content_write(None, "ART1", "body.md", "Jamie's prose")
        self.assertEqual(lt.t_production_content_read(None, "ART1", "body.md")["text"], "Jamie's prose")
        self.assertEqual(lt.t_production_content_list(None, "ART1")["names"], ["body.md"])
        ids = [p["id"] for p in lt.t_productions_list(None, production_type="article")["productions"]]
        self.assertEqual(ids, ["ART1"])
        self.assertTrue(lt.t_productions_set_phase(None, "ART1", "draft")["ok"])
        self.assertEqual(lt.t_productions_get(None, "ART1")["phase"], "draft")

    def test_unknown_production_and_type_errors(self):
        self.assertIn("error", lt.t_productions_get(None, "ART999"))
        self.assertIn("error", lt.t_productions_create(None, "zine", "x"))
        self.assertIn("error", lt.t_productions_set_phase(None, "ART999", "draft"))


class TasksTests(_DBCase):
    def setUp(self):
        super().setUp()
        db.create_production(production_type="article", title="x")  # ART1

    def test_add_claim_list_complete(self):
        t = lt.t_tasks_add(None, "ART1", "Find sources", owner="linky")
        self.assertEqual(t["owner"], "linky")
        lt.t_tasks_update(None, t["task_id"], owner="linky", status="doing")
        tasks = lt.t_tasks_list(None, "ART1")["tasks"]
        self.assertEqual(tasks[0]["status"], "doing")
        lt.t_tasks_complete(None, t["task_id"])
        self.assertEqual(db.get_task(t["task_id"])["status"], "done")

    def test_owner_and_status_validation(self):
        self.assertIn("error", lt.t_tasks_add(None, "ART1", "x", owner="bogus"))
        t = lt.t_tasks_add(None, "ART1", "y")
        self.assertIn("error", lt.t_tasks_update(None, t["task_id"], status="bogus"))

    def test_list_tasks_for_owner(self):
        db.add_task("ART1", "a", owner="eddy")
        db.add_task("ART1", "b", owner="linky")
        mine = db.list_tasks_for_owner("eddy")
        self.assertEqual([t["title"] for t in mine], ["a"])


if __name__ == "__main__":
    unittest.main()
