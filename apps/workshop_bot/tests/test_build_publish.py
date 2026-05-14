"""Tests for build-publish + the publish-to-Buttondown adapter. Extracted
from ``test_content_jobs.py`` in Item 1. Shared fixtures from
``tests/_fixtures.py``."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, build_publish  # noqa: E402
from apps.workshop_bot.tools import db, s3  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
    FakeWorkspace,
    filled_final as _filled_final,
    patch_s3 as _patch_s3,
)


class BuildPublishHelperTests(unittest.TestCase):
    def test_membership_block_slots_the_cta(self):
        out = build_publish._membership_block("  Become a member of the EFF crew.  ")
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", out)
        self.assertIn("{% elif subscriber.subscriber_type == 'regular' %}", out)
        self.assertIn("{% else %}", out)
        self.assertIn("{% endif %}", out)
        # CTA copy appears in the premium + regular branches (trimmed).
        self.assertEqual(out.count("Become a member of the EFF crew."), 2)
        self.assertIn("buy.stripe.com/3cs7w5eX6aXBbhm144", out)
        self.assertIn("{{ subscribe_form }}", out)

    def test_pixel_block_is_liquid_gated_and_issue_scoped(self):
        out = build_publish._pixel_block(347)
        self.assertTrue(out.startswith("{% if medium == 'email' %}"))
        self.assertIn("https://tinylytics.app/pixel/a2YQr3ZMqkySNYSwz4uF.gif?path=/email/347/", out)
        self.assertTrue(out.endswith("{% endif %}"))

    def test_for_preview_strips_liquid_and_keeps_regular_branch(self):
        raw = (
            "<!-- buttondown-editor-mode: plaintext -->Hi there.\n\n---\n\n"
            + build_publish._membership_block("Support the cause.")
            + "\n\n---\n\nA haiku to leave you with…\n\n**a  \nb  \nc**\n\n"
            + build_publish._CLOSING + "\n\n" + build_publish._pixel_block(347)
        )
        p = build_publish._for_preview(raw)
        self.assertNotIn("buttondown-editor-mode", p)
        self.assertNotIn("{%", p)
        self.assertNotIn("{{", p)
        self.assertNotIn("tinylytics.app/pixel", p)   # email-only block removed wholesale
        self.assertIn("Support the cause.", p)        # regular branch kept
        self.assertIn("$4 monthly", p)                # the buttons' text survives
        self.assertIn("Hi there.", p)
        self.assertIn("A haiku to leave you with", p)



class BuildPublishTests(_DBTestCase):
    def _window(self, n=458, pub="2026-05-16"):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window(pub, 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def _ctx(self, persona="eddy"):
        fc = _FakeBotChannel(persona=persona)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def test_refuses_with_missing_list(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        # Missing haiku.md, metadata.json, intro.md, cover.jpg.
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertFalse(result.ok)
        for r in ("haiku.md", "metadata.json", "intro.md", "cover.jpg"):
            self.assertIn(r, result.message)
        fc.channel.send.assert_awaited()  # posted the missing list

    def test_assembles_publish_md(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Welcome to the issue.")
        self.ws.write_issue_file(458, "cover.md", "Docks on the lake.\n\nApril 26, 2026  \nExcelsior, MN")
        self.ws.write_issue_file(458, "haiku.md", "line one\nline two\nline three")
        self.ws.write_issue_file(458, "currently.md", "Reading: a book.")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")  # presence only
        self.ws.write_issue_file(458, "cta-1.md", "---\nplacement: after_notable\n---\n\nSupport the EFF.")
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        # Editor-mode comment glommed onto the intro, the way the raw bodies are.
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Welcome to the issue."), pub[:80])
        self.assertIn("line two", pub)
        self.assertIn("Reading: a book.", pub)
        self.assertNotIn("<!-- block:", pub)            # markers stripped
        # Cover block — image (derived URL, native <img> tag) then the
        # caption/date/location below.
        self.assertIn(
            '<img src="https://files.thingelstad.com/weekly-thing/458/cover.jpg"',
            pub,
        )
        self.assertIn("Docks on the lake.", pub)
        # `---`-fenced, the way a real issue is.
        self.assertIn("\n\n---\n\n", pub)
        # Section order: intro → Currently → cover → Notable → Journal → Briefly → haiku.
        order = [pub.index(h) for h in (
            "## Currently", "/cover.jpg", "## Notable", "## Journal", "## Briefly",
            "A haiku to leave you with",
        )]
        self.assertEqual(order, sorted(order), pub)
        self.assertLess(pub.index("Reading: a book."), pub.index("/cover.jpg"), pub)
        # CTA with placement after_notable lands between Notable and Journal,
        # wrapped in the membership-block Liquid (premium/regular+Stripe/else+form).
        self.assertGreater(pub.index("Support the EFF."), pub.index("## Notable"))
        self.assertLess(pub.index("Support the EFF."), pub.index("## Journal"))
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", pub)
        self.assertIn("https://buy.stripe.com/3cs7w5eX6aXBbhm144?prefilled_email={{ subscriber.email | urlencode }}", pub)
        self.assertIn("{{ subscribe_form }}", pub)
        # Closing boilerplate, then the email-only Tinylytics pixel.
        self.assertIn("Check out the [Weekly Thing on Reddit]", pub)
        self.assertIn("{% if medium == 'email' %}", pub)
        self.assertIn("https://tinylytics.app/pixel/a2YQr3ZMqkySNYSwz4uF.gif?path=/email/458/", pub)
        # publish.html written too — no draft banner (it's the ship body), and
        # Liquid-stripped (a regular-subscriber rendering of the email).
        html = self.ws.files[(458, "publish.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Weekly Thing 458</title>", html)
        self.assertNotIn('class="banner"', html)
        self.assertNotIn("{% if", html)
        self.assertNotIn("{{ subscribe_form }}", html)
        self.assertNotIn("tinylytics.app/pixel", html)
        self.assertIn("Support the EFF.", html)
        self.assertIn("$4 monthly", html)
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/publish.html")

    def test_currently_json_renders_into_publish_md(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        self.ws.write_issue_file(458, "currently.json", '{"Listening":" Noah Kahan.","Watching":" Shrinking."}')
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertIn("## Currently\n\n**Listening:** Noah Kahan.\n\n**Watching:** Shrinking.", pub)

    def test_cta_default_placement_is_after_notable(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        # No `placement:` frontmatter → defaults to after_notable.
        self.ws.write_issue_file(458, "cta-1.md", "Become a member.")
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertGreater(pub.index("Become a member."), pub.index("## Notable"))
        self.assertLess(pub.index("Become a member."), pub.index("## Journal"))

    def test_no_currently_means_no_currently_heading(self):
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self.ws.write_issue_file(458, "intro.md", "Intro.")
        self.ws.write_issue_file(458, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(458, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(458, "cover.jpg", "(binary)")
        # No currently.md, no cover.md.
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "publish.md")]
        self.assertNotIn("## Currently", pub)            # empty optional section dropped
        self.assertNotIn("/cover.jpg)", pub)             # no cover.md → no cover block
        self.assertIn("## Notable", pub)
        self.assertIn("A haiku to leave you with", pub)
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Intro."), pub[:60])



class PublishToButtondownTests(unittest.TestCase):
    def setUp(self):
        # Importing pipeline/content/content.py runs load_dotenv() at module
        # load, which would pour the developer's .env into os.environ for the
        # rest of the test run (PINBOARD_API_TOKEN etc.). Snapshot + restore.
        self._env_snapshot = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_snapshot)

    def _content_module(self):
        import sys as _sys
        from pathlib import Path as _P
        cd = str(_P(__file__).resolve().parents[3] / "pipeline" / "content")
        if cd not in _sys.path:
            _sys.path.insert(0, cd)
        import content  # noqa: F401
        return content

    def test_refuses_without_publish_md(self):
        content = self._content_module()
        import types
        with patch.object(content, "_workspace_get_text", lambda n, f: None):
            with self.assertRaises(SystemExit):
                content.publish_to_buttondown(types.SimpleNamespace(issue="458", dry_run=True))

    def test_dry_run_with_assets(self):
        content = self._content_module()
        import types

        def fake_get(n, f):
            return "## Notable\n\nbody" if f == "publish.md" else '{"subject":"Weekly Thing 458 / A, B, C","description":"d","slug":"458"}'

        with patch.object(content, "_workspace_get_text", fake_get):
            # dry-run: no HTTP, no exception.
            content.publish_to_buttondown(types.SimpleNamespace(issue="458", dry_run=True))



