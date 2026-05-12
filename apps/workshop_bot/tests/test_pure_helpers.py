"""Unit tests for the workshop-bot pure-Python helpers.

These exercise functions that don't need Discord, Anthropic, or SQLite at
runtime — but the modules under test do *import* discord/anthropic at
load time. We install minimal stubs in ``sys.modules`` before the package
gets imported so the test process never needs the real SDKs.

Broader integration runs through ``apps/workshop_bot/eval.py``.
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _install_stubs() -> None:
    """Stub the heavyweight third-party deps so the package imports cleanly."""
    if "discord" not in sys.modules:
        discord = types.ModuleType("discord")

        class _Client:  # noqa: D401 — stub
            def __init__(self, *args, **kwargs):
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

        # discord.abc submodule for type annotations like discord.abc.Messageable.
        abc_mod = types.ModuleType("discord.abc")
        abc_mod.Messageable = object  # type: ignore[attr-defined]
        sys.modules["discord"] = discord
        sys.modules["discord.abc"] = abc_mod

    if "anthropic" not in sys.modules:
        anthropic = types.ModuleType("anthropic")

        class _Anthropic:
            def __init__(self, *args, **kwargs):
                pass

        anthropic.Anthropic = _Anthropic  # type: ignore[attr-defined]
        sys.modules["anthropic"] = anthropic


_install_stubs()


from apps.workshop_bot.personas import base  # noqa: E402
from apps.workshop_bot.personas import team as team_mod  # noqa: E402
from apps.workshop_bot.tools import agent_loop, agent_tools, conversation, discord_io, issue  # noqa: E402


class IsPassResponseTests(unittest.TestCase):
    """``is_pass_response`` gates whether a peer reaction goes to the channel.
    False positives are catastrophic — the model's rationale would leak."""

    def test_plain_pass(self):
        self.assertTrue(base.is_pass_response("PASS"))

    def test_lowercase(self):
        self.assertTrue(base.is_pass_response("pass"))

    def test_with_punctuation(self):
        for s in ("PASS.", "pass!", "PASS,", "*PASS*", "**PASS**", "`PASS`", '"pass"'):
            with self.subTest(s=s):
                self.assertTrue(base.is_pass_response(s))

    def test_with_whitespace(self):
        self.assertTrue(base.is_pass_response("  PASS  \n"))

    def test_pass_with_rationale_fails(self):
        # If the model adds rationale we MUST treat it as a real reply,
        # otherwise we'd silently drop a real message.
        self.assertFalse(base.is_pass_response("PASS — nothing to add"))
        self.assertFalse(base.is_pass_response("Pass on this one"))
        self.assertFalse(base.is_pass_response("I'll pass"))

    def test_trailing_pass_after_reasoning_paragraph(self):
        # Real heartbeat output: persona shows its work, then closes with
        # PASS on its own line. Treat the trailing token as the verdict.
        text = (
            "No inbox items, no stored preferences or themes, and issue "
            "347 hasn't started drafting yet. Last three shipped issues "
            "show a steady rhythm—travel, speed, big tech movement. "
            "Nothing to flag this morning.\n\nPASS"
        )
        self.assertTrue(base.is_pass_response(text))

    def test_trailing_pass_single_newline(self):
        # Same idea without a paragraph break — just a final-line PASS.
        self.assertTrue(base.is_pass_response("scanned the queue\nPASS"))

    def test_trailing_pass_with_formatting(self):
        self.assertTrue(base.is_pass_response("nothing material\n\n**PASS**"))
        self.assertTrue(base.is_pass_response("nothing material\n`PASS`"))

    def test_pass_followed_by_content_is_not_pass(self):
        # If PASS comes first and content follows, it isn't a PASS verdict.
        self.assertFalse(
            base.is_pass_response("PASS\nactually wait, here's a thing")
        )

    def test_empty_string(self):
        self.assertFalse(base.is_pass_response(""))

    def test_none_safe(self):
        self.assertFalse(base.is_pass_response(None))  # type: ignore[arg-type]


