"""Daily-render path tolerance — the three impure for-issue wrappers
must not raise on missing atoms (day 1 of a new issue, where no intro
/ haiku / metadata yet exist). They render placeholder content where
appropriate; failures inside one renderer don't poison the other two.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
)
from apps.workshop_bot.tools import db, renderers  # noqa: E402


class DailyRenderToleranceTests(_DBTestCase):

    def _window(self, n=458, pub="2026-05-23"):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )
        return w

    def test_render_email_for_issue_with_no_atoms(self):
        """Day-1 render — no intro, no haiku, no metadata, no cta atoms.
        Must produce output without raising."""
        self._window(n=458)
        body = renderers.render_email_for_issue(458)
        # Editor-mode preamble always emitted.
        self.assertIn("<!-- buttondown-editor-mode: plaintext -->", body)
        # Tinylytics pixel present.
        self.assertIn("tinylytics.app/pixel", body)
        # No CTA Liquid blocks (no cta atoms loaded) — sections are empty.
        self.assertNotIn("{% if subscriber.subscriber_type", body)
        # buttondown.md was written to the FakeWorkspace.
        self.assertIn((458, "buttondown.md"), self.ws.files)

    def test_render_archive_for_issue_with_no_atoms(self):
        """Day-1 archive render builds frontmatter with placeholder
        metadata (no metadata.json yet) and an empty body."""
        self._window(n=458)
        archive_md, links_json = renderers.render_archive_for_issue(458)
        self.assertTrue(archive_md.startswith("---\n"))
        # Frontmatter has the issue number + placeholder subject.
        self.assertIn("number: 458", archive_md)
        self.assertIn("Weekly Thing 458 — (pending)", archive_md)
        # Body is mostly empty but the closing line still ships.
        self.assertIn("Weekly Thing on Reddit", archive_md)
        # links.json structure intact.
        self.assertIn("notable_links", links_json)
        self.assertIn("briefly_links", links_json)
        # archive.md was written to the FakeWorkspace.
        self.assertIn((458, "archive.md"), self.ws.files)
        self.assertIn((458, "links.json"), self.ws.files)

    def test_idempotent_email_render_skips_writes_on_no_change(self):
        """Re-rendering with identical inputs shouldn't trigger S3 writes
        — the renderer compares the proposed body to the local mirror and
        skips both the S3 PUT and the local write when content matches."""
        self._window(n=458)
        renderers.render_email_for_issue(458)
        # Wrap write_issue_file to count calls during the second render.
        calls = []
        original = self.ws.write_issue_file
        def counting_write(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)
        self.ws.write_issue_file = counting_write
        renderers.render_email_for_issue(458)
        # No buttondown.md write the second time around.
        self.assertEqual(
            [c for c in calls if "buttondown.md" in c],
            [],
            "second render with identical inputs wrote buttondown.md anyway",
        )

    def test_idempotent_archive_render_skips_writes_on_no_change(self):
        """Same for archive.md + links.json — second render with no input
        changes shouldn't re-PUT either file."""
        self._window(n=458)
        renderers.render_archive_for_issue(458)
        calls = []
        original = self.ws.write_issue_file
        def counting_write(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)
        self.ws.write_issue_file = counting_write
        renderers.render_archive_for_issue(458)
        wrote = [c[1] for c in calls if len(c) > 1]
        self.assertNotIn("archive.md", wrote)
        self.assertNotIn("links.json", wrote)

    def test_render_all_for_issue_partial_success_on_failure(self):
        """If one of the three renderers raises, the others should still
        complete and the result dict reflects the partial state."""
        self._window(n=458)
        # Patch render_email_body to blow up; archive and transcript
        # should still succeed.
        with patch.object(
            renderers, "render_email_body",
            side_effect=RuntimeError("forced failure"),
        ):
            result = renderers.render_all_for_issue(458)
        self.assertTrue(result["archive"])
        self.assertFalse(result["email"])
        self.assertIn("email", result["errors"])
        # Transcript runs independently of email.
        # (Whether it produced output depends on whether the archive body
        # has enough content for the audio script to find blocks — for
        # a day-1 empty issue, there may be zero blocks. The renderer
        # itself didn't raise; that's the contract.)
        self.assertNotIn("transcript", result["errors"])


if __name__ == "__main__":
    unittest.main()
