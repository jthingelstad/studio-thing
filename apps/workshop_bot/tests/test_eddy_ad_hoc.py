"""Tests for /eddy's ad-hoc commands — review-text and archive-lookup."""

from __future__ import annotations

import asyncio
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

from apps.workshop_bot.jobs import _base, archive_lookup, review_text  # noqa: E402
from apps.workshop_bot.tools import db # noqa: E402
from apps.workshop_bot.tools.content import archive


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()


def _fake_eddy_team(reply: str = "Looks solid — tighten the second paragraph."):
    channel = MagicMock()
    channel.send = AsyncMock()
    eddy = MagicMock()
    eddy.user = object()
    eddy.get_channel = MagicMock(return_value=channel)
    eddy.core = AsyncMock(return_value=(reply, {"iterations": 1}))
    team = MagicMock()
    team.bots = {"eddy": eddy}
    deps = MagicMock()
    deps.team = team
    return deps, eddy, channel


class ReviewTextTests(_DBCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def test_review_posts_eddy_reply_to_editorial(self):
        deps, eddy, channel = _fake_eddy_team(reply="Tighten the second paragraph; the first is doing fine work.")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "1"
        result = asyncio.run(review_text.run(
            _base.JobContext(deps=deps), text="A sample paragraph to review.", invoker="jamie",
        ))
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["posted"])
        eddy.core.assert_awaited()
        channel.send.assert_awaited()
        # The pasted text shows up in Eddy's user message.
        sent = eddy.core.call_args.kwargs["latest"]
        self.assertIn("A sample paragraph to review.", sent)
        # The post mentions the invoker.
        posted_text = channel.send.call_args.args[0]
        self.assertIn("jamie", posted_text)

    def test_review_with_empty_text_errors(self):
        deps, eddy, channel = _fake_eddy_team()
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "1"
        result = asyncio.run(review_text.run(_base.JobContext(deps=deps), text="   "))
        self.assertFalse(result.ok)
        eddy.core.assert_not_awaited()

    def test_review_truncates_oversized_text(self):
        deps, eddy, _ = _fake_eddy_team()
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "1"
        cap = review_text._TEXT_CAP
        oversized = "x" * (cap + 5_000)
        result = asyncio.run(review_text.run(_base.JobContext(deps=deps), text=oversized))
        self.assertTrue(result.ok)
        self.assertTrue(result.data["truncated"])
        sent = eddy.core.call_args.kwargs["latest"]
        # The body inside the code fence is capped at `cap`.
        body = sent.split("```\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(len(body), cap)

    def test_review_skips_when_no_team(self):
        result = asyncio.run(review_text.run(
            _base.JobContext(deps=None), text="anything",
        ))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["posted"])


class ArchiveLookupTests(_DBCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def test_archive_lookup_summarizes_a_known_issue(self):
        deps, eddy, channel = _fake_eddy_team()
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "1"
        # Stub archive.read_issue to return a fake issue body.
        fake = {
            "number": 287,
            "frontmatter": {"subject": "Three Things About RSS", "publish_date": "2024-08-15"},
            "body": "Opening paragraph that grounds the issue.\n\n## Notable\n\nLinks here.\n\n## Briefly\n\nMore.",
            "path": "287.md",
        }
        with patch.object(archive, "read_issue", return_value=fake):
            result = asyncio.run(archive_lookup.run(_base.JobContext(deps=deps), issue_number=287))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["issue_number"], 287)
        self.assertEqual(result.data["subject"], "Three Things About RSS")
        self.assertEqual(result.data["publish_date"], "2024-08-15")
        self.assertEqual(set(result.data["sections"]), {"Notable", "Briefly"})
        # Posted to #editorial.
        self.assertTrue(result.data["posted"])
        posted = channel.send.call_args.args[0]
        self.assertIn("WT287", posted)
        self.assertIn("2024-08-15", posted)

    def test_archive_lookup_missing_issue_errors(self):
        deps, _, _ = _fake_eddy_team()
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "1"
        with patch.object(archive, "read_issue", return_value=None):
            result = asyncio.run(archive_lookup.run(_base.JobContext(deps=deps), issue_number=9999))
        self.assertFalse(result.ok)
        self.assertIn("no archive file", result.message)

    def test_archive_lookup_invalid_number_errors(self):
        result = asyncio.run(archive_lookup.run(_base.JobContext(deps=None), issue_number=-3))
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