class SplitForDiscordTests(unittest.TestCase):
    """Discord caps messages at 2000 chars; the splitter must never produce
    a chunk larger than that, and should prefer paragraph/line breaks.
    """

    def test_short_text_passthrough(self):
        out = discord_io.split_for_discord("hello world")
        self.assertEqual(out, ["hello world"])

    def test_splits_at_paragraph_break(self):
        text = "A" * 1500 + "\n\n" + "B" * 1000
        out = discord_io.split_for_discord(text)
        self.assertGreaterEqual(len(out), 2)
        for chunk in out:
            self.assertLessEqual(len(chunk), 2000)
        self.assertTrue(out[0].endswith("A"))
        self.assertTrue(out[1].startswith("B"))

    def test_long_unbroken_text_hard_cuts(self):
        text = "x" * 5000
        out = discord_io.split_for_discord(text)
        for chunk in out:
            self.assertLessEqual(len(chunk), 2000)
        # Round-tripping through the splitter shouldn't lose characters.
        self.assertEqual("".join(out), text)

    def test_custom_limit(self):
        text = "ab cd ef gh ij"
        out = discord_io.split_for_discord(text, limit=5)
        for chunk in out:
            self.assertLessEqual(len(chunk), 5)


class ShortBotNameTests(unittest.TestCase):
    """`Weekly Thing - Marky` → `Marky`. Used in conversation history so each
    persona can tell who's speaking.
    """

    def test_strips_prefix(self):
        self.assertEqual(conversation.short_bot_name("Weekly Thing - Marky"), "Marky")

    def test_no_separator(self):
        self.assertEqual(conversation.short_bot_name("Eddy"), "Eddy")

    def test_blank(self):
        self.assertEqual(conversation.short_bot_name(""), "")

    def test_takes_last_segment(self):
        self.assertEqual(
            conversation.short_bot_name("Some - Bot - Patty"), "Patty"
        )


class StripMentionsTests(unittest.TestCase):
    def test_strips(self):
        self.assertEqual(
            conversation.strip_mentions("hey <@123456> what's up"),
            "hey  what's up".strip(),
        )

    def test_strips_nick_mention(self):
        self.assertEqual(
            conversation.strip_mentions("<@!987654> ping"),
            "ping",
        )

    def test_handles_none(self):
        self.assertEqual(conversation.strip_mentions(None), "")


class TruncateMarkerTests(unittest.TestCase):
    """The truncated tool-result suffix must read as plain text — earlier
    code emitted ``..."[truncated]"`` which made the result invalid JSON."""

    def test_marker_is_plain_text(self):
        big_value = "x" * (agent_loop.MAX_TOOL_RESULT_CHARS + 10)

        def fake(_deps, **_kwargs):
            return big_value

        registry = agent_tools.ToolRegistry()
        registry.register(
            "test__huge",
            {"description": "test", "input_schema": {"type": "object", "properties": {}}},
            fake,
        )
        deps = types.SimpleNamespace(registry=registry)

        result = agent_loop._execute_tool("test__huge", deps=deps, raw_input={})
        self.assertIn("[truncated;", result)
        self.assertNotIn('..."[truncated]"', result)
        self.assertLessEqual(
            len(result), agent_loop.MAX_TOOL_RESULT_CHARS + 200
        )


class ExecuteToolRestrictedTests(unittest.TestCase):
    """The agent loop's ``_execute_tool`` must enforce ``restricted_to``
    independently of registry filtering. Even if a model invents a name
    for a restricted tool, the loop refuses to run it for a non-allowed
    persona."""

    def test_refuses_restricted_tool_for_other_persona(self):
        called = []

        def fake(_deps, **_kw):
            called.append(True)
            return {"ok": True}

        registry = agent_tools.ToolRegistry()
        registry.register(
            "vault__read",
            {"description": "test", "input_schema": {"type": "object", "properties": {}}},
            fake,
            restricted_to=frozenset({"patty"}),
        )
        deps = types.SimpleNamespace(registry=registry)

        result = agent_loop._execute_tool(
            "vault__read", deps=deps, raw_input={}, persona="eddy"
        )
        self.assertIn("not available to persona", result)
        self.assertEqual(called, [])

    def test_allows_restricted_tool_for_allowed_persona(self):
        def fake(_deps, **_kw):
            return {"ok": True}

        registry = agent_tools.ToolRegistry()
        registry.register(
            "vault__read",
            {"description": "test", "input_schema": {"type": "object", "properties": {}}},
            fake,
            restricted_to=frozenset({"patty"}),
        )
        deps = types.SimpleNamespace(registry=registry)

        result = agent_loop._execute_tool(
            "vault__read", deps=deps, raw_input={}, persona="patty"
        )
        self.assertIn('"ok": true', result)


