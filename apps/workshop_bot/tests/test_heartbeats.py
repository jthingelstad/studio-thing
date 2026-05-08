"""Heartbeat dispatch tests.

The shared ``handlers.heartbeat(persona, ctx)`` handler:
- loads ``prompts/<persona>/heartbeat.md`` as the user message,
- invokes the persona's agent loop once,
- swallows ``PASS`` (silent default),
- posts non-PASS replies through ``ctx.post`` to the persona's home channel,
- short-circuits when ``WORKSHOP_HEARTBEATS_ENABLED=0``.

These tests stub the agent loop and ``ctx.post`` so the suite doesn't
hit Anthropic or Discord.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


from apps.workshop_bot.scheduler import handlers  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402


class _FakeCtx:
    """Minimal stand-in for scheduler.runner.JobContext."""

    def __init__(self, bot, channel):
        self._bot = bot
        self._channel = channel
        self.posted: list[str] = []

    def bot(self, persona):
        return self._bot

    def channel(self, env_var, *, persona=None):
        return self._channel

    async def post(self, channel, text, *, suppress_embeds=False):
        self.posted.append(text)


def _async_return(value):
    async def _coro(*args, **kwargs):
        return value
    return _coro


def _make_bot(*, persona="marky", reply: str = "PASS"):
    bot = MagicMock()
    bot.persona = persona
    bot.home_channel_env = "DISCORD_CHANNEL_PROMOTION"
    # bot.core returns (answer, meta).
    bot.core = AsyncMock(return_value=(reply, {"iterations": 1, "usage": {}}))
    return bot


class HeartbeatDispatchTests(unittest.TestCase):
    def setUp(self):
        # Ensure the var defaults to enabled.
        self._orig_enabled = os.environ.get("WORKSHOP_HEARTBEATS_ENABLED")
        os.environ.pop("WORKSHOP_HEARTBEATS_ENABLED", None)
        # Use a temp DB so AgentRun rows from heartbeats don't pollute.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig_enabled is None:
            os.environ.pop("WORKSHOP_HEARTBEATS_ENABLED", None)
        else:
            os.environ["WORKSHOP_HEARTBEATS_ENABLED"] = self._orig_enabled
        if self._orig_db is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_db
        self._tmpdir.cleanup()

    def test_pass_swallowed_no_post(self):
        bot = _make_bot(persona="marky", reply="PASS")
        ctx = _FakeCtx(bot=bot, channel=MagicMock())
        asyncio.run(handlers.heartbeat("marky", ctx))
        self.assertTrue(bot.core.await_count == 1)
        self.assertEqual(ctx.posted, [])

    def test_non_pass_posts_to_home_channel(self):
        reply = "Marky here — referral spike on dd-2026-05-15."
        bot = _make_bot(persona="marky", reply=reply)
        ctx = _FakeCtx(bot=bot, channel=MagicMock())
        asyncio.run(handlers.heartbeat("marky", ctx))
        self.assertEqual(ctx.posted, [reply])

    def test_loads_persona_heartbeat_prompt(self):
        bot = _make_bot(persona="marky", reply="PASS")
        ctx = _FakeCtx(bot=bot, channel=MagicMock())
        asyncio.run(handlers.heartbeat("marky", ctx))
        # bot.core was called with the heartbeat prompt body as `latest`.
        kwargs = bot.core.call_args.kwargs
        self.assertIn("latest", kwargs)
        self.assertIn("heartbeat", kwargs["latest"].lower())

    def test_disabled_short_circuits_before_loading_prompt(self):
        os.environ["WORKSHOP_HEARTBEATS_ENABLED"] = "0"
        bot = _make_bot(persona="marky", reply="anything")
        ctx = _FakeCtx(bot=bot, channel=MagicMock())
        asyncio.run(handlers.heartbeat("marky", ctx))
        # Bot.core never called.
        self.assertEqual(bot.core.await_count, 0)
        self.assertEqual(ctx.posted, [])

    def test_unknown_persona_returns_silently(self):
        ctx = _FakeCtx(bot=None, channel=MagicMock())
        # Should not raise.
        asyncio.run(handlers.heartbeat("nonexistent", ctx))
        self.assertEqual(ctx.posted, [])

    def test_pass_variants_swallowed(self):
        for variant in ("PASS", "pass", " PASS\n", "**PASS**", "`PASS`"):
            with self.subTest(variant=variant):
                bot = _make_bot(persona="marky", reply=variant)
                ctx = _FakeCtx(bot=bot, channel=MagicMock())
                asyncio.run(handlers.heartbeat("marky", ctx))
                self.assertEqual(ctx.posted, [], f"variant {variant!r} not treated as PASS")

    def test_empty_answer_treated_as_pass(self):
        bot = _make_bot(persona="marky", reply="")
        ctx = _FakeCtx(bot=bot, channel=MagicMock())
        asyncio.run(handlers.heartbeat("marky", ctx))
        self.assertEqual(ctx.posted, [])

    def test_agent_loop_exception_is_swallowed(self):
        bot = _make_bot(persona="marky", reply="ignored")
        bot.core = AsyncMock(side_effect=RuntimeError("bedrock unavailable"))
        ctx = _FakeCtx(bot=bot, channel=MagicMock())
        # Should not raise.
        asyncio.run(handlers.heartbeat("marky", ctx))
        self.assertEqual(ctx.posted, [])

    def test_passes_heartbeat_model_from_env(self):
        os.environ["WORKSHOP_HEARTBEAT_MODEL"] = "sonnet"
        try:
            bot = _make_bot(persona="marky", reply="PASS")
            ctx = _FakeCtx(bot=bot, channel=MagicMock())
            asyncio.run(handlers.heartbeat("marky", ctx))
            kwargs = bot.core.call_args.kwargs
            self.assertEqual(kwargs.get("model"), "sonnet")
        finally:
            os.environ.pop("WORKSHOP_HEARTBEAT_MODEL", None)


class HeartbeatPromptFilesTests(unittest.TestCase):
    """Smoke check that each persona has a heartbeat.md on disk and its
    contents look like a heartbeat prompt (mention `inbox` + `PASS`)."""

    def test_each_persona_has_heartbeat_md(self):
        prompts = REPO / "apps" / "workshop_bot" / "prompts"
        for persona in ("eddy", "linky", "marky", "patty"):
            with self.subTest(persona=persona):
                path = prompts / persona / "heartbeat.md"
                self.assertTrue(path.exists(), f"missing {path}")
                body = path.read_text(encoding="utf-8")
                self.assertIn("inbox", body.lower())
                self.assertIn("PASS", body)


if __name__ == "__main__":
    unittest.main()
