"""Tests for compose-closer — the "From the Archive" paragraph generator.

compose-closer is fired by create-final (after Jamie's ✅ on the
proposal). It reads the just-assembled baseline body, the last 6
issues' closer bodies (for anti-repetition), and an archive inventory,
then asks Sonnet for a 2-4 sentence paragraph OR the literal "SKIP".
The output lands in data/issues/{N}/closer.md on both S3 and local;
create-final then re-assembles final.md with the closer spliced in.

Tests cover: refusal paths (no window, no body, no Eddy), SKIP
handling (no closer.md written, prior closer.md cleared), happy path
(closer.md written to local + S3), prior-closer lookup (reads up to 6,
skips missing), and SKIP detection edge cases.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, compose_closer  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
)


class IsSkipTests(unittest.TestCase):
    def test_plain_skip(self):
        self.assertTrue(compose_closer._is_skip("SKIP"))

    def test_skip_case_insensitive(self):
        self.assertTrue(compose_closer._is_skip("skip"))
        self.assertTrue(compose_closer._is_skip("Skip"))

    def test_skip_with_surrounding_whitespace(self):
        self.assertTrue(compose_closer._is_skip("  SKIP  \n"))

    def test_skip_with_trailing_punctuation(self):
        self.assertTrue(compose_closer._is_skip("SKIP."))
        self.assertTrue(compose_closer._is_skip("`SKIP`"))

    def test_real_closer_is_not_skip(self):
        self.assertFalse(compose_closer._is_skip(
            "Back in WT200, Jamie wrote about the same topic. It still rings true."
        ))

    def test_empty_string_is_not_skip(self):
        self.assertFalse(compose_closer._is_skip(""))


class CleanCloserTests(unittest.TestCase):
    def test_strips_outer_code_fence(self):
        out = compose_closer._clean_closer("```\nA closer.\n```")
        self.assertEqual(out, "A closer.")

    def test_strips_markdown_code_fence(self):
        out = compose_closer._clean_closer("```markdown\nA closer.\n```")
        self.assertEqual(out, "A closer.")

    def test_preserves_inline_backticks(self):
        out = compose_closer._clean_closer("A `code` reference.")
        self.assertEqual(out, "A `code` reference.")


class PriorClosersTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._issues_root_patch = patch.object(
            compose_closer, "ISSUES_ROOT", Path(self._tmp.name),
        )
        self._issues_root_patch.start()

    def tearDown(self):
        self._issues_root_patch.stop()
        self._tmp.cleanup()

    def _seed_closer(self, n: int, text: str) -> None:
        d = compose_closer.ISSUES_ROOT / str(n)
        d.mkdir(parents=True, exist_ok=True)
        (d / "closer.md").write_text(text, encoding="utf-8")

    def test_reads_up_to_six_prior_closers_newest_first(self):
        for n in range(450, 458):
            self._seed_closer(n, f"closer for WT{n}")
        out = compose_closer._prior_closers(458)
        # Returns newest-first (457, 456, ..., 452); not 451 or 450 since cap=6.
        nums = [n for n, _ in out]
        self.assertEqual(nums, [457, 456, 455, 454, 453, 452])

    def test_skips_missing_closer_files(self):
        # Only 455 and 453 have closer.md; 457/456/454/452 don't.
        self._seed_closer(455, "wt455 closer")
        self._seed_closer(453, "wt453 closer")
        out = compose_closer._prior_closers(458)
        nums = [n for n, _ in out]
        self.assertEqual(nums, [455, 453])

    def test_no_prior_closers_returns_empty(self):
        out = compose_closer._prior_closers(458)
        self.assertEqual(out, [])

    def test_stops_at_issue_one(self):
        # For issue 3 we'd look at 2, 1, then stop (offsets > N-1 hit prev<1).
        self._seed_closer(1, "wt1 closer")
        out = compose_closer._prior_closers(3)
        nums = [n for n, _ in out]
        self.assertEqual(nums, [1])


class ComposeCloserRunTests(_DBTestCase):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        # Distinct attribute name so we don't clobber _DBTestCase's
        # self._patches (which holds the s3 fake-workspace patchers and
        # gets stopped by the parent tearDown).
        self._closer_patches = [
            patch.object(compose_closer, "ISSUES_ROOT", Path(self._tmp.name)),
            patch.object(compose_closer, "EMAILS_JSON", Path(self._tmp.name) / "emails.json"),
        ]
        for p in self._closer_patches:
            p.start()
        # Seed a small archive inventory.
        (Path(self._tmp.name) / "emails.json").write_text(json.dumps([
            {"number": 280, "subject": "Weekly Thing 280 / Foo", "publish_date": "2024-06-01T12:00:00Z"},
            {"number": 281, "subject": "Weekly Thing 281 / Bar", "publish_date": "2024-06-08T12:00:00Z"},
        ]), encoding="utf-8")

    def tearDown(self):
        for p in self._closer_patches:
            p.stop()
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        self._tmp.cleanup()
        super().tearDown()

    def _window(self, n: int = 458):
        from apps.workshop_bot.tools.content import issue as issue_mod

        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )

    def _ctx(self, reply: str = "A genuine archive moment from WT281."):
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_refuses_without_window(self):
        ctx, _fc = self._ctx()
        result = asyncio.run(compose_closer.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("issue window", result.message)

    def test_refuses_without_body(self):
        """With no baseline_body and no final.md/draft.md on S3, the job
        refuses with a clear pointer at what to run first."""
        self._window()
        ctx, _fc = self._ctx()
        result = asyncio.run(compose_closer.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no body available", result.message)

    def test_happy_path_writes_closer(self):
        """Reply is a real paragraph — closer.md gets written to both S3
        (FakeWorkspace) and local ISSUES_ROOT/458/closer.md."""
        self._window()
        ctx, fc = self._ctx(reply="In WT281, Jamie wrote about local food systems. The thread runs through this issue too.")
        result = asyncio.run(compose_closer.run(
            ctx, baseline_body="## Notable\n\n### [A](http://a)\n\nbody",
        ))
        self.assertTrue(result.ok, result.message)
        self.assertFalse(result.data["skipped"])
        self.assertTrue(result.data["closer_written"])
        # S3 mirror
        self.assertIn((458, "closer.md"), self.ws.files)
        self.assertIn("WT281", self.ws.files[(458, "closer.md")])
        # Local mirror
        local_path = compose_closer.ISSUES_ROOT / "458" / "closer.md"
        self.assertTrue(local_path.exists())
        self.assertIn("WT281", local_path.read_text(encoding="utf-8"))
        # Status message posted to #editorial
        fc.channel.send.assert_awaited()
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("compose-closer", sent)
        self.assertIn("WT458", sent)

    def test_skip_reply_writes_nothing(self):
        """Literal SKIP → no closer.md written, status posted."""
        self._window()
        ctx, fc = self._ctx(reply="SKIP")
        result = asyncio.run(compose_closer.run(
            ctx, baseline_body="## Notable\n\nbody",
        ))
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["skipped"])
        self.assertFalse(result.data["closer_written"])
        self.assertNotIn((458, "closer.md"), self.ws.files)
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("SKIP", sent)

    def test_skip_reply_clears_prior_closer(self):
        """If a closer.md was written by a prior run and the new run is
        SKIP, the prior local + S3 closer.md gets removed so the issue's
        current state reflects the SKIP."""
        self._window()
        # Seed a prior closer in both S3 and local.
        self.ws.files[(458, "closer.md")] = "old closer text\n"
        local_path = compose_closer.ISSUES_ROOT / "458" / "closer.md"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("old closer text\n", encoding="utf-8")

        ctx, _fc = self._ctx(reply="SKIP")
        result = asyncio.run(compose_closer.run(
            ctx, baseline_body="## Notable\n\nbody",
        ))
        self.assertTrue(result.ok)
        self.assertTrue(result.data["skipped"])
        # Both mirrors cleared.
        self.assertNotIn((458, "closer.md"), self.ws.files)
        self.assertFalse(local_path.exists())

    def test_empty_reply_fails_cleanly(self):
        self._window()
        ctx, fc = self._ctx(reply="")
        result = asyncio.run(compose_closer.run(
            ctx, baseline_body="## Notable\n\nbody",
        ))
        self.assertFalse(result.ok)
        self.assertIn("empty reply", result.message)


if __name__ == "__main__":
    unittest.main()
