"""Tests for build-publish + the publish-to-Buttondown adapter.

Updated for the chunk-based editorial rework: ``final.md`` now carries
inline ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers placed by
``create-final``, and ``build-publish`` substitutes each marker with an
audience-aware Liquid block sourced from ``cta-N.md`` / ``thanks-N.md``.
``outro.md`` is a new optional asset (parallel to ``intro.md``) that
slots in between the body sections and the haiku close.
"""

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


# ---------- helper functions ----------

class BuildPublishHelperTests(unittest.TestCase):
    def test_supporter_block_wraps_in_non_member_liquid(self):
        out = build_publish._supporter_block("  Become a member of the EFF crew.  ")
        # Regular branch leads (CTA + Stripe buttons).
        self.assertIn("{% if subscriber.subscriber_type == 'regular' %}", out)
        # Anonymous / non-premium falls through to CTA + subscribe form.
        self.assertIn("{% elsif subscriber.subscriber_type != 'premium' %}", out)
        self.assertIn("{% endif %}", out)
        # CTA copy appears in both visible branches (trimmed).
        self.assertEqual(out.count("Become a member of the EFF crew."), 2)
        # Stripe upgrade buttons live in the regular branch.
        self.assertIn("buy.stripe.com/3cs7w5eX6aXBbhm144", out)
        self.assertIn("$4 monthly", out)
        self.assertIn("$40 yearly", out)
        # Anonymous branch carries the subscribe form.
        self.assertIn("{{ subscribe_form }}", out)
        # Premium members fall through to nothing — no premium-branch body.
        self.assertNotIn("{% if subscriber.subscriber_type == 'premium' %}", out)

    def test_thanks_block_wraps_in_premium_only_liquid(self):
        out = build_publish._thanks_block("  Thank you for being a Supporting Member.  ")
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", out)
        self.assertIn("{% endif %}", out)
        # Thanks copy appears exactly once (trimmed).
        self.assertEqual(out.count("Thank you for being a Supporting Member."), 1)
        # No CTA / Stripe / subscribe — thanks is a member-only block.
        self.assertNotIn("buy.stripe.com", out)
        self.assertNotIn("{{ subscribe_form }}", out)

    def test_pixel_block_is_liquid_gated_and_issue_scoped(self):
        out = build_publish._pixel_block(347)
        self.assertTrue(out.startswith("{% if medium == 'email' %}"))
        self.assertIn("https://tinylytics.app/pixel/a2YQr3ZMqkySNYSwz4uF.gif?path=/email/347/", out)
        self.assertTrue(out.endswith("{% endif %}"))

    def test_for_preview_strips_liquid_and_renders_regular_branch(self):
        """Preview = a regular-subscriber rendering. Supporter CTA + Stripe
        buttons visible; thanks block hidden (regulars don't see thanks);
        editor-mode comment and email-only pixel dropped."""
        raw = (
            "<!-- buttondown-editor-mode: plaintext -->Hi there.\n\n---\n\n"
            + build_publish._supporter_block("Support the cause.")
            + "\n\n---\n\n"
            + build_publish._thanks_block("Members-only thanks.")
            + "\n\n---\n\nA haiku to leave you with…\n\n**a  \nb  \nc**\n\n"
            + build_publish._CLOSING + "\n\n" + build_publish._pixel_block(347)
        )
        p = build_publish._for_preview(raw)
        self.assertNotIn("buttondown-editor-mode", p)
        self.assertNotIn("{%", p)
        self.assertNotIn("{{", p)
        self.assertNotIn("tinylytics.app/pixel", p)        # email-only block removed
        self.assertIn("Support the cause.", p)             # regular branch kept
        self.assertIn("$4 monthly", p)                     # Stripe buttons survive
        self.assertNotIn("Members-only thanks.", p)        # premium-only block hidden
        self.assertIn("Hi there.", p)
        self.assertIn("A haiku to leave you with", p)

    def test_discover_marker_slots(self):
        body = (
            "## Notable\n\nfirst\n\n<!-- cta:1 -->\n\nmore notable\n\n"
            "## Briefly\n\nblurb\n\n<!-- thanks:1 -->\n\n<!-- cta:2 -->"
        )
        slots = build_publish._discover_marker_slots(body)
        self.assertEqual(slots, [("cta", 1), ("thanks", 1), ("cta", 2)])

    def test_discover_marker_slots_dedupes(self):
        body = "<!-- cta:1 -->\n\nsome content\n\n<!-- cta:1 -->"
        self.assertEqual(build_publish._discover_marker_slots(body), [("cta", 1)])


