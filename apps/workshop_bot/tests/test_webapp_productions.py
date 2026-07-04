"""Web app productions CRUD — create / edit / list, identity + CSRF gates.

Drives the real aiohttp app (routes + identity middleware) over a TestClient
against a temp DB. Newsletter web-create is intentionally not exercised here —
it invokes the start-issue job (S3 + Discord side effects); start-issue has its
own hermetic tests. These cover the article/podcast/project registry path.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.webapp import routes, server  # noqa: E402

LOGIN = "jthingelstad@github"
H = {server.IDENTITY_HEADER: LOGIN}


class WebappProductionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        os.environ.setdefault("TAILSCALE_ALLOWED_LOGIN", LOGIN)
        db.run_migrations()

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

    async def test_create_article_records_creator_and_redirects(self):
        c = await self._client()
        r = await c.post("/productions/new", headers=H, allow_redirects=False,
                         data={"production_type": "article", "title": "On Focus",
                               "phase": "idea", "detail_slug": "on-focus"})
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/productions/ART1/edit")
        row = db.get_production("ART1")
        self.assertEqual(row["created_by"], LOGIN)
        self.assertEqual(row["details"], {"slug": "on-focus"})

    async def test_new_form_and_edit_form_render(self):
        c = await self._client()
        r = await c.get("/productions/new", headers=H)
        self.assertEqual(r.status, 200)
        db.create_production(production_type="project", title="50 supporters")
        r = await c.get("/productions/PRJ1/edit", headers=H)
        self.assertIn("50 supporters", await r.text())

    async def test_edit_changes_phase_via_set_production_phase(self):
        c = await self._client()
        db.create_production(production_type="article", title="x")
        r = await c.post("/productions/ART1/edit", headers=H, allow_redirects=False,
                         data={"title": "x", "phase": "outline", "status": "active"})
        self.assertEqual(r.status, 302)
        self.assertEqual(db.get_production("ART1")["phase"], "outline")

    async def test_list_groups_by_type(self):
        c = await self._client()
        db.create_production(production_type="article", title="Art one")
        db.create_production(production_type="project", title="Proj one")
        r = await c.get("/productions", headers=H)
        body = await r.text()
        self.assertEqual(r.status, 200)
        self.assertIn("ART1", body)
        self.assertIn("PRJ1", body)

    async def test_list_hides_shipped_archive_by_default(self):
        c = await self._client()
        db.create_production(production_type="article", title="In flight")
        db.create_production(production_type="newsletter", title="WT10", seq=10,
                             phase="share", status="done")
        body = await (await c.get("/productions", headers=H)).text()
        self.assertIn("ART1", body)          # in-flight shown
        self.assertNotIn("WT10", body)       # shipped hidden
        self.assertIn("1 shipped", body)     # but counted
        all_body = await (await c.get("/productions?all=1", headers=H)).text()
        self.assertIn("WT10", all_body)      # archive revealed with ?all=1

    async def test_list_shows_paused_but_not_archived_by_default(self):
        c = await self._client()
        db.create_production(production_type="article", title="Working")
        db.create_production(production_type="article", title="Shelved", status="paused")
        db.create_production(production_type="article", title="Filed", status="archived")
        body = await (await c.get("/productions", headers=H)).text()
        self.assertIn("Working", body)
        self.assertIn("Shelved", body)       # paused stays findable
        self.assertNotIn("Filed", body)      # archived tucked behind ?all=1
        all_body = await (await c.get("/productions?all=1", headers=H)).text()
        self.assertIn("Filed", all_body)

    async def test_bulk_status_pauses_selected(self):
        c = await self._client()
        db.create_production(production_type="article", title="a")
        db.create_production(production_type="article", title="b")
        db.create_production(production_type="article", title="c")
        r = await c.post("/productions/bulk-status", headers=H, allow_redirects=False,
                         data=[("action", "pause"), ("pid", "ART1"), ("pid", "ART3")])
        self.assertEqual(r.status, 302)
        self.assertEqual(db.get_production("ART1")["status"], "paused")
        self.assertEqual(db.get_production("ART2")["status"], "active")
        self.assertEqual(db.get_production("ART3")["status"], "paused")

    async def test_bulk_status_unknown_action_is_400(self):
        c = await self._client()
        r = await c.post("/productions/bulk-status", headers=H, allow_redirects=False,
                         data={"action": "explode", "pid": "ART1"})
        self.assertEqual(r.status, 400)

    async def test_single_status_route_and_validation(self):
        c = await self._client()
        db.create_production(production_type="article", title="a")
        r = await c.post("/productions/ART1/status", headers=H, allow_redirects=False,
                         data={"status": "paused"})
        self.assertEqual(r.status, 302)
        self.assertEqual(db.get_production("ART1")["status"], "paused")
        r = await c.post("/productions/ART1/status", headers=H, allow_redirects=False,
                         data={"status": "bogus"})
        self.assertEqual(r.status, 400)
        r = await c.post("/productions/ART99/status", headers=H, allow_redirects=False,
                         data={"status": "paused"})
        self.assertEqual(r.status, 404)

    async def test_invalid_phase_is_400(self):
        c = await self._client()
        r = await c.post("/productions/new", headers=H, allow_redirects=False,
                         data={"production_type": "article", "title": "x", "phase": "bogus"})
        self.assertEqual(r.status, 400)

    async def test_missing_title_is_400(self):
        c = await self._client()
        r = await c.post("/productions/new", headers=H, allow_redirects=False,
                         data={"production_type": "article", "title": ""})
        self.assertEqual(r.status, 400)

    async def test_foreign_origin_post_is_403(self):
        c = await self._client()
        r = await c.post("/productions/new",
                         headers={**H, "Origin": "https://evil.example"},
                         allow_redirects=False,
                         data={"production_type": "project", "title": "x"})
        self.assertEqual(r.status, 403)

    async def test_no_identity_is_403(self):
        c = await self._client()
        r = await c.get("/productions", allow_redirects=False)
        self.assertEqual(r.status, 403)

    async def test_edit_unknown_production_is_404(self):
        c = await self._client()
        r = await c.get("/productions/ART999/edit", headers=H, allow_redirects=False)
        self.assertEqual(r.status, 404)


if __name__ == "__main__":
    unittest.main()
