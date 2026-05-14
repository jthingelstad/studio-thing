"""Memory tests — round-trip remember/recall/forget against a temp SQLite DB."""

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


from apps.workshop_bot.tools import db # noqa: E402
from apps.workshop_bot.tools.llm import agent_tools


class MemoryRoundtripTests(unittest.TestCase):
    """End-to-end remember/recall/forget against a temp SQLite DB."""

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

    def test_remember_and_recall_self_scope(self):
        token = agent_tools.active_persona.set("eddy")
        try:
            r1 = agent_tools.t_remember(
                deps=None, content="Jamie said no AI takes for a few weeks",
                kind="preference", key="jamie:ai-fatigue",
            )
            self.assertTrue(r1["saved"])
            results = agent_tools.t_recall(deps=None)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["agent_name"], "eddy")
            self.assertEqual(results[0]["kind"], "preference")
        finally:
            agent_tools.active_persona.reset(token)

    def test_recall_scoped_to_self_by_default(self):
        # Eddy remembers something
        t1 = agent_tools.active_persona.set("eddy")
        try:
            agent_tools.t_remember(deps=None, content="eddy-thing", kind="observation")
        finally:
            agent_tools.active_persona.reset(t1)
        # Marky remembers something else
        t2 = agent_tools.active_persona.set("marky")
        try:
            agent_tools.t_remember(deps=None, content="marky-thing", kind="observation")
            # default recall sees only Marky's own
            results = agent_tools.t_recall(deps=None)
            agents = {r["agent_name"] for r in results}
            self.assertEqual(agents, {"marky"})
            # wildcard recall sees both
            results = agent_tools.t_recall(deps=None, agent_name="*")
            agents = {r["agent_name"] for r in results}
            self.assertEqual(agents, {"eddy", "marky"})
        finally:
            agent_tools.active_persona.reset(t2)

    def test_remember_rejects_bad_kind(self):
        t = agent_tools.active_persona.set("eddy")
        try:
            r = agent_tools.t_remember(deps=None, content="x", kind="bogus")
            self.assertIn("error", r)
        finally:
            agent_tools.active_persona.reset(t)

    def test_forget_marks_resolved(self):
        t = agent_tools.active_persona.set("patty")
        try:
            r = agent_tools.t_remember(deps=None, content="cta drafted", kind="todo")
            note_id = r["id"]
            self.assertEqual(len(agent_tools.t_recall(deps=None)), 1)
            agent_tools.t_forget_note(deps=None, note_id=note_id, status="resolved")
            self.assertEqual(len(agent_tools.t_recall(deps=None)), 0)
            self.assertEqual(
                len(agent_tools.t_recall(deps=None, include_resolved=True)), 1,
            )
        finally:
            agent_tools.active_persona.reset(t)

    def test_query_substring(self):
        t = agent_tools.active_persona.set("linky")
        try:
            agent_tools.t_remember(
                deps=None, content="cybersecurity is heating up again",
                kind="theme", key="theme:cybersecurity",
            )
            agent_tools.t_remember(
                deps=None, content="climate finance week",
                kind="theme", key="theme:climate",
            )
            r = agent_tools.t_recall(deps=None, query="cyber")
            self.assertEqual(len(r), 1)
            self.assertEqual(r[0]["key"], "theme:cybersecurity")
        finally:
            agent_tools.active_persona.reset(t)


class PinboardDedupTests(unittest.TestCase):
    """Linky's popular feed (every 6h) and to-read research (twice daily)
    rely on these dedup helpers to avoid re-showing items each tick.
    """

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

    def test_filter_unseen_popular_first_run(self):
        items = [
            {"url": "https://a.example/1", "title": "A", "posted_by": "alice"},
            {"url": "https://b.example/2", "title": "B", "posted_by": "bob"},
        ]
        unseen = db.filter_unseen_popular(items)
        self.assertEqual({i["url"] for i in unseen}, {i["url"] for i in items})

    def test_mark_popular_seen_then_filter(self):
        items = [
            {"url": "https://a.example/1", "title": "A"},
            {"url": "https://b.example/2", "title": "B"},
        ]
        n = db.mark_popular_seen(items)
        self.assertEqual(n, 2)
        # second call: same items, all seen
        unseen = db.filter_unseen_popular(items)
        self.assertEqual(unseen, [])

    def test_mark_popular_seen_idempotent(self):
        item = [{"url": "https://a.example/1", "title": "A"}]
        self.assertEqual(db.mark_popular_seen(item), 1)
        # No-op on second insert.
        self.assertEqual(db.mark_popular_seen(item), 0)

    def test_mark_popular_seen_records_judgment(self):
        items = [{"url": "https://a.example/1", "title": "A"}]
        db.mark_popular_seen(items, judged={"https://a.example/1": (True, "fits ai theme")})
        rows = db.query_agent_notes()  # unrelated; just confirming nothing crashes
        # Verify directly.
        with db.connect() as conn:
            row = conn.execute(
                "SELECT judged_interesting, judgment_note FROM pinboard_popular_seen "
                "WHERE url = ?",
                ("https://a.example/1",),
            ).fetchone()
        self.assertEqual(row["judged_interesting"], 1)
        self.assertEqual(row["judgment_note"], "fits ai theme")

    def test_filter_unresearched_urls(self):
        urls = ["u1", "u2", "u3"]
        self.assertEqual(db.filter_unresearched_urls(urls), urls)
        db.mark_url_researched(url="u2", title="t2", summary="s2")
        self.assertEqual(db.filter_unresearched_urls(urls), ["u1", "u3"])

    def test_mark_url_researched_idempotent(self):
        self.assertTrue(db.mark_url_researched(url="x", title="t", summary="s"))
        self.assertFalse(db.mark_url_researched(url="x", title="t", summary="s"))

    def test_filter_helpers_handle_empty(self):
        self.assertEqual(db.filter_unseen_popular([]), [])
        self.assertEqual(db.filter_unresearched_urls([]), [])
        self.assertEqual(db.mark_popular_seen([]), 0)


if __name__ == "__main__":
    unittest.main()
