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
from unittest.mock import patch

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
from apps.workshop_bot.systems.pinboard import client as pb_client  # noqa: E402
from apps.workshop_bot.systems.pinboard.server import PinboardServer  # noqa: E402
from apps.workshop_bot.systems.stripe import client as st_client  # noqa: E402
from apps.workshop_bot.systems.stripe.server import StripeServer  # noqa: E402
from apps.workshop_bot.systems.tinylytics import client as tl_client  # noqa: E402
from apps.workshop_bot.systems.tinylytics.server import TinylyticsServer  # noqa: E402
from apps.workshop_bot.tools.llm import agent_tools


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
        os.environ.setdefault("TINYLYTICS_SITE_ID", "3063")
        self.server = TinylyticsServer()
        self.tools = {t.name: t for t in self.server.list_tools()}

    def test_namespace_is_tinylytics(self):
        self.assertEqual(self.server.name, "tinylytics")

    def test_list_tools_returns_expected_set(self):
        self.assertEqual(
            set(self.tools),
            {
                "summary",
                "top_pages",
                "referrers",
                "sources",
                "campaign_traffic",
                "leaderboard",
                "user_journeys",
                "kudos",
                "insights",
                "uptime",
            },
        )

    def test_summary_dispatch(self):
        def fake_request(path, *, params=None):
            if path != "/hits":
                raise AssertionError(f"unexpected path {path!r}")
            if not params.get("grouped"):
                return {"pagination": {"total_count": 421}}
            if params.get("group_by") == "path":
                return {"grouped_hits": [{"path": "/", "views": 100, "unique_views": 80}]}
            if params.get("group_by") == "referrer":
                return {"grouped_hits": [{"referrer": "https://buttondown.com/", "hit_count": 27}]}
            raise AssertionError(f"unexpected params {params!r}")

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["summary"].handler(deps=None, days=7)
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(out["days"], 7)
        self.assertEqual(out["total_hits"], 421)
        self.assertEqual(out["top_pages"][0]["views"], 100)
        self.assertEqual(out["referrers"][0]["hit_count"], 27)

    def test_top_pages_passes_grouped_params(self):
        captured: list[dict] = []

        def fake_request(path, *, params=None):
            captured.append({"path": path, "params": dict(params or {})})
            return {"grouped_hits": [{"path": "/foo", "views": 1, "unique_views": 1}]}

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["top_pages"].handler(deps=None, days=14, limit=5)
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(out, [{"path": "/foo", "views": 1, "unique_views": 1}])
        self.assertEqual(captured[0]["path"], "/hits")
        self.assertEqual(captured[0]["params"]["grouped"], "true")
        self.assertEqual(captured[0]["params"]["group_by"], "path")
        self.assertEqual(captured[0]["params"]["per_page"], 5)
        # Date window forwarded.
        self.assertIn("start_date", captured[0]["params"])
        self.assertIn("end_date", captured[0]["params"])

    def test_referrers_passes_grouped_params(self):
        captured: list[dict] = []

        def fake_request(path, *, params=None):
            captured.append({"path": path, "params": dict(params or {})})
            return {"grouped_hits": [{"referrer": "https://x.example/", "hit_count": 9}]}

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["referrers"].handler(deps=None, days=7, limit=5)
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(out[0]["referrer"], "https://x.example/")
        self.assertEqual(captured[0]["params"]["group_by"], "referrer")

    def test_sources_uses_server_side_group_by(self):
        captured: list[dict] = []

        def fake_request(path, *, params=None):
            captured.append({"path": path, "params": dict(params or {})})
            return {
                "grouped_hits": [
                    {"source": "densediscovery", "hit_count": 12},
                    {"source": "powrss.com", "hit_count": 4},
                ],
                "pagination": {"total_count": 2},
            }

        original = tl_client._request
        tl_client._request = fake_request  # type: ignore[assignment]
        try:
            out = self.tools["sources"].handler(deps=None, days=30, limit=10)
        finally:
            tl_client._request = original  # type: ignore[assignment]
        self.assertEqual(captured[0]["path"], "/hits")
        self.assertEqual(captured[0]["params"]["grouped"], "true")
        self.assertEqual(captured[0]["params"]["group_by"], "source")
        self.assertEqual(captured[0]["params"]["per_page"], 10)
        self.assertEqual(out["days"], 30)
        self.assertEqual(out["total_sources"], 2)
        self.assertEqual(out["by_source"], {"densediscovery": 12, "powrss.com": 4})


class PinboardServerTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("PINBOARD_API_TOKEN", "jthingelstad:STUB")
        # Use a fresh temp DB so the SQLite-side effects of pinboard__recent /
        # pinboard__unread don't accumulate across tests.
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        from apps.workshop_bot.tools import db as _db
        _db.run_migrations()
        self.server = PinboardServer()
        self.tools = {t.name: t for t in self.server.list_tools()}

    def tearDown(self):
        if self._orig_db is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_db
        self._tmpdir.cleanup()

    def test_namespace_is_pinboard(self):
        self.assertEqual(self.server.name, "pinboard")

    def test_list_tools_returns_expected_set(self):
        self.assertEqual(
            set(self.tools),
            {
                # job-oriented verbs
                "issue_candidates",
                "capture_blurb",
                "popular_unseen",
                "mark_seen",
                "queue_depth_vs_deadline",
                "archive_recall",
                # thin API mirrors
                "recent",
                "unread",
                "lookup_url",
                "tags",
                "save",
            },
        )

    def test_each_tool_has_description_and_schema(self):
        for tool in self.tools.values():
            self.assertIsInstance(tool, ToolDef)
            self.assertTrue(tool.description.strip())
            self.assertEqual(tool.input_schema.get("type"), "object")

    def test_recent_normalizes_and_persists(self):
        page = {
            "posts": [
                {
                    "href": "https://example.com/a",
                    "description": "Title A",
                    "extended": "body A",
                    "tags": "ai writing",
                    "time": "2026-05-08T00:00:00Z",
                    "toread": "no",
                },
            ],
        }

        def fake_get(url, params=None, timeout=None, headers=None):
            return _FakeResp(page)

        with _patch_requests_get(pb_client, fake_get):
            out = self.tools["recent"].handler(deps=None, count=10)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "https://example.com/a")
        self.assertEqual(out[0]["title"], "Title A")
        self.assertTrue(out[0]["pinboard_url"].startswith("https://pinboard.in/u:"))

    def test_unread_passes_toread_flag(self):
        captured: list[dict] = []

        def fake_get(url, params=None, timeout=None, headers=None):
            captured.append({"url": url, "params": dict(params or {})})
            return _FakeResp([
                {
                    "href": "https://x/1",
                    "description": "X",
                    "extended": "",
                    "tags": "ai",
                    "time": "2026-05-08T00:00:00Z",
                    "toread": "yes",
                },
            ])

        with _patch_requests_get(pb_client, fake_get):
            out = self.tools["unread"].handler(deps=None, limit=50, tag="ai")
        self.assertEqual(len(out), 1)
        self.assertEqual(captured[0]["params"]["toread"], "yes")
        self.assertEqual(captured[0]["params"]["tag"], "ai")
        self.assertEqual(captured[0]["params"]["results"], 50)

    def test_mark_seen_reports_insert_vs_existing(self):
        first = self.tools["mark_seen"].handler(
            deps=None, url="https://x.example/a", title="A",
        )
        second = self.tools["mark_seen"].handler(
            deps=None, url="https://x.example/a", title="A",
        )
        self.assertEqual(first["recorded"], True)
        self.assertEqual(first["already_seen"], False)
        self.assertEqual(second["recorded"], False)
        self.assertEqual(second["already_seen"], True)

    def test_tags_unread_scope_aggregates(self):
        def fake_get(url, params=None, timeout=None, headers=None):
            return _FakeResp([
                {"href": "u1", "description": "A", "tags": "ai writing"},
                {"href": "u2", "description": "B", "tags": "ai climate"},
                {"href": "u3", "description": "C", "tags": "writing"},
                {"href": "u4", "description": "D", "tags": ""},
            ])

        with _patch_requests_get(pb_client, fake_get):
            out = self.tools["tags"].handler(deps=None, scope="unread", limit=200, top=5)
        self.assertEqual(out["scope"], "unread")
        self.assertEqual(out["total_items"], 4)
        # ai appears 2x, writing 2x, climate 1x; ordering is most_common.
        counts = {entry["tag"]: entry["count"] for entry in out["top_tags"]}
        self.assertEqual(counts["ai"], 2)
        self.assertEqual(counts["writing"], 2)
        self.assertEqual(counts["climate"], 1)

    def test_tags_archive_scope(self):
        def fake_get(url, params=None, timeout=None, headers=None):
            return _FakeResp({"ai": 12, "writing": 7, "climate": 3})

        with _patch_requests_get(pb_client, fake_get):
            out = self.tools["tags"].handler(deps=None, scope="archive", top=2)
        self.assertEqual(out["scope"], "archive")
        self.assertEqual(len(out["top_tags"]), 2)

    def test_estimate_read_length_moved_to_web(self):
        # The pinboard tool is gone; web.read_length is the home now.
        self.assertNotIn("estimate_read_length", self.tools)
        from apps.workshop_bot.tools import web
        with patch.object(web, "fetch_text", lambda url, max_chars=0: {"text": "word " * 100}):
            self.assertEqual(web.read_length("http://x")["bucket"], "short")
        with patch.object(web, "fetch_text", lambda url, max_chars=0: {"text": "word " * 5000}):
            self.assertEqual(web.read_length("http://x")["bucket"], "long")
        with patch.object(web, "fetch_text", lambda url, max_chars=0: {"error": "paywall"}):
            self.assertEqual(web.read_length("http://x")["bucket"], "unknown")


class StripeServerTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("STRIPE_API_KEY", "rk_test_stub")
        self.server = StripeServer()
        self.tools = {t.name: t for t in self.server.list_tools()}

    def test_namespace_is_stripe(self):
        self.assertEqual(self.server.name, "stripe")

    def test_list_tools_returns_expected_set(self):
        self.assertEqual(
            set(self.tools),
            {
                "balance",
                "recent_donations",
                "donations_by_month",
                "donations_by_ref",
                "year_to_date",
            },
        )

    def test_each_tool_has_description_and_schema(self):
        for tool in self.tools.values():
            self.assertIsInstance(tool, ToolDef)
            self.assertTrue(tool.description.strip())
            self.assertEqual(tool.input_schema.get("type"), "object")

    def test_balance_sums_usd_only(self):
        class _FakeBalance:
            @staticmethod
            def retrieve():
                return {
                    "available": [
                        {"currency": "usd", "amount": 1000},
                        {"currency": "eur", "amount": 5000},  # filtered out
                    ],
                    "pending": [
                        {"currency": "usd", "amount": 358},
                    ],
                }

        original = st_client.stripe.Balance
        st_client.stripe.Balance = _FakeBalance  # type: ignore[assignment]
        try:
            out = self.tools["balance"].handler(deps=None)
        finally:
            st_client.stripe.Balance = original  # type: ignore[assignment]
        self.assertEqual(out["available_usd"], 10.00)
        self.assertEqual(out["pending_usd"], 3.58)
        self.assertEqual(out["total_usd"], 13.58)

    def test_recent_donations_hashes_donor_pii(self):
        now_secs = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
        page = {
            "data": [
                {
                    "id": "ch_1",
                    "amount": 1500,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {
                        "email": "JAMIE@example.com",
                        "name": "Jamie Thingelstad",
                    },
                    "metadata": {"ref": "dd-2026-05-15"},
                    "payment_intent": "pi_1",
                },
            ],
            "has_more": False,
        }

        class _FakeCharge:
            @staticmethod
            def list(**kwargs):
                return page

        original = st_client.stripe.Charge
        st_client.stripe.Charge = _FakeCharge  # type: ignore[assignment]
        try:
            out = self.tools["recent_donations"].handler(deps=None, limit=5)
        finally:
            st_client.stripe.Charge = original  # type: ignore[assignment]
        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertEqual(rec["amount_usd"], 15.0)
        self.assertEqual(rec["donor_domain"], "example.com")
        self.assertEqual(len(rec["donor_hash"]), 32)
        self.assertEqual(rec["ref_tag"], "dd-2026-05-15")
        # Raw PII never appears.
        self.assertNotIn("billing_details", rec)
        self.assertNotIn("email", rec)
        self.assertNotIn("name", rec)

    def test_recent_donations_skips_unsucceeded(self):
        now_secs = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
        page = {
            "data": [
                {
                    "id": "ch_pending",
                    "amount": 500,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "pending",
                    "paid": False,
                    "billing_details": {},
                    "metadata": {},
                },
                {
                    "id": "ch_ok",
                    "amount": 1000,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {},
                    "metadata": {},
                },
            ],
            "has_more": False,
        }

        class _FakeCharge:
            @staticmethod
            def list(**kwargs):
                return page

        original = st_client.stripe.Charge
        st_client.stripe.Charge = _FakeCharge  # type: ignore[assignment]
        try:
            out = self.tools["recent_donations"].handler(deps=None, limit=5)
        finally:
            st_client.stripe.Charge = original  # type: ignore[assignment]
        ids = [r["id"] for r in out]
        self.assertEqual(ids, ["ch_ok"])

    def test_donations_by_ref_buckets_no_ref_separately(self):
        now_secs = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
        page = {
            "data": [
                {
                    "id": "ch_a",
                    "amount": 1000,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {},
                    "metadata": {"ref": "dd-2026-05-15"},
                },
                {
                    "id": "ch_b",
                    "amount": 500,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {},
                    "metadata": {"ref": "dd-2026-05-15"},
                },
                {
                    "id": "ch_c",
                    "amount": 2500,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {},
                    "metadata": {},  # no ref
                },
            ],
            "has_more": False,
        }

        class _FakeCharge:
            @staticmethod
            def list(**kwargs):
                return page

        original = st_client.stripe.Charge
        st_client.stripe.Charge = _FakeCharge  # type: ignore[assignment]
        try:
            out = self.tools["donations_by_ref"].handler(deps=None, days=90)
        finally:
            st_client.stripe.Charge = original  # type: ignore[assignment]
        self.assertEqual(out["total_count"], 3)
        self.assertEqual(out["total_usd"], 40.0)
        self.assertEqual(out["by_ref"]["dd-2026-05-15"], {"count": 2, "total_usd": 15.0})
        self.assertEqual(out["by_ref"]["(no-ref)"], {"count": 1, "total_usd": 25.0})

    def test_year_to_date_returns_current_nonprofit(self):
        now_secs = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
        page = {
            "data": [
                {
                    "id": "ch_a",
                    "amount": 1000,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {},
                    "metadata": {},
                },
                {
                    "id": "ch_b",
                    "amount": 500,
                    "currency": "usd",
                    "created": now_secs,
                    "status": "succeeded",
                    "paid": True,
                    "billing_details": {},
                    "metadata": {},
                },
            ],
            "has_more": False,
        }

        class _FakeCharge:
            @staticmethod
            def list(**kwargs):
                return page

        original = st_client.stripe.Charge
        st_client.stripe.Charge = _FakeCharge  # type: ignore[assignment]
        try:
            out = self.tools["year_to_date"].handler(deps=None)
        finally:
            st_client.stripe.Charge = original  # type: ignore[assignment]
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["total_usd"], 15.0)
        self.assertEqual(out["average_usd"], 7.50)
        # Reads from support.json's `current.short_name` — assert it's
        # non-empty rather than pinning a specific org so the test doesn't
        # rot when the annual nonprofit changes.
        self.assertTrue(out["current_nonprofit"])