# ---------- end-to-end build-publish ----------

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

    def _seed_required_assets(self, n=458):
        """Write the REQUIRED assets so build-publish doesn't refuse upstream."""
        self.ws.write_issue_file(n, "intro.md", "Welcome to the issue.")
        self.ws.write_issue_file(n, "haiku.md", "line one\nline two\nline three")
        self.ws.write_issue_file(n, "metadata.json", '{"subject":"x"}')
        self.ws.write_issue_file(n, "cover.jpg", "(binary)")  # presence only

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

    def test_refuses_when_marker_has_no_copy_file(self):
        """If final.md declares a `<!-- cta:1 -->` slot but cta-1.md is
        missing (or empty), build-publish must refuse with a missing-list
        entry pointing at `/patty cta` — so a half-finished issue never
        ships with an empty membership block."""
        self._window()
        final_with_marker = _filled_final(
            notable="### [A](http://a)\n\nfirst\n\n<!-- cta:1 -->"
        )
        self.ws.write_issue_file(458, "final.md", final_with_marker)
        self._seed_required_assets()
        # cta-1.md missing.
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("cta-1.md", result.message)
        self.assertIn("/patty cta", result.message)

    def test_assembles_buttondown_md_with_marker_substitution(self):
        self._window()
        # In the row-backed model, final.md is already assembled with the
        # atoms inlined — the assembler bakes intro / currently / cover /
        # haiku into the file at create-final time. The build-publish
        # transform just substitutes markers + adds editor-mode + pixel.
        final_with_marker = _filled_final(
            notable=(
                "### [A](http://a)\n\nbody A\n\n\n"
                "### [B](http://b)\n\nbody B\n\n<!-- cta:1 -->"
            ),
            intro="Welcome to the issue.",
            currently="**Reading:** a book.",
            cover=(
                '<img src="https://files.thingelstad.com/weekly-thing/458/cover.jpg" '
                'alt="cover" />\n\nDocks on the lake.\n\nApril 26, 2026  \nExcelsior, MN'
            ),
            haiku="**line one  \nline two  \nline three**",
        )
        self.ws.write_issue_file(458, "final.md", final_with_marker)
        self._seed_required_assets()
        self.ws.write_issue_file(
            458, "cta-1.md", "---\nkind: supporter\n---\n\nSupport the EFF.",
        )
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        # Editor-mode comment glommed onto the intro.
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Welcome to the issue."), pub[:80])
        self.assertIn("line two", pub)
        self.assertIn("Reading:", pub)
        self.assertNotIn("<!-- block:", pub)  # block markers stripped
        # Marker substituted — the raw `<!-- cta:1 -->` shouldn't appear,
        # the supporter Liquid block + the CTA copy should.
        self.assertNotIn("<!-- cta:1 -->", pub)
        self.assertIn("Support the EFF.", pub)
        # The non-member Liquid wrapper.
        self.assertIn("{% if subscriber.subscriber_type == 'regular' %}", pub)
        self.assertIn("{% elsif subscriber.subscriber_type != 'premium' %}", pub)
        self.assertIn(
            "https://buy.stripe.com/3cs7w5eX6aXBbhm144?prefilled_email={{ subscriber.email | urlencode }}",
            pub,
        )
        self.assertIn("{{ subscribe_form }}", pub)
        # Section order: intro → Currently → cover → Notable → Journal → Briefly → haiku.
        order = [pub.index(h) for h in (
            "## Currently", "/cover.jpg", "## Notable", "## Journal", "## Briefly",
            "A haiku to leave you with",
        )]
        self.assertEqual(order, sorted(order), pub)
        # CTA inline placement: sits after item B's body, before the next
        # section. It must NOT come before "## Notable" (it's inside Notable).
        cta_pos = pub.index("Support the EFF.")
        self.assertGreater(cta_pos, pub.index("body B"))
        self.assertLess(cta_pos, pub.index("## Journal"))
        # Closing boilerplate + tracking pixel.
        self.assertIn("Check out the [Weekly Thing on Reddit]", pub)
        self.assertIn("{% if medium == 'email' %}", pub)
        self.assertIn("https://tinylytics.app/pixel/a2YQr3ZMqkySNYSwz4uF.gif?path=/email/458/", pub)
        # buttondown.html written too — Liquid-stripped, regular-subscriber view.
        html = self.ws.files[(458, "buttondown.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Weekly Thing 458</title>", html)
        self.assertNotIn('class="banner"', html)
        self.assertNotIn("{% if", html)
        self.assertNotIn("{{ subscribe_form }}", html)
        self.assertNotIn("tinylytics.app/pixel", html)
        self.assertIn("Support the EFF.", html)
        self.assertIn("$4 monthly", html)
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/buttondown.html")

    def test_thanks_marker_resolves_to_premium_only_block(self):
        """A `<!-- thanks:1 -->` marker in final.md is substituted with a
        premium-only Liquid conditional sourced from thanks-1.md. The
        preview (regular-subscriber view) hides it."""
        self._window()
        final_with_marker = _filled_final(
            brief="A blurb. → **[B](http://b)**\n\n<!-- thanks:1 -->"
        )
        self.ws.write_issue_file(458, "final.md", final_with_marker)
        self._seed_required_assets()
        self.ws.write_issue_file(
            458, "thanks-1.md", "---\nkind: thanks\n---\n\nThank you for keeping this free.",
        )
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        self.assertNotIn("<!-- thanks:1 -->", pub)
        self.assertIn("Thank you for keeping this free.", pub)
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", pub)
        # Preview hides the thanks (regular subscribers don't see it).
        html = self.ws.files[(458, "buttondown.html")]
        self.assertNotIn("Thank you for keeping this free.", html)

    def test_outro_appears_when_inlined_in_final(self):
        # In the row-backed model, outro is baked into final.md at
        # create-final time. build-publish passes it through.
        self._window()
        self.ws.write_issue_file(
            458, "final.md",
            _filled_final(outro="Closing thought — see you next week."),
        )
        self._seed_required_assets()
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        outro_pos = pub.index("Closing thought — see you next week.")
        self.assertGreater(outro_pos, pub.index("## Briefly"))
        self.assertLess(outro_pos, pub.index("A haiku to leave you with"))

    def test_missing_outro_drops_cleanly(self):
        """No outro in final.md → no orphan outro in buttondown.md."""
        self._window()
        self.ws.write_issue_file(458, "final.md", _filled_final())
        self._seed_required_assets()
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        self.assertIn("## Briefly", pub)
        self.assertIn("A haiku to leave you with", pub)

    def test_currently_inlined_in_final_renders_into_publish(self):
        self._window()
        self.ws.write_issue_file(
            458, "final.md",
            _filled_final(
                intro="Intro.",
                currently="**Listening:** Noah Kahan.\n\n**Watching:** Shrinking.",
            ),
        )
        self._seed_required_assets()
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        self.assertIn("## Currently\n\n**Listening:** Noah Kahan.\n\n**Watching:** Shrinking.", pub)

    # ---------- featured (promoted) sections ----------
    # In the row-backed model, promoted sections splice inline into
    # final.md at create-final time (covered by
    # test_compose_jobs.CreateFinalTests.test_*_splices_inline). Here
    # we only verify the publish path passes inline ``## Heading``
    # sections through unchanged.

    def test_inline_featured_section_passes_through(self):
        self._window()
        # final.md with a manually-inlined featured section between
        # Notable and Journal — mirrors what create-final emits.
        final = _filled_final()
        final = final.replace(
            "<!-- /block:notable -->",
            "<!-- /block:notable -->\n\n---\n\n## Featured: The Big Read\n\n### [Original](http://orig)\n\nfeature body para.",
            1,
        )
        self.ws.write_issue_file(458, "final.md", final)
        self._seed_required_assets()
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        self.assertIn("## Featured: The Big Read", pub)
        feat_pos = pub.index("## Featured: The Big Read")
        notable_pos = pub.index("## Notable")
        journal_pos = pub.index("## Journal")
        self.assertLess(notable_pos, feat_pos)
        self.assertLess(feat_pos, journal_pos)

    def test_no_currently_means_no_currently_heading(self):
        self._window()
        # _filled_final without currently → empty currently block in
        # final.md; the publish-strip cleanup drops the orphan heading.
        self.ws.write_issue_file(458, "final.md", _filled_final(intro="Intro."))
        self._seed_required_assets()
        ctx, fc = self._ctx()
        result = asyncio.run(build_publish.run(ctx))
        self.assertTrue(result.ok, result.message)
        pub = self.ws.files[(458, "buttondown.md")]
        self.assertNotIn("## Currently", pub)
        self.assertNotIn("/cover.jpg)", pub)
        self.assertIn("## Notable", pub)
        self.assertIn("A haiku to leave you with", pub)
        # Intro from final.md present.
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Intro."), pub[:80])
        self.assertTrue(pub.startswith("<!-- buttondown-editor-mode: plaintext -->Intro."), pub[:60])


class PublishToButtondownTests(unittest.TestCase):
    def setUp(self):
        # Importing pipeline/content/content.py runs load_dotenv() at module
        # load, which would pour the developer's .env into os.environ for the
        # rest of the test run. Snapshot + restore.
        self._env_snapshot = dict(os.environ)
        # Buttondown's `headers()` insists on a non-empty API key. Set a
        # fake one so PATCH / POST construct cleanly; all actual HTTP is
        # patched out in each test.
        os.environ["BUTTONDOWN_API_KEY"] = "test-key-not-real"

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

    @staticmethod
    def _fake_workspace_get(*, meta_overrides: dict | None = None):
        """Build a ``_workspace_get_text`` stub that returns a canonical
        buttondown.md + metadata.json for tests. ``meta_overrides`` patches
        the metadata.json before serialising — handy for toggling
        ``buttondown_id``."""
        meta = {
            "subject": "Weekly Thing 458 / A, B, C",
            "description": "d",
            "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
            "slug": "458",
            "publish_date": "2026-05-17T12:00:00Z",  # must NOT be sent to Buttondown
        }
        meta.update(meta_overrides or {})
        meta_json = json.dumps(meta)

        def fake_get(_n: str, filename: str):
            if filename == "buttondown.md":
                return "## Notable\n\nbody"
            if filename == "metadata.json":
                return meta_json
            return None
        return fake_get

    def test_refuses_without_buttondown_md(self):
        content = self._content_module()
        import types
        with patch.object(content, "_workspace_get_text", lambda n, f: None):
            with self.assertRaises(SystemExit):
                content.publish_to_buttondown(types.SimpleNamespace(issue="458", dry_run=True))

    def test_dry_run_with_assets_shows_would_create(self):
        content = self._content_module()
        import types
        with patch.object(content, "_workspace_get_text", self._fake_workspace_get()):
            content.publish_to_buttondown(types.SimpleNamespace(issue="458", dry_run=True))

    def test_dry_run_with_existing_id_says_would_update(self):
        """If metadata.json already carries a ``buttondown_id``, the
        dry-run reports ``would_update`` (and the real run would PATCH)."""
        content = self._content_module()
        result = content.buttondown_publish_idempotent(
            "458",
            dry_run=True,
        ) if False else None  # placeholder for clarity
        with patch.object(
            content, "_workspace_get_text",
            self._fake_workspace_get(meta_overrides={"buttondown_id": "abc-123"}),
        ):
            result = content.buttondown_publish_idempotent("458", dry_run=True)
        self.assertEqual(result["action"], "would_update")
        self.assertEqual(result["id"], "abc-123")

    def test_first_run_posts_and_persists_id(self):
        """No ``buttondown_id`` in metadata → POST → response id is
        written back to ``metadata.json`` so subsequent runs PATCH."""
        content = self._content_module()
        # Capture what gets written back to metadata.json.
        put_calls: list[tuple[str, str, str]] = []

        def fake_put(n, filename, body):
            put_calls.append((n, filename, body))

        def fake_post(url, headers=None, json=None):
            self.assertTrue(url.endswith("/emails"))
            # publish_date must NOT appear in the payload.
            self.assertNotIn("publish_date", json)
            self.assertEqual(json["status"], "draft")
            self.assertEqual(json["slug"], "458")
            resp = MagicMock()
            resp.status_code = 201
            resp.text = '{"id":"new-uuid-001"}'
            resp.json.return_value = {"id": "new-uuid-001"}
            return resp

        with patch.object(content, "_workspace_get_text", self._fake_workspace_get()), \
             patch.object(content, "_workspace_put_text", fake_put), \
             patch.object(content, "requests") as fake_requests:
            fake_requests.post.side_effect = fake_post
            result = content.buttondown_publish_idempotent("458")
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["id"], "new-uuid-001")
        # buttondown_id was persisted back to metadata.json.
        self.assertEqual(len(put_calls), 1)
        n, filename, body = put_calls[0]
        self.assertEqual(filename, "metadata.json")
        persisted = json.loads(body)
        self.assertEqual(persisted["buttondown_id"], "new-uuid-001")

    def test_subsequent_run_patches_existing_draft(self):
        """``buttondown_id`` present → PATCH that draft; no POST, no
        metadata.json write."""
        content = self._content_module()
        put_calls: list[tuple] = []

        def fake_patch(url, headers=None, json=None):
            self.assertTrue(url.endswith("/emails/abc-123"))
            self.assertNotIn("publish_date", json)
            self.assertEqual(json["body"], "## Notable\n\nbody")
            resp = MagicMock()
            resp.status_code = 200
            resp.text = '{"id":"abc-123"}'
            resp.json.return_value = {"id": "abc-123"}
            return resp

        with patch.object(
            content, "_workspace_get_text",
            self._fake_workspace_get(meta_overrides={"buttondown_id": "abc-123"}),
        ), patch.object(content, "_workspace_put_text", lambda *a: put_calls.append(a)), \
             patch.object(content, "requests") as fake_requests:
            fake_requests.patch.side_effect = fake_patch
            # POST mock just so a stray call would error out visibly.
            fake_requests.post.side_effect = AssertionError("POST shouldn't be called when PATCH succeeds")
            result = content.buttondown_publish_idempotent("458")
        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["id"], "abc-123")
        # metadata.json not rewritten on a successful PATCH.
        self.assertEqual(put_calls, [])

    def test_patch_404_falls_back_to_post(self):
        """If the draft was deleted in Buttondown's UI, PATCH 404s — the
        publisher falls through to POST and overwrites buttondown_id."""
        content = self._content_module()
        put_calls: list[tuple] = []

        def fake_patch(url, headers=None, json=None):
            resp = MagicMock()
            resp.status_code = 404
            resp.text = '{"error":"not found"}'
            return resp

        def fake_post(url, headers=None, json=None):
            resp = MagicMock()
            resp.status_code = 201
            resp.text = '{"id":"replacement-uuid"}'
            resp.json.return_value = {"id": "replacement-uuid"}
            return resp

        with patch.object(
            content, "_workspace_get_text",
            self._fake_workspace_get(meta_overrides={"buttondown_id": "abc-123"}),
        ), patch.object(content, "_workspace_put_text", lambda *a: put_calls.append(a)), \
             patch.object(content, "requests") as fake_requests:
            fake_requests.patch.side_effect = fake_patch
            fake_requests.post.side_effect = fake_post
            result = content.buttondown_publish_idempotent("458")
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["id"], "replacement-uuid")
        # New id persisted.
        self.assertEqual(len(put_calls), 1)
        persisted = json.loads(put_calls[0][2])
        self.assertEqual(persisted["buttondown_id"], "replacement-uuid")

    def test_buttondown_error_raises_typed_exception(self):
        content = self._content_module()

        def fake_post(url, headers=None, json=None):
            resp = MagicMock()
            resp.status_code = 422
            resp.text = '{"error":"validation failed"}'
            return resp

        with patch.object(content, "_workspace_get_text", self._fake_workspace_get()), \
             patch.object(content, "requests") as fake_requests:
            fake_requests.post.side_effect = fake_post
            with self.assertRaises(content.ButtondownPublishError) as cx:
                content.buttondown_publish_idempotent("458")
        self.assertIn("422", str(cx.exception))

    def test_publish_date_never_in_payload_full_flow(self):
        """Belt-and-suspenders: even when metadata.json explicitly has a
        publish_date, the Buttondown payload omits it. Jamie schedules
        the send manually in the UI."""
        content = self._content_module()
        captured_payloads: list[dict] = []

        def fake_post(url, headers=None, json=None):
            captured_payloads.append(json)
            resp = MagicMock()
            resp.status_code = 201
            resp.text = '{"id":"u"}'
            resp.json.return_value = {"id": "u"}
            return resp

        with patch.object(
            content, "_workspace_get_text",
            self._fake_workspace_get(meta_overrides={"publish_date": "2026-05-17T12:00:00Z"}),
        ), patch.object(content, "_workspace_put_text", lambda *a: None), \
             patch.object(content, "requests") as fake_requests:
            fake_requests.post.side_effect = fake_post
            content.buttondown_publish_idempotent("458")
        self.assertEqual(len(captured_payloads), 1)
        self.assertNotIn("publish_date", captured_payloads[0])
