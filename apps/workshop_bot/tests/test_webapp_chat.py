"""In-web chat — the web routes that run a persona's agent loop in-process."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import test_pure_helpers  # noqa: F401, E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.webapp import routes, server  # noqa: E402

LOGIN = "jthingelstad@github"
H = {server.IDENTITY_HEADER: LOGIN}


class WebChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        os.environ.setdefault("TAILSCALE_ALLOWED_LOGIN", LOGIN)
        db.run_migrations()
        db.create_production(production_type="newsletter", title="WT360",
                             seq=360, phase="build")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()

    async def _client(self, deps):
        app = web.Application(middlewares=[server._identity_mw])
        app[server.DEPS] = deps
        routes.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_chat_runs_the_addressed_agent_with_context(self):
        eddy = MagicMock()
        eddy.core = AsyncMock(return_value=("Open with the tension.", {}))
        deps = SimpleNamespace(team=SimpleNamespace(bots={"eddy": eddy}))
        c = await self._client(deps)
        r = await c.post("/chat", headers=H,
                         data={"context_key": "WT360", "message": "How do I open?", "persona": "eddy"})
        self.assertEqual((await r.json())["persona"], "eddy")
        for _ in range(20):
            await asyncio.sleep(0.05)
            msgs = (await (await c.get("/chat?context_key=WT360", headers=H)).json())["messages"]
            if any(m["role"] == "assistant" for m in msgs):
                break
        roles = [(m["role"], m["content"]) for m in msgs]
        self.assertIn(("user", "How do I open?"), roles)
        self.assertIn(("assistant", "Open with the tension."), roles)
        self.assertIn("newsletter issue WT360", eddy.core.call_args.kwargs["latest"])

    async def test_unknown_persona_falls_back_to_eddy(self):
        eddy = MagicMock()
        eddy.core = AsyncMock(return_value=("Let's stay with the issue.", {}))
        deps = SimpleNamespace(team=SimpleNamespace(bots={"eddy": eddy}))
        c = await self._client(deps)
        r = await c.post("/chat", headers=H,
                         data={"context_key": "WT360", "message": "@linky find sources", "persona": "linky"})
        self.assertEqual((await r.json())["persona"], "eddy")

    async def test_offline_when_no_team(self):
        c = await self._client(None)
        await c.post("/chat", headers=H, data={"context_key": "WT360", "message": "hi", "persona": "eddy"})
        for _ in range(20):
            await asyncio.sleep(0.05)
            msgs = (await (await c.get("/chat?context_key=WT360", headers=H)).json())["messages"]
            if any(m["role"] == "assistant" for m in msgs):
                break
        self.assertTrue(any("Eddy is not reachable" in m["content"] for m in msgs if m["role"] == "assistant"))

    async def test_foreign_origin_is_403(self):
        c = await self._client(None)
        r = await c.post("/chat", headers={**H, "Origin": "https://evil.example"},
                         data={"context_key": "WT360", "message": "hi"})
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
