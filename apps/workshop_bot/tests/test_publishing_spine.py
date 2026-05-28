"""Tests for the publishing spine — phase state, the three phase cards
(Build / Publish / Share), the Echoes rename, and the persistent button Views.

See docs/publishing-process.md for the model.
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

from apps.workshop_bot.jobs import (  # noqa: E402
    _base,
    build_card,
    compose_cta,
    promotion_prep,
    publish_card,
    put_to_bed,
    share_card,
)
from apps.workshop_bot.tools import db, renderers  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase as _DBTestCase, filled_final  # noqa: E402
from apps.workshop_bot.personas.views import build_card_view, publish_card_view, share_card_view  # noqa: E402


def _window(n=458, pub="2026-05-23"):
    from apps.workshop_bot.tools.content import issue as issue_mod
    w = issue_mod.compute_window(pub, 7)
    db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                        start_date=w["start_date"], day_count=w["day_count"], set_by="test")


class PhaseModelTests(_DBTestCase):
    def test_start_seeds_build_phase(self):
        _window(458)
        self.assertEqual(db.get_active_issue_window()["phase"], "build")

    def test_set_phase_and_cards(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")
        self.assertIsNone(db.get_issue_card(458, "build"))
        db.set_issue_card(458, "build", message_id=11, channel_id=22)
        db.set_issue_card(458, "publish", message_id=33, channel_id=44)
        self.assertEqual(db.get_issue_card(458, "build"), {"message_id": 11, "channel_id": 22})
        db.clear_issue_cards(458, "build")
        self.assertIsNone(db.get_issue_card(458, "build"))
        self.assertIsNotNone(db.get_issue_card(458, "publish"))
        db.clear_issue_cards(458)  # all
        self.assertIsNone(db.get_issue_card(458, "publish"))


class BuildCardTests(_DBTestCase):
    def _seed_full_content(self, n=458):
        self.ws.write_issue_file(n, "draft.md", filled_final(intro="Opening.", haiku="a\nb\nc"))
        self.ws.write_issue_file(n, "intro.md", "Opening.")
        self.ws.write_issue_file(n, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(n, "cover.jpg", "binary")

    def test_anatomy_in_reading_order_and_build_ready(self):
        _window(458)
        self._seed_full_content()
        st = build_card.gather_state(458)
        self.assertTrue(st["build_ready"])
        lines = build_card.render_anatomy_lines(st)
        labels = [l.split(" — ")[0].split(" ", 1)[1] for l in lines]  # strip the ✅/☐ icon
        # Haiku moved to Publish phase (Eddy writes it via compose-haiku
        # off the Publish card; not authored content). Build anatomy is
        # the content Jamie authors.
        self.assertEqual(
            labels,
            ["Intro", "Currently", "Cover", "Notable", "Journal", "Briefly", "Outro"],
        )

    def test_build_not_ready_without_content(self):
        _window(459, pub="2026-05-30")
        # Empty workspace → no sections/intro/cover.
        st = build_card.gather_state(459)
        self.assertFalse(st["build_ready"])

    def test_embed_titled_build_with_anatomy_field(self):
        _window(458)
        self._seed_full_content()
        embed = build_card.render_embed(build_card.gather_state(458))
        self.assertIn("Build · WT458", embed.title)
        names = [f["name"] for f in embed.fields]
        self.assertIn("The issue (reading order)", names)

    def test_mark_built_refuses_when_not_ready(self):
        _window(459, pub="2026-05-30")
        res = asyncio.run(build_card.mark_built(_base.JobContext()))
        self.assertFalse(res.ok)
        self.assertIn("isn't built", res.message.lower())
        self.assertEqual(db.get_active_issue_window()["phase"], "build")

    def test_mark_built_flips_to_publish_when_ready(self):
        _window(458)
        self._seed_full_content()
        with patch.object(publish_card, "post_or_update", new=AsyncMock(return_value=1)), \
             patch.object(compose_cta, "run", new=AsyncMock(return_value=_base.JobResult(True, "ok"))):
            res = asyncio.run(build_card.mark_built(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")

    def test_mark_built_recovers_when_compose_cta_raises(self):
        # If Patty's compose-cta auto-request blows up (Anthropic flake,
        # bug in the prompt, etc.), the phase still flips to Publish and
        # the user-facing ack is success — the Publish card just shows
        # "CTA — pending" so Jamie can pick a framing manually. The
        # logged exception is the recovery signal; the ship doesn't stall.
        _window(458)
        self._seed_full_content()
        with patch.object(publish_card, "post_or_update", new=AsyncMock(return_value=1)), \
             patch.object(compose_cta, "run", new=AsyncMock(side_effect=RuntimeError("LLM hiccup"))):
            res = asyncio.run(build_card.mark_built(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")

    def test_reopen_flips_publish_back_to_build(self):
        # Operator catches a content issue post-mark-built — `/eddy issue
        # reopen` flips phase back so the Build card surfaces again.
        _window(458)
        db.set_issue_phase(458, "publish")
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")
        with patch.object(build_card, "post_or_update", new=AsyncMock(return_value=42)) as mock_post:
            res = asyncio.run(build_card.reopen(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(db.get_active_issue_window()["phase"], "build")
        # Build card re-posted as part of the flip.
        mock_post.assert_awaited_once()

    def test_reopen_no_op_when_no_active_window(self):
        # Defensive: no active issue → reopen refuses cleanly, doesn't try
        # to mutate state or post a card.
        with patch.object(build_card, "post_or_update", new=AsyncMock()) as mock_post:
            res = asyncio.run(build_card.reopen(_base.JobContext()))
        self.assertFalse(res.ok)
        mock_post.assert_not_awaited()


class PublishCardTests(_DBTestCase):
    def _seed_built(self, n=458, *, subject="", description="", buttondown_id=""):
        self.ws.write_issue_file(n, "draft.md", filled_final(intro="x", haiku="a\nb\nc"))
        self.ws.write_issue_file(n, "intro.md", "x")
        self.ws.write_issue_file(n, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(n, "cover.jpg", "bin")
        meta = {"number": n, "slug": str(n)}
        if subject:
            meta["subject"] = subject
        if description:
            meta["description"] = description
        if buttondown_id:
            meta["buttondown_id"] = buttondown_id
            meta["absolute_url"] = "https://weekly.thingelstad.com/archive/%d/" % n
        self.ws.write_issue_file(n, "metadata.json", json.dumps(meta))

    def test_email_gate_needs_subject_and_description(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="WT458 — Test")  # no description
        st = publish_card.gather_state(458)
        self.assertFalse(st["gates"][publish_card.BTN_EMAIL])
        self.assertIn("description", st["email_missing"])
        # With both, email is ready.
        self._seed_built(subject="WT458 — Test", description="a, b, c")
        st = publish_card.gather_state(458)
        self.assertTrue(st["gates"][publish_card.BTN_EMAIL])

    def test_website_gate_opens_after_buttondown(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d", buttondown_id="em_x")
        st = publish_card.gather_state(458)
        self.assertTrue(st["email_shipped"])
        self.assertTrue(st["gates"][publish_card.BTN_WEBSITE])

    def test_embed_has_channels_field(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        embed = publish_card.render_embed(publish_card.gather_state(458))
        self.assertIn("Publish · WT458", embed.title)
        self.assertIn("Channels", [f["name"] for f in embed.fields])

    def test_recompose_gate_off_when_thesis_and_echoes_present(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        # Both atoms present → no recompose needed.
        self.ws.write_issue_file(458, "thesis.md", "An issue about X.")
        self.ws.write_issue_file(458, "echoes.md", "Echoes prose.")
        st = publish_card.gather_state(458)
        self.assertFalse(st["thesis_failed"])
        self.assertFalse(st["echoes_failed"])
        self.assertFalse(st["recompose_needed"])
        self.assertFalse(st["gates"][publish_card.BTN_RECOMPOSE])

    def test_recompose_gate_on_when_thesis_failed_in_publish(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        # Echoes present, thesis missing → recompose needed.
        self.ws.write_issue_file(458, "echoes.md", "Echoes prose.")
        st = publish_card.gather_state(458)
        self.assertTrue(st["thesis_failed"])
        self.assertFalse(st["echoes_failed"])
        self.assertTrue(st["recompose_needed"])
        self.assertTrue(st["gates"][publish_card.BTN_RECOMPOSE])

    def test_recompose_gate_off_in_build_phase(self):
        # In build phase, thesis + echoes haven't been auto-fired yet,
        # so their absence isn't a failure — recompose stays disabled.
        _window(458)
        # phase defaults to 'build'
        self._seed_built(subject="", description="")
        st = publish_card.gather_state(458)
        self.assertFalse(st["thesis_failed"])
        self.assertFalse(st["echoes_failed"])
        self.assertFalse(st["recompose_needed"])
        self.assertFalse(st["gates"][publish_card.BTN_RECOMPOSE])

    def test_render_shows_failure_marker_for_failed_echoes(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        self.ws.write_issue_file(458, "thesis.md", "An issue about X.")
        # Echoes missing in publish phase → failure line.
        st = publish_card.gather_state(458)
        lines = publish_card.render_shared_lines(st)
        echoes_line = next(l for l in lines if "Echoes" in l)
        self.assertIn("❌", echoes_line)
        self.assertIn("compose-echoes failed", echoes_line)


class ShareCardTests(_DBTestCase):
    def test_targets_last_published_issue(self):
        # No issues filed → no card state.
        self.assertIsNone(share_card.gather_state().get("issue_number"))
        # File one issue into the `issues` table.
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO issues (number, subject, publish_date, era) VALUES (?, ?, ?, ?)",
                (348, "WT348 — Prior", "2026-05-16", "buttondown"),
            )
        st = share_card.gather_state()
        self.assertEqual(st["issue_number"], 348)
        embed = share_card.render_embed(st)
        self.assertIn("Share · WT348", embed.title)


class PutToBedShareHandoffTests(_DBTestCase):
    """`put-to-bed` is the formal transition: closes the active window,
    clears the Build/Publish cards, posts the Share card, and auto-fires
    `promotion-prep`. Without this end-to-end test, regressions in the
    handoff (e.g. forgetting to call share_card.post_or_update, or
    swapping the order so promotion-prep fires before the share card is
    visible) would slip through silently."""

    def _seed_filing_artifacts(self, n=458):
        # The on-disk files put-to-bed reads to populate the issues +
        # issue_links rows. Patch ISSUES_ROOT to our tempdir so the
        # writes don't reach into the real data/issues/ tree, then drop
        # the three local files put-to-bed expects.
        issues_dir = Path(self._tmpdir.name) / "data" / "issues" / str(n)
        issues_dir.mkdir(parents=True, exist_ok=True)
        (issues_dir / "metadata.json").write_text(json.dumps({
            "number": n,
            "subject": f"WT{n} — Test ship",
            "publish_date": "2026-05-23T12:00:00Z",
            "slug": str(n),
            "buttondown_id": "em_test",
            "absolute_url": f"https://buttondown.com/weekly-thing/archive/{n}/",
        }), encoding="utf-8")
        (issues_dir / "links.json").write_text(json.dumps({
            "notable_links": [], "briefly_links": [], "domains": [], "word_count": 0,
        }), encoding="utf-8")
        audio_path = Path(self._tmpdir.name) / "data" / "audio" / "manifest.json"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_text(json.dumps({str(n): {}}), encoding="utf-8")
        return issues_dir.parent, audio_path

    def test_put_to_bed_clears_cards_posts_share_and_fires_promotion_prep(self):
        n = 458
        _window(n)
        db.set_issue_phase(n, "publish")
        # Stamp pretend Build + Publish cards so we can assert they're cleared.
        db.set_issue_card(n, "build", message_id=11, channel_id=22)
        db.set_issue_card(n, "publish", message_id=33, channel_id=44)
        issues_root, audio_manifest = self._seed_filing_artifacts(n)
        ctx = _base.JobContext()
        # Patch the file-system constants put-to-bed reads from, and stub
        # the three handoff targets so we can assert their call shape.
        with patch.object(put_to_bed, "ISSUES_ROOT", issues_root), \
             patch.object(put_to_bed, "AUDIO_MANIFEST", audio_manifest), \
             patch.object(share_card, "post_or_update", new=AsyncMock(return_value=99)) as mock_share, \
             patch.object(promotion_prep, "run", new=AsyncMock(return_value=_base.JobResult(True, "ok"))) as mock_prep, \
             patch.object(ctx, "post", new=AsyncMock(return_value=True)):
            res = asyncio.run(put_to_bed.run(ctx))
        self.assertTrue(res.ok, res.message)
        # Window is closed.
        self.assertIsNone(db.get_active_issue_window())
        # Both phase cards cleared from the issue_cards table.
        self.assertIsNone(db.get_issue_card(n, "build"))
        self.assertIsNone(db.get_issue_card(n, "publish"))
        # Share card posted exactly once; promotion-prep auto-fired.
        mock_share.assert_awaited_once()
        mock_prep.assert_awaited_once()
        # Share is the target — `put-to-bed` is the last-published-issue
        # gate, and the issues table picks up the WT458 row file_issue wrote.
        latest = db.get_latest_issue()
        self.assertIsNotNone(latest)
        self.assertEqual(int(latest["number"]), n)

    def test_share_handoff_failure_does_not_undo_the_filing(self):
        # If share_card.post_or_update raises (Discord hiccup, channel
        # permissions slip), the issue is still filed and the window is
        # still closed — the share-handoff is best-effort and logged.
        n = 458
        _window(n)
        db.set_issue_phase(n, "publish")
        issues_root, audio_manifest = self._seed_filing_artifacts(n)
        ctx = _base.JobContext()
        with patch.object(put_to_bed, "ISSUES_ROOT", issues_root), \
             patch.object(put_to_bed, "AUDIO_MANIFEST", audio_manifest), \
             patch.object(share_card, "post_or_update", new=AsyncMock(side_effect=RuntimeError("Discord down"))), \
             patch.object(promotion_prep, "run", new=AsyncMock()), \
             patch.object(ctx, "post", new=AsyncMock(return_value=True)):
            res = asyncio.run(put_to_bed.run(ctx))
        self.assertTrue(res.ok, res.message)
        self.assertIsNone(db.get_active_issue_window())
        # Issue is filed even though the share handoff blew up.
        latest = db.get_latest_issue()
        self.assertIsNotNone(latest)
        self.assertEqual(int(latest["number"]), n)


class ViewTests(unittest.TestCase):
    def test_build_view_buttons_and_mark_built_gate(self):
        ids = {getattr(c, "custom_id", None) for c in build_card_view.BuildCardView().children}
        # Echoes button moved off the Build card — compose-echoes auto-fires
        # at mark-built now (with /eddy edit echoes for manual refinement).
        self.assertIn(build_card.BTN_REORDER, ids)
        self.assertIn(build_card.BTN_MARK_BUILT, ids)
        # Mark built disabled until build_ready.
        v = build_card_view.build_view({"build_ready": False})
        disabled = {getattr(c, "custom_id", None): c.disabled for c in v.children}
        self.assertTrue(disabled[build_card.BTN_MARK_BUILT])
        v = build_card_view.build_view({"build_ready": True})
        disabled = {getattr(c, "custom_id", None): c.disabled for c in v.children}
        self.assertFalse(disabled[build_card.BTN_MARK_BUILT])

    def test_publish_view_ship_buttons_gated(self):
        state = {"gates": {publish_card.BTN_EMAIL: True, publish_card.BTN_WEBSITE: False,
                           publish_card.BTN_PODCAST: True, publish_card.BTN_ALL: False}}
        v = publish_card_view.build_view(state)
        disabled = {getattr(c, "custom_id", None): c.disabled for c in v.children}
        self.assertFalse(disabled[publish_card.BTN_EMAIL])
        self.assertTrue(disabled[publish_card.BTN_WEBSITE])
        self.assertFalse(disabled[publish_card.BTN_PODCAST])
        # Subject/CTA (envelope) buttons are never gated.
        self.assertFalse(disabled[publish_card.BTN_META])

    def test_all_views_persistent(self):
        self.assertIsNone(build_card_view.BuildCardView().timeout)
        self.assertIsNone(publish_card_view.PublishCardView().timeout)
        self.assertIsNone(share_card_view.ShareCardView().timeout)


class EchoesRenameTests(unittest.TestCase):
    def test_renderer_emits_echoes_heading(self):
        body = renderers.render_archive_body(
            atoms={"intro": "Hi.", "haiku": "a\nb\nc"},
            sections={"notable": "### [A](http://a)\n\nx"},
            features=[],
            echoes="Thingy connects this to [WT287](https://weekly.thingelstad.com/archive/287/).",
        )
        self.assertIn("## Echoes", body)
        self.assertNotIn("## The Closer", body)


if __name__ == "__main__":
    unittest.main()
