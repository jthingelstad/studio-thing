"""Scheduler config tests.

Verify that every declared job is well-formed: unique id, parseable cron,
and a handler function that exists and is async.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
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


from apps.workshop_bot.scheduler import handlers, jobs as jobs_module  # noqa: E402


class JobConfigTests(unittest.TestCase):
    def test_unique_ids(self):
        ids = [job.id for job in jobs_module.JOBS]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate job ids: {ids}")

    def test_cron_is_5_fields(self):
        # APScheduler's full parse happens at scheduler.start(); we just want
        # to catch typos at config time.
        for job in jobs_module.JOBS:
            with self.subTest(job=job.id):
                self.assertEqual(
                    len(job.cron.split()), 5,
                    f"cron {job.cron!r} should have 5 fields",
                )

    def test_handler_resolvable_and_async(self):
        for job in jobs_module.JOBS:
            with self.subTest(job=job.id):
                self.assertTrue(callable(job.func), f"job {job.id} func is not callable")
                # Heartbeats wire ``functools.partial(handlers.heartbeat, persona=...)``
                # into ``func``. Unwrap once so the underlying coroutine
                # function and source module land cleanly.
                underlying = (
                    job.func.func if isinstance(job.func, functools.partial)
                    else job.func
                )
                self.assertTrue(
                    inspect.iscoroutinefunction(underlying),
                    f"job {job.id} func must be async",
                )
                self.assertEqual(
                    underlying.__module__,
                    handlers.__name__,
                    f"job {job.id} func should live in handlers.py",
                )

    def test_by_id_lookup(self):
        for job in jobs_module.JOBS:
            self.assertIs(jobs_module.by_id(job.id), job)
        self.assertIsNone(jobs_module.by_id("nonexistent"))

    def test_every_persona_has_a_heartbeat(self):
        heartbeat_jobs = [
            j for j in jobs_module.JOBS if j.id.endswith("-heartbeat")
        ]
        self.assertEqual(len(heartbeat_jobs), 4)
        personas = set()
        for job in heartbeat_jobs:
            self.assertIsInstance(job.func, functools.partial)
            self.assertIs(job.func.func, handlers.heartbeat)
            personas.add(job.func.keywords["persona"])
        self.assertEqual(personas, {"eddy", "linky", "marky", "patty"})

    def test_known_handlers_referenced(self):
        # Sanity: every handler we ship should be wired to a job — except
        # the explicitly folded handlers preserved as a one-release
        # safety net (see jobs.FOLDED_HANDLER_NAMES).
        wired: set[object] = set()
        for job in jobs_module.JOBS:
            underlying = (
                job.func.func if isinstance(job.func, functools.partial)
                else job.func
            )
            wired.add(underlying)
        for name in dir(handlers):
            obj = getattr(handlers, name)
            if (
                inspect.iscoroutinefunction(obj)
                and obj.__module__ == handlers.__name__
                and not name.startswith("_")
                and name not in jobs_module.FOLDED_HANDLER_NAMES
            ):
                self.assertIn(
                    obj, wired,
                    f"handler {name} is defined but no JobSpec references it",
                )


if __name__ == "__main__":
    unittest.main()
