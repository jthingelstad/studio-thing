"""Tests for ``compose-envelope`` — the batched Publish-phase composer.

One LLM call over the assembled draft returns a structured envelope (5
subject options + 1 description + 3 haiku options); the per-slot pickers
then **replay** those options without re-calling the model, so the happy
path is exactly one ``bot.core`` call. Writes ``metadata.json`` +
``haiku.md`` — the same artifacts ``compose-meta`` / ``compose-haiku``
write. Shares the in-memory S3 + temp-DB fixtures with the other compose
tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, compose_envelope  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
)
from apps.workshop_bot.tests._fixtures import (
    FakeBotChannel as _FakeBotChannel,
)
from apps.workshop_bot.tools import content_store, db  # noqa: E402
from apps.workshop_bot.tools.discord import interaction  # noqa: E402

_ENVELOPE_REPLY = json.dumps({
    "subjects": [
        "WT458 — Alpha", "WT458 — Bravo", "WT458 — Charlie",
        "WT458 — Delta", "WT458 — Echo",
    ],
    "description": "Alpha, Bravo, Charlie, Delta, Echo.",
    "haikus": ["one\ntwo\nthree", "a\nb\nc", "x\ny\nz"],
})


def _seed_issue_body(n: int = 458) -> None:
    from apps.workshop_bot.tools import issue_items
    issue_items.upsert_item(issue_number=n, section="notable", source="pinboard",
                            source_id="seed1", url="https://ex/a", title="Seed item",
                            body_md="Seed blurb about capital and code.")


class ComposeEnvelopeTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def _ctx(self, reply=_ENVELOPE_REPLY):
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_writes_metadata_and_haiku_from_one_call(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        # Pick subject #1 (Alpha) then haiku #2 ("a\nb\nc").
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0, 1])):
            result = asyncio.run(compose_envelope.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Exactly ONE model call — the pickers replay, they don't re-prompt.
        self.assertEqual(fc.bot.core.await_count, 1)
        meta = json.loads(content_store.read_issue(458, "metadata.json"))
        self.assertEqual(meta["number"], 458)
        self.assertEqual(meta["subject"], "WT458 — Alpha")
        self.assertEqual(meta["description"], "Alpha, Bravo, Charlie, Delta, Echo.")
        self.assertEqual(meta["slug"], "458")
        self.assertTrue(meta["image"].endswith("/458/cover.jpg"))
        self.assertTrue(meta["publish_date"].startswith("2026-05-16"))
        self.assertEqual(content_store.read_issue(458, "haiku.md").strip(), "a\nb\nc")

    def test_forces_sonnet_model(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0, 0])):
            asyncio.run(compose_envelope.run(ctx))
        self.assertEqual(fc.bot.core.await_args.kwargs["model"], "sonnet")

    def test_refresh_on_subject_regenerates_with_one_extra_call(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        # Subject: refresh (→ one extra batched call) then pick #1; haiku: pick #1.
        with patch.object(interaction, "await_choice",
                          AsyncMock(side_effect=["refresh", 0, 0])):
            result = asyncio.run(compose_envelope.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Initial batched call + one regenerate on the subject refresh.
        self.assertEqual(fc.bot.core.await_count, 2)
        self.assertEqual(
            json.loads(content_store.read_issue(458, "metadata.json"))["subject"],
            "WT458 — Alpha",
        )

    def test_no_subject_pick_writes_nothing(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_envelope.run(ctx))
        self.assertFalse(result.ok)
        self.assertIsNone(content_store.read_issue(458, "metadata.json"))
        self.assertIsNone(content_store.read_issue(458, "haiku.md"))

    def test_no_haiku_pick_still_writes_metadata(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        # Subject picked, haiku times out.
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0, None])):
            result = asyncio.run(compose_envelope.run(ctx))
        self.assertFalse(result.ok)
        self.assertTrue(result.data["metadata_written"])
        self.assertFalse(result.data["haiku_written"])
        self.assertEqual(
            json.loads(content_store.read_issue(458, "metadata.json"))["subject"],
            "WT458 — Alpha",
        )
        self.assertIsNone(content_store.read_issue(458, "haiku.md"))

    def test_unparseable_reply_exhausts_retries(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx(reply="sorry, no JSON here")
        result = asyncio.run(compose_envelope.run(ctx))
        self.assertFalse(result.ok)
        # Retried MAX_REFRESH_ROUNDS times, never reached a picker.
        from apps.workshop_bot.jobs import _llm_job
        self.assertEqual(fc.bot.core.await_count, _llm_job.MAX_REFRESH_ROUNDS)
        self.assertIsNone(content_store.read_issue(458, "metadata.json"))
        self.assertIsNone(content_store.read_issue(458, "haiku.md"))

    def test_preserves_buttondown_id_on_rerun(self):
        self._window()
        _seed_issue_body(458)
        content_store.write_issue(458, "metadata.json", json.dumps({
            "number": 458, "subject": "old", "description": "old",
            "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
            "slug": "458", "publish_date": "2026-05-16T12:00:00Z",
            "buttondown_id": "em_existing_123",
        }))
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0, 0])):
            result = asyncio.run(compose_envelope.run(ctx))
        self.assertTrue(result.ok, result.message)
        meta = json.loads(content_store.read_issue(458, "metadata.json"))
        self.assertEqual(meta["subject"], "WT458 — Alpha")
        self.assertEqual(meta["buttondown_id"], "em_existing_123")

    def test_no_active_window(self):
        ctx, fc = self._ctx()
        result = asyncio.run(compose_envelope.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)
        self.assertEqual(fc.bot.core.await_count, 0)

    def test_no_draft_body(self):
        self._window()  # window but no content rows / intro
        ctx, fc = self._ctx()
        result = asyncio.run(compose_envelope.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no draft body", result.message)
        self.assertEqual(fc.bot.core.await_count, 0)

    def test_concurrent_run_blocked_by_lock(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        with _base.job_lock(["458/haiku.md"], compose_envelope.NAME):
            result = asyncio.run(compose_envelope.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        fc.bot.core.assert_not_awaited()


if __name__ == "__main__":
    import unittest
    unittest.main()
