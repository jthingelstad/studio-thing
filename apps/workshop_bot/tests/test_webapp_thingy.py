"""Studio's private Thingy operations route."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from apps.librarian.admin.dashboard_data import (
    CorpusStatus,
    FindingExample,
    ImprovementFinding,
    QualitySummary,
    ThingyDashboard,
)
from apps.workshop_bot.webapp import routes, server

LOGIN = "jthingelstad@github"
H = {server.IDENTITY_HEADER: LOGIN}


def fixture_dashboard() -> ThingyDashboard:
    corpus = CorpusStatus(
        key="weekly_thing",
        label="Weekly Thing",
        status="ready",
        status_label="Current",
        object_key="artifacts/corpus.json",
        generated_at="2026-07-17T20:00:00Z",
        uploaded_at="2026-07-17T21:00:00Z",
        source_latest_at="2026-07-12T12:00:00Z",
        source_changed_at="2026-07-17T19:00:00Z",
        deployed_count=350,
        source_count=350,
        chunk_count=9651,
        link_count=1200,
        size_bytes=1024,
        embedding_model="cohere.embed-english-v3",
        reasons=("Deployed coverage matches the current source mirror.",),
    )
    example = FindingExample(
        conversation_id="conversation-1",
        updated_at="2026-07-17T20:00:00Z",
        mode="research_guide",
        scope="blog",
        reader_label="reader·12345678",
        note="The cited source did not support the claim.",
    )
    high = ImprovementFinding(
        key="citation_mismatch",
        label="Citation mismatch",
        priority="high",
        occurrences=4,
        conversation_count=3,
        latest_at=example.updated_at,
        modes=("research_guide",),
        scopes=("blog",),
        sources=("blog",),
        regression_candidate=True,
        examples=(example,),
    )
    low = ImprovementFinding(
        key="answer_too_long",
        label="Answer too long",
        priority="low",
        occurrences=1,
        conversation_count=1,
        latest_at=example.updated_at,
        modes=("thingy",),
        scopes=("all",),
        sources=(),
        regression_candidate=False,
        examples=(example,),
    )
    return ThingyDashboard(
        generated_at="2026-07-18T12:00:00Z",
        days=90,
        corpora=(corpus,),
        findings=(high, low),
        quality=QualitySummary(
            conversations=12,
            reviewed=11,
            needs_attention=4,
            downvotes=1,
            feedback=2,
            real_readers=5,
            quality_counts={"clean": 7, "watch": 4},
        ),
        modes=("research_guide", "thingy"),
        scopes=("all", "blog"),
    )


class ThingyWebappTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self):
        app = web.Application(middlewares=[server._identity_mw])
        app[server.DEPS] = None
        routes.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_thingy_route_is_identity_protected(self):
        client = await self._client()
        response = await client.get("/thingy/")
        self.assertEqual(response.status, 403)

    async def test_thingy_route_renders_health_and_quality_queue(self):
        client = await self._client()
        with patch.object(
            routes.dashboard_data, "load_dashboard", return_value=fixture_dashboard()
        ):
            response = await client.get("/thingy/", headers=H)
        body = await response.text()
        self.assertEqual(response.status, 200)
        self.assertIn("Thingy Operations", body)
        self.assertIn("Weekly Thing", body)
        self.assertIn("350 / 350 items", body)
        self.assertIn("Citation mismatch", body)
        self.assertIn("regression candidate", body)
        self.assertIn('class="active">Thingy</a>', body)

    async def test_action_filter_keeps_only_high_priority_findings(self):
        client = await self._client()
        with patch.object(
            routes.dashboard_data, "load_dashboard", return_value=fixture_dashboard()
        ):
            response = await client.get("/thingy/?priority=action", headers=H)
        body = await response.text()
        self.assertIn("Citation mismatch", body)
        self.assertNotIn("Answer too long", body)
        self.assertIn("1 of 2 grouped findings", body)


if __name__ == "__main__":
    unittest.main()
