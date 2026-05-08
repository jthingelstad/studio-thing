"""Inbox tests — post/list/read/mark_read lifecycle against a temp DB."""

from __future__ import annotations

import os
import sys
import tempfile
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


from apps.workshop_bot.tools import agent_tools, db, inbox  # noqa: E402


class InboxLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig_path is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_path
        self._tmpdir.cleanup()

    def test_post_then_list_then_read_then_mark_read(self):
        token = agent_tools.active_persona.set("linky")
        try:
            posted = inbox.t_inbox_post(
                deps=None,
                recipient="eddy",
                kind="handoff",
                subject="Curated set for #348",
                body="Top items attached.",
                related_issue=348,
            )
            self.assertTrue(posted["posted"])
            self.assertEqual(posted["sender"], "linky")
            self.assertEqual(posted["recipient"], "eddy")
        finally:
            agent_tools.active_persona.reset(token)

        token = agent_tools.active_persona.set("eddy")
        try:
            unread = inbox.t_inbox_list(deps=None)
            self.assertEqual(len(unread), 1)
            item_id = unread[0]["id"]

            full = inbox.t_inbox_read(deps=None, id=item_id)
            self.assertEqual(full["subject"], "Curated set for #348")
            self.assertEqual(full["related_issue"], 348)

            # read does NOT mark read; item still appears in unread filter.
            still_unread = inbox.t_inbox_list(deps=None)
            self.assertEqual(len(still_unread), 1)

            marked = inbox.t_inbox_mark_read(deps=None, id=item_id, status="acted")
            self.assertTrue(marked["updated"])

            after = inbox.t_inbox_list(deps=None)
            self.assertEqual(after, [])

            all_items = inbox.t_inbox_list(deps=None, filter="all")
            self.assertEqual(len(all_items), 1)
            self.assertIsNotNone(all_items[0]["read_at"])
        finally:
            agent_tools.active_persona.reset(token)

    def test_post_rejects_unknown_recipient(self):
        token = agent_tools.active_persona.set("marky")
        try:
            r = inbox.t_inbox_post(
                deps=None,
                recipient="bogus",
                kind="fyi",
                subject="x",
                body="y",
            )
            self.assertIn("error", r)
        finally:
            agent_tools.active_persona.reset(token)

    def test_post_rejects_unknown_kind(self):
        token = agent_tools.active_persona.set("marky")
        try:
            r = inbox.t_inbox_post(
                deps=None,
                recipient="patty",
                kind="invalid",
                subject="x",
                body="y",
            )
            self.assertIn("error", r)
        finally:
            agent_tools.active_persona.reset(token)

    def test_team_inbox_visible_via_recipient_argument(self):
        sender_token = agent_tools.active_persona.set("marky")
        try:
            inbox.t_inbox_post(
                deps=None,
                recipient="team",
                kind="fyi",
                subject="referral spike",
                body="dd-2026-05-15 doubled",
            )
        finally:
            agent_tools.active_persona.reset(sender_token)

        # Linky reads team inbox by passing recipient='team'.
        reader_token = agent_tools.active_persona.set("linky")
        try:
            personal = inbox.t_inbox_list(deps=None)
            self.assertEqual(personal, [])
            team_items = inbox.t_inbox_list(deps=None, recipient="team")
            self.assertEqual(len(team_items), 1)
            self.assertEqual(team_items[0]["sender"], "marky")
            self.assertEqual(team_items[0]["recipient"], "team")
        finally:
            agent_tools.active_persona.reset(reader_token)

    def test_filter_by_kind_and_related_issue(self):
        sender_token = agent_tools.active_persona.set("patty")
        try:
            inbox.t_inbox_post(
                deps=None,
                recipient="marky",
                kind="handoff",
                subject="cta tone for 348",
                body="...",
                related_issue=348,
            )
            inbox.t_inbox_post(
                deps=None,
                recipient="marky",
                kind="fyi",
                subject="general note",
                body="...",
            )
            inbox.t_inbox_post(
                deps=None,
                recipient="marky",
                kind="handoff",
                subject="cta tone for 349",
                body="...",
                related_issue=349,
            )
        finally:
            agent_tools.active_persona.reset(sender_token)

        reader_token = agent_tools.active_persona.set("marky")
        try:
            handoffs = inbox.t_inbox_list(deps=None, filter="kind=handoff")
            self.assertEqual(len(handoffs), 2)

            for_348 = inbox.t_inbox_list(deps=None, filter="related_issue=348")
            self.assertEqual(len(for_348), 1)
            self.assertEqual(for_348[0]["related_issue"], 348)
        finally:
            agent_tools.active_persona.reset(reader_token)

    def test_mark_read_invalid_status_returns_error(self):
        token = agent_tools.active_persona.set("eddy")
        try:
            inbox.t_inbox_post(
                deps=None,
                recipient="eddy",
                kind="fyi",
                subject="self-test",
                body="x",
            )
            items = inbox.t_inbox_list(deps=None)
            r = inbox.t_inbox_mark_read(deps=None, id=items[0]["id"], status="bogus")
            self.assertIn("error", r)
        finally:
            agent_tools.active_persona.reset(token)


if __name__ == "__main__":
    unittest.main()
