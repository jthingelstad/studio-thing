"""System module round-trip tests.

For each ``SystemServer``, exercise ``list_tools()`` and dispatch each
handler with the underlying HTTP client stubbed so the suite never
hits the network.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import os
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _install_stubs() -> None:
    if "discord" not in sys.modules:
        discord = types.ModuleType("discord")

        class _Client:
            def __init__(self, *a, **k):
                self.user = None

        class _Intents:
            message_content = False
            guilds = False

            @staticmethod
            def default():
                return _Intents()

        discord.Client = _Client  # type: ignore[attr-defined]
        discord.Intents = _Intents  # type: ignore[attr-defined]
        discord.Message = object  # type: ignore[attr-defined]
        discord.DiscordException = Exception  # type: ignore[attr-defined]
        abc_mod = types.ModuleType("discord.abc")
        abc_mod.Messageable = object  # type: ignore[attr-defined]
        sys.modules["discord"] = discord
        sys.modules["discord.abc"] = abc_mod

    if "anthropic" not in sys.modules:
        anthropic = types.ModuleType("anthropic")

        class _A:
            def __init__(self, *a, **k):
                pass

        anthropic.Anthropic = _A  # type: ignore[attr-defined]
        sys.modules["anthropic"] = anthropic


_install_stubs()


from apps.workshop_bot.systems._base import ToolDef  # noqa: E402
from apps.workshop_bot.systems.buttondown import client as bd_client  # noqa: E402
from apps.workshop_bot.systems.buttondown.server import ButtondownServer  # noqa: E402
from apps.workshop_bot.systems.tinylytics import client as tl_client  # noqa: E402
from apps.workshop_bot.systems.tinylytics.server import TinylyticsServer  # noqa: E402
from apps.workshop_bot.tools import agent_tools  # noqa: E402


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@contextlib.contextmanager
def _patch_requests_get(module, fake_get):
    """Replace ``module.requests.get`` for the duration of the block.

    ``module.requests`` is the actual imported requests module — so we
    save the original ``get`` attribute and restore it on exit rather
    than ``del``-ing it (which would leave the real requests broken
    for subsequent tests).
    """
    requests_mod = module.requests
    original = requests_mod.get
    requests_mod.get = fake_get
    try:
        yield
    finally:
        requests_mod.get = original


class ButtondownServerTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("BUTTONDOWN_API_KEY", "stub")
        self.server = ButtondownServer()
        self.tools = {t.name: t for t in self.server.list_tools()}

    def test_namespace_is_buttondown(self):
        self.assertEqual(self.server.name, "buttondown")

    def test_list_tools_returns_expected_set(self):
        self.assertEqual(
            set(self.tools),
            {
                "counts",
                "list_subscribers",
                "recent_unsubscribes",
                "subscriber_sources",
                "subscriber_growth",
                "list_recent_emails",
                "email_engagement",
            },
        )

    def test_each_tool_has_description_and_schema(self):
        for tool in self.tools.values():
            self.assertIsInstance(tool, ToolDef)
            self.assertTrue(tool.description.strip())
            self.assertEqual(tool.input_schema.get("type"), "object")

    def test_counts_dispatch(self):
        captured: list[dict] = []

        def fake_get(url, headers=None, params=None, timeout=None):
            captured.append({"url": url, "params": params})
            return _FakeResp({"count": 1539})

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["counts"].handler(deps=None)
        self.assertEqual(out["total"], 1539)
        self.assertEqual(out["premium"], 1539)
        self.assertEqual(out["unsubscribed"], 1539)
        self.assertEqual(len(captured), 3)

    def test_list_subscribers_hashes_emails(self):
        page = {
            "next": None,
            "results": [
                {
                    "id": "abc",
                    "email_address": "JAMIE@example.com",
                    "type": "regular",
                    "source": "embed",
                    "creation_date": "2026-05-08T00:00:00Z",
                },
            ],
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            return _FakeResp(page)

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["list_subscribers"].handler(deps=None, limit=5)
        self.assertEqual(len(out), 1)
        rec = out[0]
        # Raw email never appears in the model-facing payload.
        self.assertNotIn("email_address", rec)
        self.assertNotIn("email", rec)
        self.assertEqual(rec["email_domain"], "example.com")
        self.assertEqual(len(rec["email_hash"]), 32)
        self.assertEqual(rec["source"], "embed")

    def test_subscriber_sources_aggregates(self):
        now = _dt.datetime.now(_dt.timezone.utc)
        recent = (now - _dt.timedelta(days=1)).isoformat()
        page = {
            "next": None,
            "results": [
                {"email_address": "a@x", "source": "embed", "creation_date": recent},
                {"email_address": "b@x", "source": "embed", "creation_date": recent},
                {"email_address": "c@x", "source": "api", "creation_date": recent},
                {"email_address": "d@x", "source": None, "creation_date": recent},
            ],
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            return _FakeResp(page)

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["subscriber_sources"].handler(deps=None, days=30)
        self.assertEqual(out["subscribers_seen"], 4)
        self.assertEqual(out["by_source"]["embed"], 2)
        self.assertEqual(out["by_source"]["api"], 1)
        self.assertEqual(out["by_source"]["unknown"], 1)

    def test_subscriber_sources_stops_at_window_boundary(self):
        now = _dt.datetime.now(_dt.timezone.utc)
        in_window = (now - _dt.timedelta(days=1)).isoformat()
        out_window = (now - _dt.timedelta(days=60)).isoformat()
        page = {
            "next": None,
            "results": [
                {"email_address": "a@x", "source": "embed", "creation_date": in_window},
                {"email_address": "b@x", "source": "embed", "creation_date": out_window},
                {"email_address": "c@x", "source": "api", "creation_date": out_window},
            ],
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            return _FakeResp(page)

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["subscriber_sources"].handler(deps=None, days=30)
        self.assertEqual(out["subscribers_seen"], 1)

    def test_list_recent_emails_summary_shape(self):
        page = {
            "results": [
                {
                    "id": "em_1",
                    "subject": "Weekly Thing 346",
                    "publish_date": "2026-05-03T13:54:35Z",
                    "status": "sent",
                    "email_type": "public",
                    "absolute_url": "https://weekly.thingelstad.com/archive/346/",
                    "slug": "weekly-thing-346",
                    "creation_date": "2026-05-03T13:54:35Z",
                    "analytics": {
                        "recipients": 1541,
                        "deliveries": 1539,
                        "opens": 773,
                        "clicks": 0,
                        "unsubscriptions": 3,
                        "subscriptions": 0,
                        "replies": 1,
                    },
                },
            ],
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            return _FakeResp(page)

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["list_recent_emails"].handler(deps=None, limit=5)
        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertEqual(rec["id"], "em_1")
        self.assertEqual(rec["engagement"]["opens"], 773)
        self.assertEqual(rec["engagement"]["recipients"], 1541)

    def test_email_engagement_404(self):
        def fake_get(url, headers=None, params=None, timeout=None):
            return _FakeResp({"detail": "Not Found"}, status_code=404)

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["email_engagement"].handler(deps=None, email_id="bogus")
        self.assertIn("error", out)


class TinylyticsServerTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("TINYLYTICS_API_KEY", "stub")
        os.environ.setdefault("TINYLYTICS_SITE_UID", "stub-uid")
        self.server = TinylyticsServer()
        self.tools = {t.name: t for t in self.server.list_tools()}

    def test_namespace_is_tinylytics(self):
        self.assertEqual(self.server.name, "tinylytics")

    def test_list_tools_returns_expected_set(self):
        self.assertEqual(
            set(self.tools),
            {"summary", "ref_traffic", "top_pages", "referrers", "events"},
        )

    def test_summary_dispatch(self):
        def fake_request(path, *, params=None):
            if path == "/stats":
                return {"hits": 10}
            if path == "/pages":
                return [{"path": "/", "hits": 5}]
            if path == "/referrers":
                return [{"source": "bsky", "hits": 2}]
            if path == "/events":
                return []
            raise AssertionError(f"unexpected path {path!r}")

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["summary"].handler(deps=None, days=7)
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(out["days"], 7)
        self.assertEqual(out["stats"], {"hits": 10})
        self.assertEqual(out["top_pages"], [{"path": "/", "hits": 5}])
        self.assertEqual(out["referrers"], [{"source": "bsky", "hits": 2}])

    def test_ref_traffic_filters_and_aggregates(self):
        captured: list[dict] = []

        def fake_request(path, *, params=None):
            captured.append({"path": path, "params": params})
            return [
                {"path": "/?ref=dd-2026-05-15", "hits": 7},
                {"path": "/archive/348/?ref=dd-2026-05-15", "hits": 3},
                {"path": "/?ref=other-tag", "hits": 99},
                {"path": "/about/", "hits": 4},
            ]

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["ref_traffic"].handler(
                deps=None, tag="dd-2026-05-15", days=14
            )
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(out["tag"], "dd-2026-05-15")
        self.assertEqual(out["hits"], 10)
        self.assertEqual(len(out["paths"]), 2)
        # Forwarded the `days` param to the upstream call.
        self.assertEqual(captured[0]["params"], {"days": 14, "limit": 200})

    def test_ref_traffic_rejects_blank_tag(self):
        out = self.tools["ref_traffic"].handler(deps=None, tag="   ", days=7)
        self.assertIn("error", out)

    def test_top_pages_passthrough(self):
        def fake_request(path, *, params=None):
            self.assertEqual(path, "/pages")
            self.assertEqual(params, {"days": 14, "limit": 5})
            return [{"path": "/foo", "hits": 1}]

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["top_pages"].handler(deps=None, days=14, limit=5)
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(out, [{"path": "/foo", "hits": 1}])


class RegistryIntegrationTests(unittest.TestCase):
    """Exercising the bot.py composition path: local helpers + system modules."""

    def setUp(self):
        os.environ.setdefault("BUTTONDOWN_API_KEY", "stub")
        os.environ.setdefault("TINYLYTICS_API_KEY", "stub")
        os.environ.setdefault("TINYLYTICS_SITE_UID", "stub-uid")
        self.registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(self.registry)
        self.registry.register_system(ButtondownServer())
        self.registry.register_system(TinylyticsServer())

    def test_legacy_marky_names_still_dispatch(self):
        # Old multi-purpose tool stays available for personas that haven't
        # migrated yet; system module's split tools live alongside.
        for legacy in (
            "fetch_buttondown_subscribers",
            "fetch_tinylytics",
            "fetch_tinylytics_ref",
        ):
            self.assertIsNotNone(self.registry.get(legacy), legacy)

    def test_dotted_buttondown_names_come_from_system(self):
        for new in (
            "buttondown.counts",
            "buttondown.list_subscribers",
            "buttondown.recent_unsubscribes",
            "buttondown.subscriber_sources",
            "buttondown.subscriber_growth",
            "buttondown.list_recent_emails",
            "buttondown.email_engagement",
        ):
            tool = self.registry.get(new)
            self.assertIsNotNone(tool, new)
            self.assertEqual(tool.source, "system:buttondown")

    def test_dotted_tinylytics_names_come_from_system(self):
        for new in (
            "tinylytics.summary",
            "tinylytics.ref_traffic",
            "tinylytics.top_pages",
            "tinylytics.referrers",
            "tinylytics.events",
        ):
            tool = self.registry.get(new)
            self.assertIsNotNone(tool, new)
            self.assertEqual(tool.source, "system:tinylytics")


if __name__ == "__main__":
    unittest.main()