class ComputeIssueWindowTests(unittest.TestCase):
    """``/workshop issue start`` validates inputs through ``compute_window``.
    These rules are load-bearing — once a window is committed the
    scheduler and the jobs read it, so bad data poisons the issue."""

    def test_happy_path_seven_days(self):
        # 2026-05-09 is a Saturday.
        out = issue.compute_window("2026-05-09", 7)
        self.assertEqual(out["pub_date"], "2026-05-09")
        self.assertEqual(out["end_date"], "2026-05-08")  # Friday before pub
        self.assertEqual(out["start_date"], "2026-05-01")  # 7 days earlier
        self.assertEqual(out["day_count"], 7)

    def test_double_issue(self):
        out = issue.compute_window("2026-05-09", 14)
        self.assertEqual(out["start_date"], "2026-04-24")
        self.assertEqual(out["day_count"], 14)

    def test_strips_whitespace(self):
        out = issue.compute_window("  2026-05-09  ", 7)
        self.assertEqual(out["pub_date"], "2026-05-09")

    def test_rejects_non_saturday(self):
        # 2026-05-10 is a Sunday.
        with self.assertRaises(issue.IssueWindowError) as ctx:
            issue.compute_window("2026-05-10", 7)
        self.assertIn("Sunday", str(ctx.exception))

    def test_rejects_unparseable_date(self):
        with self.assertRaises(issue.IssueWindowError):
            issue.compute_window("not-a-date", 7)

    def test_rejects_zero_day_count(self):
        with self.assertRaises(issue.IssueWindowError):
            issue.compute_window("2026-05-09", 0)

    def test_rejects_negative_day_count(self):
        with self.assertRaises(issue.IssueWindowError):
            issue.compute_window("2026-05-09", -3)

    def test_rejects_non_int_day_count(self):
        with self.assertRaises(issue.IssueWindowError):
            issue.compute_window("2026-05-09", "seven")  # type: ignore[arg-type]


class ApiSafeNameTests(unittest.TestCase):
    """Tool names go to the API verbatim — registry rejects anything
    that doesn't fit Anthropic's ``^[a-zA-Z0-9_-]{1,128}$`` regex.
    Catches accidental reintroduction of the dotted form."""

    def test_register_rejects_dotted_name(self):
        registry = agent_tools.ToolRegistry()
        with self.assertRaises(ValueError):
            registry.register(
                "archive.search",
                {"description": "x", "input_schema": {}},
                lambda _deps, **_kw: None,
            )

    def test_register_rejects_special_chars(self):
        registry = agent_tools.ToolRegistry()
        for bad in ("foo bar", "foo:bar", "foo!", "", "x" * 129):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    registry.register(
                        bad,
                        {"description": "x", "input_schema": {}},
                        lambda _deps, **_kw: None,
                    )

    def test_register_accepts_double_underscore_form(self):
        registry = agent_tools.ToolRegistry()
        registry.register(
            "archive__search",
            {"description": "x", "input_schema": {}},
            lambda _deps, **_kw: None,
        )
        self.assertIn("archive__search", registry.all_names())

    def test_build_tool_specs_passes_name_through(self):
        registry = agent_tools.ToolRegistry()
        registry.register(
            "ns__thing",
            {
                "description": "test",
                "input_schema": {"type": "object", "properties": {}},
            },
            lambda _deps, **_kw: "ok",
        )
        deps = types.SimpleNamespace(registry=registry)
        specs = agent_loop._build_tool_specs(["ns__thing"], deps=deps)
        self.assertEqual(specs[0]["name"], "ns__thing")