class RegistryIntegrationTests(unittest.TestCase):
    """Exercising the bot.py composition path: local helpers + system modules."""

    def setUp(self):
        os.environ.setdefault("BUTTONDOWN_API_KEY", "stub")
        os.environ.setdefault("PINBOARD_API_TOKEN", "jthingelstad:STUB")
        os.environ.setdefault("STRIPE_API_KEY", "rk_test_stub")
        os.environ.setdefault("TINYLYTICS_API_KEY", "stub")
        os.environ.setdefault("TINYLYTICS_SITE_ID", "3063")
        self.registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(self.registry)
        self.registry.register_system(ButtondownServer())
        self.registry.register_system(PinboardServer())
        self.registry.register_system(StripeServer())
        self.registry.register_system(TinylyticsServer())

    def test_legacy_flat_names_no_longer_registered(self):
        # Phase 5 cleanup removed the dual-name aliases; only the dotted
        # forms exist now.
        for legacy in (
            "fetch_buttondown_subscribers",
            "fetch_tinylytics",
            "fetch_tinylytics_ref",
            "fetch_pinboard",
            "fetch_pinboard_unread",
            "fetch_pinboard_popular",
            "read_stored_bookmarks",
        ):
            self.assertIsNone(self.registry.get(legacy), legacy)

    def test_dotted_buttondown_names_come_from_system(self):
        for new in (
            "buttondown__counts",
            "buttondown__list_subscribers",
            "buttondown__recent_unsubscribes",
            "buttondown__subscriber_sources",
            "buttondown__subscriber_growth",
            "buttondown__list_recent_emails",
            "buttondown__email_engagement",
        ):
            tool = self.registry.get(new)
            self.assertIsNotNone(tool, new)
            self.assertEqual(tool.source, "system:buttondown")

    def test_dotted_pinboard_names_come_from_system(self):
        for new in (
            "pinboard__recent",
            "pinboard__unread",
            "pinboard__popular_unseen",
            "pinboard__tags",
            "pinboard__archive_recall",
        ):
            tool = self.registry.get(new)
            self.assertIsNotNone(tool, new)
            self.assertEqual(tool.source, "system:pinboard")

    def test_dotted_stripe_names_come_from_system(self):
        for new in (
            "stripe__balance",
            "stripe__recent_donations",
            "stripe__donations_by_month",
            "stripe__donations_by_ref",
            "stripe__year_to_date",
        ):
            tool = self.registry.get(new)
            self.assertIsNotNone(tool, new)
            self.assertEqual(tool.source, "system:stripe")

    def test_dotted_tinylytics_names_come_from_system(self):
        for new in (
            "tinylytics__summary",
            "tinylytics__top_pages",
            "tinylytics__referrers",
        ):
            tool = self.registry.get(new)
            self.assertIsNotNone(tool, new)
            self.assertEqual(tool.source, "system:tinylytics")


if __name__ == "__main__":
    unittest.main()
