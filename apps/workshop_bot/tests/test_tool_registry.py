"""Registry tests — dual-name dispatch, composition, collision rejection."""

from __future__ import annotations

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


from apps.workshop_bot.systems._base import SystemServer, ToolDef  # noqa: E402
from apps.workshop_bot.tools import agent_tools  # noqa: E402


class DottedAliasTests(unittest.TestCase):
    """Every old name has a dotted twin pointing at the same handler."""

    def test_every_renamed_tool_has_dotted_alias(self):
        for old, new in agent_tools.RENAMES.items():
            self.assertIn(old, agent_tools.FUNCS, msg=f"missing source: {old}")
            self.assertIn(new, agent_tools.FUNCS, msg=f"missing alias: {new}")
            self.assertIs(
                agent_tools.FUNCS[old],
                agent_tools.FUNCS[new],
                msg=f"alias {new!r} should share handler with {old!r}",
            )

    def test_dotted_alias_spec_has_correct_name(self):
        for old, new in agent_tools.RENAMES.items():
            self.assertEqual(agent_tools.SPECS[new]["name"], new)
            # Description and schema preserved verbatim from the old spec.
            self.assertEqual(
                agent_tools.SPECS[new]["description"],
                agent_tools.SPECS[old]["description"],
            )

    def test_install_dotted_aliases_is_idempotent(self):
        before = dict(agent_tools.SPECS)
        agent_tools._install_dotted_aliases()
        agent_tools._install_dotted_aliases()
        self.assertEqual(set(agent_tools.SPECS), set(before))


class ToolRegistryCompositionTests(unittest.TestCase):
    def setUp(self):
        self.registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(self.registry)

    def test_registry_includes_old_and_new_names(self):
        names = set(self.registry.all_names())
        for old, new in agent_tools.RENAMES.items():
            self.assertIn(old, names)
            self.assertIn(new, names)

    def test_registry_includes_inbox_tools(self):
        names = set(self.registry.all_names())
        for tool in ("inbox.post", "inbox.list", "inbox.read", "inbox.mark_read"):
            self.assertIn(tool, names)

    def test_old_and_new_names_dispatch_to_same_handler(self):
        for old, new in agent_tools.RENAMES.items():
            t_old = self.registry.get(old)
            t_new = self.registry.get(new)
            self.assertIsNotNone(t_old)
            self.assertIsNotNone(t_new)
            self.assertIs(t_old.func, t_new.func)

    def test_all_specs_have_name_field(self):
        for spec in self.registry.all_specs():
            self.assertIn("name", spec)
            self.assertIn("description", spec)
            self.assertIn("input_schema", spec)

    def test_duplicate_registration_raises(self):
        with self.assertRaises(ValueError):
            self.registry.register(
                "memory.remember",
                {"description": "x", "input_schema": {}},
                lambda deps, **kw: None,
            )

    def test_unknown_dispatch_raises(self):
        with self.assertRaises(KeyError):
            self.registry.dispatch("nonexistent.tool", deps=None, args={}, persona="eddy")

    def test_dispatch_sets_active_persona(self):
        seen: list[str] = []

        def handler(deps, **_kw):
            seen.append(agent_tools.active_persona.get())
            return "ok"

        registry = agent_tools.ToolRegistry()
        registry.register("test.echo", {"description": "x", "input_schema": {}}, handler)
        result = registry.dispatch("test.echo", deps=None, args={}, persona="marky")
        self.assertEqual(result, "ok")
        self.assertEqual(seen, ["marky"])
        # ContextVar was reset after dispatch.
        self.assertNotEqual(agent_tools.active_persona.get(), "marky")


class SystemServerRegistrationTests(unittest.TestCase):
    """A SystemServer round-trips list_tools() into dotted-name registration."""

    def test_register_system_namespaces_each_tool(self):
        class FakeServer:
            name = "fake"

            def list_tools(self):
                return [
                    ToolDef(
                        name="ping",
                        description="say pong",
                        input_schema={"type": "object", "properties": {}},
                        handler=lambda deps, **_: {"ok": True},
                    ),
                ]

        registry = agent_tools.ToolRegistry()
        registry.register_system(FakeServer())

        self.assertIn("fake.ping", registry.all_names())
        tool = registry.get("fake.ping")
        self.assertEqual(tool.source, "system:fake")
        self.assertEqual(tool.spec["name"], "fake.ping")
        out = registry.dispatch("fake.ping", deps=None, args={}, persona="eddy")
        self.assertEqual(out, {"ok": True})


if __name__ == "__main__":
    unittest.main()
