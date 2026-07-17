"""The atom editor page + POST handlers (build 1).

Drives the real aiohttp app over a TestClient against a temp DB, following
``test_webapp_productions.py``. The newsletter production is seeded as a bare
registry row + issue_items rows — no start-issue side effects.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402
from apps.workshop_bot.tools import content_store, db, issue_items  # noqa: E402
from apps.workshop_bot.tools.db.connection import connect  # noqa: E402
from apps.workshop_bot.webapp import routes, server  # noqa: E402

LOGIN = "jthingelstad@github"
H = {server.IDENTITY_HEADER: LOGIN}


class WebappEditorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        os.environ.setdefault("TAILSCALE_ALLOWED_LOGIN", LOGIN)
        db.run_migrations()
        db.create_production(production_type="newsletter", title="WT349",
                             seq=349, phase="build")
        content_store.set("WT349", "intro.md", "Hello.", by="t")
        self.n1 = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="p1", url="https://a", title="A pin", body_md="a")
        self.b1 = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="p2", url="https://b", title="B pin", body_md="b")
        self.j1 = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="m1", url="https://j", title="A day", body_md="j")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmpdir.cleanup()

    async def _client(self):
        app = web.Application(middlewares=[server._identity_mw])
        app[server.DEPS] = None
        routes.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_editor_page_renders_atoms_in_order(self):
        c = await self._client()
        r = await c.get("/productions/WT349/editor", headers=H)
        body = await r.text()
        self.assertEqual(r.status, 200)
        self.assertIn("Hello.", body)          # authored intro
        self.assertIn("A pin", body)           # derived notable
        # Compare section headers (bare strings appear early in buttons,
        # e.g. the notable item's "→ Briefly" demote button).
        self.assertLess(body.index("<h2>Notable"), body.index("<h2>Journal"))
        self.assertLess(body.index("<h2>Journal"), body.index("<h2>Briefly"))

    async def test_production_page_renders_live_issue_canvas(self):
        c = await self._client()
        r = await c.get("/productions/WT349", headers=H)
        body = await r.text()
        self.assertEqual(r.status, 200)
        self.assertIn("Issue Canvas", body)
        self.assertIn("A pin", body)
        self.assertIn("Edit text", body)
        self.assertNotIn("Draft Preview", body)
        self.assertNotIn("<iframe", body)

    async def test_editor_is_newsletter_only_and_404s(self):
        c = await self._client()
        with connect() as conn:
            conn.execute(
                "INSERT INTO productions (id, production_type, seq, title, phase, status) "
                "VALUES ('ART1', 'article', 1, 'legacy article', 'draft', 'active')"
            )
        r = await c.get("/productions/ART1/editor", headers=H)
        self.assertEqual(r.status, 400)
        r = await c.get("/productions/WT999/editor", headers=H)
        self.assertEqual(r.status, 404)

    async def test_atom_save_authored_and_currently(self):
        c = await self._client()
        r = await c.post("/productions/WT349/editor/atom", headers=H,
                         allow_redirects=False,
                         data={"key": "content:intro.md", "value": "New intro."})
        self.assertEqual(r.status, 302)
        self.assertEqual(content_store.get("WT349", "intro.md"), "New intro.")
        db.currently_add_type("Building")
        r = await c.post("/productions/WT349/editor/atom", headers=H,
                         allow_redirects=False,
                         data={"key": "currently:Building", "value": "atoms"})
        self.assertEqual(r.status, 302)
        entries = db.currently_get_entries(349)
        self.assertEqual(entries[0]["value"], "atoms")

    async def test_atom_save_issue_item_body_override(self):
        c = await self._client()
        r = await c.post("/productions/WT349/editor/atom", headers=H,
                         allow_redirects=False,
                         data={
                             "key": f"item:{self.n1}",
                             "value": "Edited in Studio.",
                             "return_to": f"/productions/WT349#atom-item-{self.n1}",
                         })
        self.assertEqual(r.status, 302)
        self.assertEqual(
            r.headers["Location"], f"/productions/WT349#atom-item-{self.n1}")
        row = issue_items.get_item(self.n1)
        self.assertEqual(row["body_md"], "Edited in Studio.")
        self.assertEqual(row["source_body_md"], "a")
        r = await c.post("/productions/WT349/editor/atom", headers=H,
                         allow_redirects=False,
                         data={
                             "key": f"item:{self.n1}",
                             "value": "ignored",
                             "clear_override": "1",
                         })
        self.assertEqual(r.status, 302)
        self.assertEqual(issue_items.get_item(self.n1)["body_md"], "a")

    async def test_atom_save_rejects_non_editor_names(self):
        c = await self._client()
        for key in ("content:metadata.json", "content:../evil", "bogus"):
            r = await c.post("/productions/WT349/editor/atom", headers=H,
                             allow_redirects=False, data={"key": key, "value": "x"})
            self.assertEqual(r.status, 400, key)

    async def test_flip_select_move_roundtrip(self):
        c = await self._client()
        # Flip briefly → notable.
        r = await c.post("/productions/WT349/editor/flip", headers=H,
                         allow_redirects=False,
                         data={"item_id": self.b1, "target": "notable"})
        self.assertEqual(r.status, 302)
        self.assertEqual(issue_items.get_item(self.b1)["section_override"], "notable")
        # Move the flipped item up within notable.
        r = await c.post("/productions/WT349/editor/move", headers=H,
                         allow_redirects=False,
                         data={"item_id": self.b1, "dir": "up"})
        self.assertEqual(r.status, 302)
        ids = [x["id"] for x in issue_items.list_items(349, section="notable")]
        self.assertEqual(ids, [self.b1, self.n1])
        # Undo the flip.
        r = await c.post("/productions/WT349/editor/flip", headers=H,
                         allow_redirects=False,
                         data={"item_id": self.b1, "target": "clear"})
        self.assertEqual(r.status, 302)
        self.assertIsNone(issue_items.get_item(self.b1)["section_override"])
        # Deselect + reselect journal.
        r = await c.post("/productions/WT349/editor/select", headers=H,
                         allow_redirects=False,
                         data={"item_id": self.j1, "selected": "0"})
        self.assertEqual(r.status, 302)
        self.assertEqual(issue_items.get_item(self.j1)["excluded"], 1)
        body = await (await c.get("/productions/WT349/editor", headers=H)).text()
        self.assertIn("deselected", body)      # still listed, marked
        r = await c.post("/productions/WT349/editor/select", headers=H,
                         allow_redirects=False,
                         data={"item_id": self.j1, "selected": "1"})
        self.assertEqual(issue_items.get_item(self.j1)["excluded"], 0)

    async def test_bad_inputs_are_400(self):
        c = await self._client()
        r = await c.post("/productions/WT349/editor/flip", headers=H,
                         allow_redirects=False,
                         data={"item_id": 9999, "target": "notable"})
        self.assertEqual(r.status, 400)
        r = await c.post("/productions/WT349/editor/move", headers=H,
                         allow_redirects=False,
                         data={"item_id": self.n1, "dir": "sideways"})
        self.assertEqual(r.status, 400)

    async def test_foreign_origin_post_is_403(self):
        c = await self._client()
        r = await c.post("/productions/WT349/editor/atom",
                         headers={**H, "Origin": "https://evil.example"},
                         allow_redirects=False,
                         data={"key": "content:intro.md", "value": "x"})
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
