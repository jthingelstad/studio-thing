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


from apps.workshop_bot.tools import db  # noqa: E402
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
                deps=None,
                content="Jamie said no AI takes for a few weeks",
                kind="preference",
                key="jamie:ai-fatigue",
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
        # A historical agent namespace can still have notes.
        t2 = agent_tools.active_persona.set("historical")
        try:
            agent_tools.t_remember(deps=None, content="historical-thing", kind="observation")
            # default recall sees only the active namespace's notes
            results = agent_tools.t_recall(deps=None)
            agents = {r["agent_name"] for r in results}
            self.assertEqual(agents, {"historical"})
            # wildcard recall sees both
            results = agent_tools.t_recall(deps=None, agent_name="*")
            agents = {r["agent_name"] for r in results}
            self.assertEqual(agents, {"eddy", "historical"})
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
        t = agent_tools.active_persona.set("eddy")
        try:
            r = agent_tools.t_remember(deps=None, content="review follow-up drafted", kind="todo")
            note_id = r["id"]
            self.assertEqual(len(agent_tools.t_recall(deps=None)), 1)
            agent_tools.t_forget_note(deps=None, note_id=note_id, status="resolved")
            self.assertEqual(len(agent_tools.t_recall(deps=None)), 0)
            self.assertEqual(
                len(agent_tools.t_recall(deps=None, include_resolved=True)),
                1,
            )
        finally:
            agent_tools.active_persona.reset(t)

    def test_query_substring(self):
        t = agent_tools.active_persona.set("eddy")
        try:
            agent_tools.t_remember(
                deps=None,
                content="cybersecurity is heating up again",
                kind="theme",
                key="theme:cybersecurity",
            )
            agent_tools.t_remember(
                deps=None,
                content="climate finance week",
                kind="theme",
                key="theme:climate",
            )
            r = agent_tools.t_recall(deps=None, query="cyber")
            self.assertEqual(len(r), 1)
            self.assertEqual(r[0]["key"], "theme:cybersecurity")
        finally:
            agent_tools.active_persona.reset(t)


if __name__ == "__main__":
    unittest.main()
