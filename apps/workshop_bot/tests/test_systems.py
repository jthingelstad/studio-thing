"""System module tests for active workshop_bot tool servers."""

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
from apps.workshop_bot.tools.llm import agent_tools  # noqa: E402


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
                "attribution_summary",
                "campaign_signups",
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
        rec = out[0]
        self.assertNotIn("email_address", rec)
        self.assertNotIn("email", rec)
        self.assertEqual(rec["email_domain"], "example.com")
        self.assertEqual(len(rec["email_hash"]), 32)

    def test_subscriber_sources_aggregates_recent_sources(self):
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
        self.assertEqual(out["by_source"], {"embed": 2, "api": 1, "unknown": 1})

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
        self.assertEqual(out[0]["id"], "em_1")
        self.assertEqual(out[0]["engagement"]["opens"], 773)

    def test_email_engagement_404(self):
        def fake_get(url, headers=None, params=None, timeout=None):
            return _FakeResp({"detail": "Not Found"}, status_code=404)

        with _patch_requests_get(bd_client, fake_get):
            out = self.tools["email_engagement"].handler(deps=None, email_id="bogus")
        self.assertIn("error", out)


class RegistryIntegrationTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("BUTTONDOWN_API_KEY", "stub")
        self.registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(self.registry)
        self.registry.register_system(ButtondownServer())

    def test_buttondown_names_come_from_system(self):
        for name in (
            "buttondown__counts",
            "buttondown__list_subscribers",
            "buttondown__recent_unsubscribes",
            "buttondown__subscriber_sources",
            "buttondown__subscriber_growth",
            "buttondown__list_recent_emails",
            "buttondown__email_engagement",
        ):
            tool = self.registry.get(name)
            self.assertIsNotNone(tool, name)
            self.assertEqual(tool.source, "system:buttondown")

    def test_retired_system_names_are_not_registered(self):
        for name in (
            "pinboard__recent",
            "pinboard__unread",
            "stripe__balance",
            "tinylytics__summary",
        ):
            self.assertIsNone(self.registry.get(name), name)


if __name__ == "__main__":
    unittest.main()
