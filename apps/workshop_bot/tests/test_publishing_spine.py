"""Tests for the publishing spine — phase state + the headless transitions.

The Discord phase cards (Build / Publish / Share) were retired; production
status is the web scoreboard now. The status that used to live on the cards is
in `jobs/production_state.py` (`build_state` / `publish_state` + the gate keys),
and the transitions are in `jobs/production_ops.py` (`mark_built` / `reopen` /
`recompose`). See docs/publishing-process.md for the model.
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import (  # noqa: E402
    _base,
    compose_cta,
    compose_echoes,
    compose_thesis,
    production_ops,
    production_state,
    promotion_prep,
    put_to_bed,
)
from apps.workshop_bot.tools import db, renderers  # noqa: E402
from apps.workshop_bot.tests._fixtures import DBTestCase as _DBTestCase  # noqa: E402

_OK = _base.JobResult(True, "ok")


def _window(n=458, pub="2026-05-23"):
    from apps.workshop_bot.tools.content import issue as issue_mod
    w = issue_mod.compute_window(pub, 7)
    db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                        start_date=w["start_date"], day_count=w["day_count"], set_by="test")


def _patch_composes():
    """Patch the three compose jobs (lazily imported inside production_ops) so
    mark_built's auto-fires don't hit Anthropic."""
    return (
        patch.object(compose_thesis, "run", new=AsyncMock(return_value=_OK)),
        patch.object(compose_echoes, "run", new=AsyncMock(return_value=_OK)),
        patch.object(compose_cta, "run", new=AsyncMock(return_value=_OK)),
    )


class PhaseModelTests(_DBTestCase):
    def test_start_seeds_build_phase(self):
        _window(458)
        self.assertEqual(db.get_active_issue_window()["phase"], "build")

    def test_set_phase(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")


class BuildStateTests(_DBTestCase):
    def _seed_full_content(self, n=458):
        # The DB is the draft: sections are issue_items rows, authored atoms
        # live in the content store; cover.jpg stays an S3 binary.
        from apps.workshop_bot.tools import issue_items
        for section, source, sid in (("notable", "pinboard", "n1"),
                                     ("brief", "pinboard", "b1"),
                                     ("journal", "microblog", "j1")):
            issue_items.upsert_item(issue_number=n, section=section,
                                    source=source, source_id=sid, body_md="x")
        self.ws.write_issue_file(n, "intro.md", "Opening.")
        self.ws.write_issue_file(n, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(n, "cover.jpg", "binary")

    def test_build_ready_when_content_present(self):
        _window(458)
        self._seed_full_content()
        st = production_state.build_state(458)
        self.assertTrue(st["build_ready"])
        self.assertTrue(st["intro_present"])
        self.assertTrue(st["cover_present"])

    def test_build_not_ready_without_content(self):
        _window(459, pub="2026-05-30")
        st = production_state.build_state(459)
        self.assertFalse(st["build_ready"])

    def test_mark_built_refuses_when_not_ready(self):
        _window(459, pub="2026-05-30")
        res = asyncio.run(production_ops.mark_built(_base.JobContext()))
        self.assertFalse(res.ok)
        self.assertIn("isn't built", res.message.lower())
        self.assertEqual(db.get_active_issue_window()["phase"], "build")

    def test_mark_built_flips_to_publish_and_fires_composes(self):
        _window(458)
        self._seed_full_content()
        pt, pe, pc = _patch_composes()
        with pt as m_thesis, pe as m_echoes, pc as m_cta:
            res = asyncio.run(production_ops.mark_built(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(res.data["phase"], "publish")
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")
        m_thesis.assert_awaited_once()
        m_echoes.assert_awaited_once()
        m_cta.assert_awaited_once()

    def test_mark_built_recovers_when_a_compose_raises(self):
        # If a compose auto-fire blows up, the phase still flips to Publish and
        # the ack is success — the logged exception is the recovery signal.
        _window(458)
        self._seed_full_content()
        with patch.object(compose_thesis, "run", new=AsyncMock(return_value=_OK)), \
             patch.object(compose_echoes, "run", new=AsyncMock(return_value=_OK)), \
             patch.object(compose_cta, "run", new=AsyncMock(side_effect=RuntimeError("LLM hiccup"))):
            res = asyncio.run(production_ops.mark_built(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(db.get_active_issue_window()["phase"], "publish")

    def test_reopen_flips_publish_back_to_build(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        res = asyncio.run(production_ops.reopen(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        self.assertEqual(db.get_active_issue_window()["phase"], "build")

    def test_reopen_no_op_when_no_active_window(self):
        res = asyncio.run(production_ops.reopen(_base.JobContext()))
        self.assertFalse(res.ok)


class PublishStateTests(_DBTestCase):
    def _seed_built(self, n=458, *, subject="", description="", buttondown_id=""):
        self.ws.write_issue_file(n, "intro.md", "x")
        self.ws.write_issue_file(n, "haiku.md", "a\nb\nc")
        self.ws.write_issue_file(n, "cover.jpg", "bin")
        meta = {"number": n, "slug": str(n)}
        if subject:
            meta["subject"] = subject
        if description:
            meta["description"] = description
        self.ws.write_issue_file(n, "metadata.json", json.dumps(meta))
        if buttondown_id:
            # Publish-stamped fields live on the issue window now.
            db.set_issue_publish_record(
                n, buttondown_id=buttondown_id,
                absolute_url="https://weekly.thingelstad.com/archive/%d/" % n,
            )

    def test_email_gate_needs_subject_and_description(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="WT458 — Test")  # no description
        st = production_state.publish_state(458)
        self.assertFalse(st["gates"][production_state.BTN_EMAIL])
        self.assertIn("description", st["email_missing"])
        # With both, email is ready.
        self._seed_built(subject="WT458 — Test", description="a, b, c")
        st = production_state.publish_state(458)
        self.assertTrue(st["gates"][production_state.BTN_EMAIL])

    def test_website_gate_opens_after_buttondown(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d", buttondown_id="em_x")
        st = production_state.publish_state(458)
        self.assertTrue(st["email_shipped"])
        self.assertTrue(st["gates"][production_state.BTN_WEBSITE])

    def test_recompose_gate_off_when_thesis_and_echoes_present(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        self.ws.write_issue_file(458, "thesis.md", "An issue about X.")
        self.ws.write_issue_file(458, "echoes.md", "Echoes prose.")
        st = production_state.publish_state(458)
        self.assertFalse(st["thesis_failed"])
        self.assertFalse(st["echoes_failed"])
        self.assertFalse(st["recompose_needed"])
        self.assertFalse(st["gates"][production_state.BTN_RECOMPOSE])

    def test_recompose_gate_on_when_thesis_failed_in_publish(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        self.ws.write_issue_file(458, "echoes.md", "Echoes prose.")  # thesis missing
        st = production_state.publish_state(458)
        self.assertTrue(st["thesis_failed"])
        self.assertFalse(st["echoes_failed"])
        self.assertTrue(st["recompose_needed"])
        self.assertTrue(st["gates"][production_state.BTN_RECOMPOSE])

    def test_recompose_gate_off_in_build_phase(self):
        # In build phase the composes haven't auto-fired yet, so their absence
        # isn't a failure — recompose stays off.
        _window(458)
        self._seed_built(subject="", description="")
        st = production_state.publish_state(458)
        self.assertFalse(st["recompose_needed"])
        self.assertFalse(st["gates"][production_state.BTN_RECOMPOSE])

    def test_recompose_refires_missing_thesis(self):
        _window(458)
        db.set_issue_phase(458, "publish")
        self._seed_built(subject="S", description="d")
        self.ws.write_issue_file(458, "echoes.md", "Echoes prose.")  # thesis missing
        with patch.object(compose_thesis, "run", new=AsyncMock(return_value=_OK)) as m_thesis, \
             patch.object(compose_echoes, "run", new=AsyncMock(return_value=_OK)) as m_echoes:
            res = asyncio.run(production_ops.recompose(_base.JobContext()))
        self.assertTrue(res.ok, res.message)
        m_thesis.assert_awaited_once()
        m_echoes.assert_not_awaited()  # echoes already present


class PutToBedTests(_DBTestCase):
    """`put-to-bed` files the shipped issue and hands off to Marky by firing
    promotion-prep. (The card clear / Share-card post were retired.)"""

    def _seed_filing_artifacts(self, n=458):
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

    def test_put_to_bed_files_issue_and_fires_promotion_prep(self):
        n = 458
        _window(n)
        db.set_issue_phase(n, "publish")
        issues_root, audio_manifest = self._seed_filing_artifacts(n)
        ctx = _base.JobContext()
        with patch.object(put_to_bed, "ISSUES_ROOT", issues_root), \
             patch.object(put_to_bed, "AUDIO_MANIFEST", audio_manifest), \
             patch.object(promotion_prep, "run", new=AsyncMock(return_value=_OK)) as mock_prep, \
             patch.object(ctx, "post", new=AsyncMock(return_value=True)):
            res = asyncio.run(put_to_bed.run(ctx))
        self.assertTrue(res.ok, res.message)
        # Window is closed; issue filed; promotion-prep auto-fired.
        self.assertIsNone(db.get_active_issue_window())
        mock_prep.assert_awaited_once()
        latest = db.get_latest_issue()
        self.assertIsNotNone(latest)
        self.assertEqual(int(latest["number"]), n)

    def test_promotion_prep_failure_does_not_undo_the_filing(self):
        # The handoff is best-effort: if promotion-prep raises, the issue is
        # still filed and the window still closed.
        n = 458
        _window(n)
        db.set_issue_phase(n, "publish")
        issues_root, audio_manifest = self._seed_filing_artifacts(n)
        ctx = _base.JobContext()
        with patch.object(put_to_bed, "ISSUES_ROOT", issues_root), \
             patch.object(put_to_bed, "AUDIO_MANIFEST", audio_manifest), \
             patch.object(promotion_prep, "run", new=AsyncMock(side_effect=RuntimeError("down"))), \
             patch.object(ctx, "post", new=AsyncMock(return_value=True)):
            res = asyncio.run(put_to_bed.run(ctx))
        self.assertTrue(res.ok, res.message)
        self.assertIsNone(db.get_active_issue_window())
        latest = db.get_latest_issue()
        self.assertIsNotNone(latest)
        self.assertEqual(int(latest["number"]), n)


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
