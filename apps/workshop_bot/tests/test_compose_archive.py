"""Tests for the compose-archive job — produces archive.md + links.json for
the website from final.md + atoms."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, compose_archive  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
    filled_final as _filled_final,
)


def _parse_archive_frontmatter(archive_md: str) -> tuple[dict, str]:
    import re

    import yaml

    m = re.match(r"^---\n(.+?)\n---\n(.*)$", archive_md, re.DOTALL)
    assert m, "archive.md is missing YAML frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


class ComposeArchiveHelperTests(unittest.TestCase):
    def test_strip_membership_markers_removes_marker_and_surrounding_blank(self):
        body = (
            "## Notable\n\nfirst link\n\n<!-- cta:1 -->\n\nsecond link\n\n"
            "## Briefly\n\nblurb\n\n<!-- thanks:1 -->\n\nlast blurb"
        )
        stripped = compose_archive._strip_membership_markers(body)
        self.assertNotIn("cta:1", stripped)
        self.assertNotIn("thanks:1", stripped)
        # Content on either side of the marker survives.
        self.assertIn("first link", stripped)
        self.assertIn("second link", stripped)
        # No leftover triple-newline gap.
        self.assertNotIn("\n\n\n", stripped)


class ComposeArchiveTests(_DBTestCase):
    def setUp(self):
        super().setUp()
        # compose_archive mirrors writes to ISSUES_ROOT — point that at a
        # tempdir so tests don't pollute the real repo's data/issues/.
        self._issues_tmp = tempfile.TemporaryDirectory()
        self._issues_patch = patch.object(
            compose_archive, "ISSUES_ROOT", Path(self._issues_tmp.name),
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

    def _seed_required_assets(self, n=458):
        self.ws.write_issue_file(n, "intro.md", "Welcome to the issue.")
        self.ws.write_issue_file(n, "haiku.md", "line one\nline two\nline three")
        self.ws.write_issue_file(
            n, "metadata.json",
            json.dumps({
                "number": n,
                "buttondown_id": "em_abc",
                "subject": "Weekly Thing 458 / Test",
                "slug": "458",
                "description": "topics, more topics, even more topics.",
                "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
                "publish_date": "2026-05-16T12:00:00Z",
                "absolute_url": "https://buttondown.com/weekly-thing/archive/458/",
            }) + "\n",
        )
        self.ws.write_issue_file(n, "cover.jpg", "(binary)")

    def test_refuses_with_missing_list(self):
        self._window()
        # Only final.md present — others missing.
        self.ws.write_issue_file(458, "final.md", _filled_final())
        ctx, fc = self._ctx()
        result = asyncio.run(compose_archive.run(ctx))
        self.assertFalse(result.ok)
        for r in ("haiku.md", "metadata.json", "intro.md", "cover.jpg"):
            self.assertIn(r, result.message)
        fc.channel.send.assert_awaited()

    def test_writes_archive_md_and_links_json(self):
        self._window()
        self._seed_required_assets()
        final = _filled_final(
            notable="### [Title A](http://a.example/post)\n\nA commentary line.",
            brief="A short blurb. → **[Bee](http://b.example/x)**",
            journal="[Tuesday @ 3:02 PM](https://www.thingelstad.com/2026/05/12/test/)\n\nA journal note.",
        )
        self.ws.write_issue_file(458, "final.md", final)

        ctx, _fc = self._ctx()
        result = asyncio.run(compose_archive.run(ctx))
        self.assertTrue(result.ok, result.message)

        # archive.md written.
        archive_md = self.ws.files[(458, "archive.md")]
        fm, body = _parse_archive_frontmatter(archive_md)
        self.assertEqual(fm["number"], 458)
        self.assertEqual(fm["buttondown_id"], "em_abc")
        self.assertEqual(fm["subject"], "Weekly Thing 458 / Test")
        self.assertEqual(fm["slug"], "458")
        # Editorial links extracted into front matter.
        self.assertEqual(len(fm["links"]), 2)
        self.assertEqual({l["domain"] for l in fm["links"]}, {"a.example", "b.example"})
        # Domains excludes excluded hosts.
        self.assertEqual(set(fm["domains"]), {"a.example", "b.example"})
        # word_count is computed (not zero) and present.
        self.assertGreater(fm["word_count"], 0)
        # Body still has the editorial content; no cta/thanks markers.
        self.assertIn("Title A", body)
        self.assertNotIn("cta:", body)
        self.assertNotIn("thanks:", body)
        # No buttondown-editor-mode preamble, no tinylytics pixel.
        self.assertNotIn("buttondown-editor-mode", archive_md)
        self.assertNotIn("tinylytics.app/pixel", archive_md)
        self.assertNotIn("{% if medium", archive_md)

        # links.json written with the same data, JSON-shaped.
        links_raw = self.ws.files[(458, "links.json")]
        links = json.loads(links_raw)
        self.assertEqual(len(links["notable_links"]), 1)
        self.assertEqual(len(links["briefly_links"]), 1)
        self.assertEqual(links["notable_links"][0]["url"], "http://a.example/post")
        self.assertEqual(links["briefly_links"][0]["url"], "http://b.example/x")
        self.assertEqual(set(links["domains"]), {"a.example", "b.example"})
        self.assertEqual(links["word_count"], fm["word_count"])

    def test_strips_cta_thanks_markers_from_body(self):
        """A final.md that carries Eddy-declared cta/thanks markers must not
        ship those markers into archive.md — they're an email-only concern."""
        self._window()
        self._seed_required_assets()
        final = _filled_final(
            notable=(
                "### [Title A](http://a.example/post)\n\nFirst.\n\n<!-- cta:1 -->\n\n"
                "### [Title B](http://b.example/q)\n\nSecond."
            ),
            brief="A blurb. → **[C](http://c.example/r)**\n\n<!-- thanks:1 -->",
            journal="[Tuesday @ 3:02 PM](https://www.thingelstad.com/2026/05/12/test/)\n\nA journal note.",
        )
        self.ws.write_issue_file(458, "final.md", final)

        ctx, _fc = self._ctx()
        result = asyncio.run(compose_archive.run(ctx))
        self.assertTrue(result.ok, result.message)

        archive_md = self.ws.files[(458, "archive.md")]
        self.assertNotIn("<!-- cta:", archive_md)
        self.assertNotIn("<!-- thanks:", archive_md)
        # Both link titles survive, regardless of marker position.
        self.assertIn("Title A", archive_md)
        self.assertIn("Title B", archive_md)
        # Body's link extraction picked up both Notable links + the Briefly link.
        fm, _body = _parse_archive_frontmatter(archive_md)
        self.assertEqual(len(fm["links"]), 3)

    def test_idempotent_on_identical_final(self):
        """Re-running compose-archive on the same final.md produces byte-
        identical archive.md and links.json."""
        self._window()
        self._seed_required_assets()
        final = _filled_final()
        self.ws.write_issue_file(458, "final.md", final)

        ctx, _fc = self._ctx()
        asyncio.run(compose_archive.run(ctx))
        first_archive = self.ws.files[(458, "archive.md")]
        first_links = self.ws.files[(458, "links.json")]

        asyncio.run(compose_archive.run(ctx))
        second_archive = self.ws.files[(458, "archive.md")]
        second_links = self.ws.files[(458, "links.json")]

        self.assertEqual(first_archive, second_archive)
        self.assertEqual(first_links, second_links)

    def test_no_window_refuses_cleanly(self):
        # No active issue window — run /eddy issue start first.
        ctx, _fc = self._ctx()
        result = asyncio.run(compose_archive.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("issue window", result.message)


if __name__ == "__main__":
    unittest.main()
