"""Tests for compose-transcript — per-block TTS prose files written to
the issue's transcript/ directory."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, compose_transcript  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
)


class ComposeTranscriptHelperTests(unittest.TestCase):
    def test_slugify_normalizes_to_filename_safe(self):
        slugify = compose_transcript._slugify
        self.assertEqual(slugify("Now, the Notable section."), "now-the-notable-section")
        self.assertEqual(
            slugify('Link one. "OpenAI\'s Codex App"'),
            "link-one-openais-codex-app",
        )
        self.assertEqual(slugify("Quote."), "quote")
        self.assertEqual(slugify(""), "block")
        self.assertEqual(slugify("    "), "block")

    def test_slugify_caps_length(self):
        long = "a " * 100
        out = compose_transcript._slugify(long)
        self.assertLessEqual(len(out), 40)

    def test_block_filenames_zero_pad_and_index(self):
        blocks = ["A", "B", "C"]
        named = compose_transcript._block_filenames(blocks)
        self.assertEqual([name for name, _ in named], ["000-a.txt", "001-b.txt", "002-c.txt"])


class ComposeTranscriptTests(_DBTestCase):
    def setUp(self):
        super().setUp()
        # compose_transcript mirrors writes to ISSUES_ROOT — point that at a
        # tempdir so tests don't pollute the real repo's data/issues/.
        self._issues_tmp = tempfile.TemporaryDirectory()
        self._issues_patch = patch.object(
            compose_transcript, "ISSUES_ROOT", Path(self._issues_tmp.name),
        )
        self._issues_patch.start()

    def _window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools.content import issue as issue_mod

        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )

    def _ctx(self):
        fc = _FakeBotChannel(persona="eddy")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def tearDown(self):
        self._issues_patch.stop()
        self._issues_tmp.cleanup()
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _seed_archive(self, n=458, body=None):
        body = body or (
            "Welcome to the issue intro.\n\n"
            "## Notable\n\n"
            "### [Title A](http://a.example/post)\n\nA commentary line.\n\n"
            "### [Title B](http://b.example/x)\n\nMore commentary.\n\n"
            "## Briefly\n\n"
            "Short blurb. → **[C](http://c.example/r)**\n\n"
            "## Journal\n\n"
            "[Tuesday @ 3:02 PM](https://www.thingelstad.com/2026/05/12/test/)\n\n"
            "A journal note.\n"
        )
        frontmatter = (
            "---\n"
            f"number: {n}\n"
            "subject: 'Weekly Thing 458 / Test'\n"
            "publish_date: '2026-05-16T12:00:00Z'\n"
            "description: 'A test issue with several sections.'\n"
            "---\n"
        )
        self.ws.write_issue_file(n, "archive.md", frontmatter + body)

    def test_refuses_when_archive_missing(self):
        self._window()
        ctx, fc = self._ctx()
        result = asyncio.run(compose_transcript.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("archive.md", result.message)
        fc.channel.send.assert_awaited()

    def test_writes_per_block_files(self):
        self._window()
        self._seed_archive()
        ctx, _fc = self._ctx()
        result = asyncio.run(compose_transcript.run(ctx))
        self.assertTrue(result.ok, result.message)

        # All transcript files live under transcript/{NNN-slug}.txt.
        names = [
            fn[len("transcript/"):]
            for (i, fn) in self.ws.files
            if i == 458 and fn.startswith("transcript/")
        ]
        names.sort()
        self.assertGreater(len(names), 0)
        # Filename shape: zero-padded 3-digit prefix + slug + .txt.
        for name in names:
            self.assertRegex(name, r"^\d{3}-[a-z0-9-]+\.txt$")

        # Section intros land in their own files; link cues too.
        joined = "\n\n".join(
            self.ws.files[(458, f"transcript/{n}")] for n in names
        )
        self.assertIn("Now, the Notable section.", joined)
        # Each link cue starts a file (per the BLOCK_START_RE in synthesize.py).
        link_cue_files = [
            n for n in names
            if self.ws.files[(458, f"transcript/{n}")].splitlines()[0].startswith("Link ")
        ]
        # We had 2 Notable links + 1 Briefly link = 3 link cues.
        self.assertEqual(len(link_cue_files), 3)

    def test_idempotent_on_identical_archive(self):
        self._window()
        self._seed_archive()
        ctx, _fc = self._ctx()
        asyncio.run(compose_transcript.run(ctx))
        first = {
            fn: text for (i, fn), text in self.ws.files.items()
            if i == 458 and fn.startswith("transcript/")
        }
        asyncio.run(compose_transcript.run(ctx))
        second = {
            fn: text for (i, fn), text in self.ws.files.items()
            if i == 458 and fn.startswith("transcript/")
        }
        self.assertEqual(first, second)

    def test_wipes_stale_blocks_on_shrunken_re_run(self):
        """If the second run produces fewer blocks than the first (say the
        body shrank), stale higher-numbered files get cleaned up."""
        self._window()
        # First run with a fat body — many blocks.
        long_body = (
            "Intro paragraph.\n\n"
            "## Notable\n\n"
            "### [A](http://a.example)\n\ncomment\n\n"
            "### [B](http://b.example)\n\ncomment\n\n"
            "### [C](http://c.example)\n\ncomment\n\n"
            "### [D](http://d.example)\n\ncomment\n\n"
            "### [E](http://e.example)\n\ncomment\n"
        )
        self._seed_archive(body=long_body)
        ctx, _fc = self._ctx()
        asyncio.run(compose_transcript.run(ctx))
        first_count = sum(
            1 for (i, fn) in self.ws.files
            if i == 458 and fn.startswith("transcript/")
        )

        # Replace archive.md with a much shorter body.
        short_body = (
            "Quick intro.\n\n"
            "## Notable\n\n"
            "### [A](http://a.example)\n\ncomment\n"
        )
        self._seed_archive(body=short_body)
        asyncio.run(compose_transcript.run(ctx))
        second_count = sum(
            1 for (i, fn) in self.ws.files
            if i == 458 and fn.startswith("transcript/")
        )

        self.assertLess(second_count, first_count)


if __name__ == "__main__":
    unittest.main()
