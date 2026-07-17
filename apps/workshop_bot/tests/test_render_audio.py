"""Tests for the render-audio workshop job — TTS + bumpers + S3 upload
called from inside the ship sequence.

Workshop_bot's render_audio.run() wraps pipeline/audio/audio.build_issue so
the underlying TTS / chunking / S3 upload / manifest update logic stays in
one place. Tests stub the audio pipeline entirely so no real TTS or AWS
calls happen, and verify:

- refuses if no active issue window
- refuses if data/issues/{N}/transcript/ is empty
- happy path: calls build_issue once, writes the updated manifest back,
  returns a JobResult with audio_url / duration / byte_size from the entry
- exception in build_issue surfaces as a failed JobResult (doesn't crash
  the ship)
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, render_audio  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
)
from apps.workshop_bot.tests._fixtures import (
    FakeBotChannel as _FakeBotChannel,
)
from apps.workshop_bot.tools import db  # noqa: E402


class ProgressHookTests(unittest.TestCase):
    """The §6 fix: the live progress card stuck on "starting…" because the
    print-intercept missed the synthesize module. These cover the plumbing —
    module resolution, line classification, and the print hook — without the
    real TTS pipeline."""

    def test_classify_per_block_line(self):
        out = render_audio._classify_print("Issue #349: synthesizing block 3/12 (512 chars)")
        self.assertEqual(out, "🎙️ block 3/12 (512 chars)")

    def test_classify_ignores_unrelated_line(self):
        self.assertIsNone(render_audio._classify_print("some unrelated log line"))

    def test_synthesize_mod_resolves_via_function_module(self):
        # Simulate `from synthesize import synthesize_blocks_to_mp3`: the fn's
        # __module__ points at a module registered under a NON-"synthesize" key
        # (the case that broke the old sys.modules['synthesize'] lookup).
        import types
        syn = types.ModuleType("pipeline.audio.synthesize")
        def _blocks():  # noqa: ANN202
            pass
        _blocks.__module__ = "pipeline.audio.synthesize"
        syn.synthesize_blocks_to_mp3 = _blocks
        audio_mod = types.ModuleType("audio")
        audio_mod.synthesize_blocks_to_mp3 = _blocks  # imported into audio's ns
        sys.modules["pipeline.audio.synthesize"] = syn
        try:
            self.assertIs(render_audio._synthesize_mod(audio_mod), syn)
        finally:
            sys.modules.pop("pipeline.audio.synthesize", None)

    def test_print_intercept_forwards_classified_lines(self):
        import types
        syn = types.ModuleType("synth_under_test")
        events: list[str] = []
        with render_audio._print_intercept(syn, progress_cb=events.append):
            # A call resolved via the module's patched `print`.
            syn.print("Issue #349: synthesizing block 1/4 (100 chars)")
            syn.print("noise that should not classify")
        self.assertEqual(events, ["🎙️ block 1/4 (100 chars)"])
        # print restored on exit (module had no own `print` before).
        self.assertNotIn("print", vars(syn))


class RenderAudioTests(_DBTestCase):
    def setUp(self):
        super().setUp()
        # Redirect render_audio's filesystem lookups to a tempdir so tests
        # don't read/write the real repo's data/issues/ or apps/site/archive/.
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._patches_files = [
            patch.object(render_audio, "TRANSCRIPT_DIR_TPL", tmp / "data" / "issues"),
            patch.object(render_audio, "AUDIO_MANIFEST", tmp / "data" / "audio" / "manifest.json"),
            patch.object(render_audio, "REPO", tmp),
        ]
        for p in self._patches_files:
            p.start()

    def tearDown(self):
        for p in self._patches_files:
            p.stop()
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        self._tmp.cleanup()
        super().tearDown()

    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod

        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )

    def _ctx(self):
        fc = _FakeBotChannel(persona="eddy")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def _seed_transcripts(self, n=458):
        d = render_audio.TRANSCRIPT_DIR_TPL / str(n) / "transcript"
        d.mkdir(parents=True, exist_ok=True)
        (d / "000-preamble.txt").write_text("The Weekly Thing for May 16, 2026.\n", encoding="utf-8")
        (d / "001-intro.txt").write_text("Welcome to the issue.\n", encoding="utf-8")

    def _fake_audio_pipeline(self, *, audio_url="https://x/y.mp3",
                             duration=360, byte_size=4_500_000, changed=True):
        """Build (audio_mod, bumpers_mod, manifest_mod) MagicMocks that the
        job's _import_audio_pipeline hook would have produced. build_issue
        side-effects the manifest dict in place with the new entry."""
        audio_mod = MagicMock()
        bumpers_mod = MagicMock()
        manifest_mod = MagicMock()

        manifest_data: dict = {}
        write_calls: list[dict] = []

        def fake_read_manifest():
            return manifest_data  # live dict — caller mutates it

        def fake_write_manifest(data):
            # Snapshot what was passed (don't mutate manifest_data — it shares
            # identity with `data` since build_issue mutated the live dict).
            write_calls.append(dict(data))

        def fake_build_issue(issue, manifest, *, dry_run, force, reassemble_only):
            manifest[issue] = {
                "audio_url": audio_url,
                "audio_duration_seconds": duration,
                "audio_byte_size": byte_size,
            }
            return changed

        manifest_mod.read_manifest = fake_read_manifest
        manifest_mod.write_manifest = fake_write_manifest
        manifest_mod._write_calls = write_calls  # expose for assertions
        audio_mod.build_issue = fake_build_issue
        return audio_mod, bumpers_mod, manifest_mod

    # ---------- failure-path tests ----------

    def test_refuses_if_no_active_window(self):
        ctx, _fc = self._ctx()
        result = asyncio.run(render_audio.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)

    def test_refuses_if_transcripts_missing(self):
        self._window()
        ctx, fc = self._ctx()
        result = asyncio.run(render_audio.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("transcript", result.message.lower())
        fc.channel.send.assert_awaited()  # missing list posted

    def test_build_issue_exception_surfaces(self):
        self._window()
        self._seed_transcripts()
        ctx, _fc = self._ctx()

        audio_mod, bumpers_mod, manifest_mod = self._fake_audio_pipeline()
        audio_mod.build_issue = MagicMock(side_effect=RuntimeError("TTS API down"))

        with patch.object(
            render_audio, "_import_audio_pipeline",
            return_value=(audio_mod, bumpers_mod, manifest_mod),
        ), patch.object(render_audio, "_materialize_apps_site_archive"):
            result = asyncio.run(render_audio.run(ctx))

        self.assertFalse(result.ok)
        self.assertIn("TTS API down", result.message)

    # ---------- success-path tests ----------

    def test_happy_path_returns_audio_metadata(self):
        self._window()
        self._seed_transcripts()
        ctx, _fc = self._ctx()

        audio_mod, bumpers_mod, manifest_mod = self._fake_audio_pipeline(
            audio_url="https://files.thingelstad.com/weekly-thing/458/weekly-thing-458.mp3",
            duration=420, byte_size=5_200_000,
        )

        with patch.object(
            render_audio, "_import_audio_pipeline",
            return_value=(audio_mod, bumpers_mod, manifest_mod),
        ), patch.object(render_audio, "_materialize_apps_site_archive"):
            result = asyncio.run(render_audio.run(ctx))

        self.assertTrue(result.ok, result.message)
        self.assertEqual(
            result.data["audio_url"],
            "https://files.thingelstad.com/weekly-thing/458/weekly-thing-458.mp3",
        )
        self.assertEqual(result.data["duration_seconds"], 420)
        self.assertEqual(result.data["byte_size"], 5_200_000)
        self.assertTrue(result.data["changed"])
        # Bumpers ensured before build_issue ran. ensure_bumpers takes
        # the manifest as its first positional arg (mutates it in place
        # to stamp the bumper hash + voice into _bumpers).
        bumpers_mod.ensure_bumpers.assert_called_once()
        passed_manifest = bumpers_mod.ensure_bumpers.call_args.args[0]
        self.assertIsInstance(passed_manifest, dict)

    def test_idempotent_skip_reports_up_to_date(self):
        self._window()
        self._seed_transcripts()
        ctx, _fc = self._ctx()

        audio_mod, bumpers_mod, manifest_mod = self._fake_audio_pipeline(changed=False)
        with patch.object(
            render_audio, "_import_audio_pipeline",
            return_value=(audio_mod, bumpers_mod, manifest_mod),
        ), patch.object(render_audio, "_materialize_apps_site_archive"):
            result = asyncio.run(render_audio.run(ctx))

        self.assertTrue(result.ok, result.message)
        self.assertFalse(result.data["changed"])


if __name__ == "__main__":
    unittest.main()
