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


class DottedNameTests(unittest.TestCase):
    """Every local helper is keyed under a dotted name."""

    def test_every_local_helper_uses_dotted_name(self):
        for name in agent_tools.FUNCS:
            self.assertIn(".", name, msg=f"flat name still in FUNCS: {name!r}")

    def test_spec_name_field_matches_key(self):
        for name, spec in agent_tools.SPECS.items():
            self.assertEqual(spec["name"], name)


class ToolRegistryCompositionTests(unittest.TestCase):
    def setUp(self):
        self.registry = agent_tools.ToolRegistry()
        agent_tools.register_local_helpers(self.registry)

    def test_registry_includes_local_helpers(self):
        names = set(self.registry.all_names())
        # Spot-check a few; full coverage lives in DottedNameTests.
        for tool in (
            "archive.search",
            "memory.remember",
            "issue.current_number",
            "s3_issues.list",
            "s3_personas.read_file",
            "site.support_state",
            "web.fetch_url",
        ):
            self.assertIn(tool, names)

    def test_registry_includes_inbox_tools(self):
        names = set(self.registry.all_names())
        for tool in ("inbox.post", "inbox.list", "inbox.read", "inbox.mark_read"):
            self.assertIn(tool, names)

    def test_legacy_flat_names_are_gone(self):
        names = set(self.registry.all_names())
        for legacy in (
            "search_archive",
            "fetch_url",
            "fetch_pinboard",
            "fetch_buttondown_subscribers",
            "remember",
            "current_issue_number",
            "persona_read",
            "get_support_state",
        ):
            self.assertNotIn(legacy, names, msg=f"legacy name {legacy!r} should be gone")

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


class RestrictedSystemTests(unittest.TestCase):
    """A system declaring `restricted_to` is only visible to the named personas."""

    def _registry_with_restricted_fake(self):
        class RestrictedServer:
            name = "vault"
            restricted_to = {"patty"}

            def list_tools(self):
                return [
                    ToolDef(
                        name="read",
                        description="read the vault",
                        input_schema={"type": "object", "properties": {}},
                        handler=lambda deps, **_: {"secret": "ok"},
                    ),
                ]

        registry = agent_tools.ToolRegistry()
        registry.register_system(RestrictedServer())
        return registry

    def test_restricted_tool_visible_only_to_allowed_persona(self):
        registry = self._registry_with_restricted_fake()
        # all_names() ignores restrictions — it's the unscoped view.
        self.assertIn("vault.read", registry.all_names())
        # names_for(persona) is the scoped view the agent loop uses.
        self.assertIn("vault.read", registry.names_for("patty"))
        for other in ("eddy", "linky", "marky"):
            self.assertNotIn(
                "vault.read",
                registry.names_for(other),
                msg=f"vault.read should be hidden from {other!r}",
            )

    def test_dispatch_refuses_restricted_tool_for_other_persona(self):
        registry = self._registry_with_restricted_fake()
        # Patty can call it.
        out = registry.dispatch("vault.read", deps=None, args={}, persona="patty")
        self.assertEqual(out, {"secret": "ok"})
        # Marky cannot — even if she tries to invoke it directly.
        with self.assertRaises(PermissionError):
            registry.dispatch("vault.read", deps=None, args={}, persona="marky")

    def test_unrestricted_system_visible_to_everyone(self):
        class OpenServer:
            name = "public"
            # No `restricted_to` attribute → visible to all.

            def list_tools(self):
                return [
                    ToolDef(
                        name="ping",
                        description="public ping",
                        input_schema={"type": "object", "properties": {}},
                        handler=lambda deps, **_: "pong",
                    ),
                ]

        registry = agent_tools.ToolRegistry()
        registry.register_system(OpenServer())
        for persona in ("eddy", "linky", "marky", "patty"):
            self.assertIn("public.ping", registry.names_for(persona))


if __name__ == "__main__":
    unittest.main()