class ReactAddTests(unittest.TestCase):
    """``react__add`` is a tool that schedules ``Message.add_reaction`` on
    the persona's bot loop. These tests stub the bot + loop so the tool
    runs without a live Discord connection."""

    def setUp(self):
        # Wipe any context from previous tests.
        agent_tools.active_react_target.set(None)
        agent_tools.active_persona.set("eddy")

    def tearDown(self):
        agent_tools.active_react_target.set(None)
        agent_tools.active_persona.set("unknown")

    def test_no_message_in_context_returns_error(self):
        agent_tools.active_react_target.set(None)
        deps = types.SimpleNamespace(team=types.SimpleNamespace(bots={}))
        out = agent_tools.t_react_add(deps, emoji="👀")
        self.assertIn("error", out)
        self.assertIn("no message in context", out["error"])

    def test_empty_emoji_returns_error(self):
        agent_tools.active_react_target.set((1, 2))
        deps = types.SimpleNamespace(team=types.SimpleNamespace(bots={}))
        out = agent_tools.t_react_add(deps, emoji="   ")
        self.assertIn("error", out)
        self.assertIn("emoji", out["error"])

    def test_missing_team_returns_error(self):
        agent_tools.active_react_target.set((1, 2))
        deps = types.SimpleNamespace()
        out = agent_tools.t_react_add(deps, emoji="🔥")
        self.assertEqual(out, {"error": "team registry unavailable"})

    def test_persona_not_registered_returns_error(self):
        agent_tools.active_react_target.set((1, 2))
        deps = types.SimpleNamespace(team=types.SimpleNamespace(bots={}))
        out = agent_tools.t_react_add(deps, emoji="🔥")
        self.assertIn("error", out)
        self.assertIn("eddy", out["error"])

    def test_happy_path_calls_add_reaction_via_bot_loop(self):
        # Build a fake bot whose ``loop`` is a real running asyncio loop in
        # a dedicated thread, so ``run_coroutine_threadsafe`` can schedule
        # work on it from the test thread (mirrors the agent-loop worker).
        import threading

        loop_ready = threading.Event()
        loop_holder: dict = {}

        def _runner():
            loop = asyncio.new_event_loop()
            loop_holder["loop"] = loop
            asyncio.set_event_loop(loop)
            loop_ready.set()
            try:
                loop.run_forever()
            finally:
                loop.close()

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        loop_ready.wait()
        loop = loop_holder["loop"]

        try:
            captured: dict = {}

            class _FakePartialMessage:
                async def add_reaction(self, emoji):
                    captured["emoji"] = emoji
                    captured["channel_id"] = self._cid
                    captured["message_id"] = self._mid

            class _FakePartialMessageable:
                def __init__(self, cid):
                    self._cid = cid

                def get_partial_message(self, mid):
                    pm = _FakePartialMessage()
                    pm._cid = self._cid
                    pm._mid = mid
                    return pm

            class _FakeBot:
                user = object()

                def get_partial_messageable(self, cid):
                    return _FakePartialMessageable(cid)

            bot = _FakeBot()
            bot.loop = loop  # type: ignore[attr-defined]
            deps = types.SimpleNamespace(
                team=types.SimpleNamespace(bots={"eddy": bot})
            )
            agent_tools.active_react_target.set((42, 4242))

            out = agent_tools.t_react_add(deps, emoji="📝")
            self.assertEqual(out, {"ok": True, "emoji": "📝"})
            self.assertEqual(
                captured, {"emoji": "📝", "channel_id": 42, "message_id": 4242}
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2)


class TrimOrderedSetTests(unittest.TestCase):
    """``_trim_ordered_set`` evicts oldest entries first. The prior trim
    relied on plain-set order, which Python sets don't guarantee."""

    def test_trim_oldest(self):
        d: "OrderedDict[int, None]" = OrderedDict()
        for i in range(10):
            d[i] = None
        team_mod._trim_ordered_set(d, cap=4)
        self.assertEqual(list(d.keys()), [6, 7, 8, 9])

    def test_no_trim_when_under_cap(self):
        d: "OrderedDict[int, None]" = OrderedDict()
        for i in range(3):
            d[i] = None
        team_mod._trim_ordered_set(d, cap=10)
        self.assertEqual(list(d.keys()), [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
