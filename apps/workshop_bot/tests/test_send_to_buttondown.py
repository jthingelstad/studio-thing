"""Tests for the ``send-to-buttondown`` workshop_bot job — the ship sequence.

The Phase-5 send_to_buttondown.run() runs the full ship:
  compose-archive → compose-transcript → Buttondown POST/PATCH →
  re-run compose-archive (so absolute_url lands in the front matter) →
  github_repo.put_tree (atomic website commit) → success card.

Most tests here mock compose-* and github_repo to focus on send_to_buttondown's
own logic (Buttondown idempotency, error surfacing, success-card shape,
job-lock contention). One end-to-end test exercises the full sequence with
all the prerequisites seeded.
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

from apps.workshop_bot.jobs import _base, compose_archive, compose_transcript, send_to_buttondown  # noqa: E402
from apps.workshop_bot.tools import db, github_repo  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
    filled_final as _filled_final,
)


class _FakeButtondownErr(RuntimeError):
    """Stand-in for ``ButtondownPublishError`` in the fake pipeline module."""


def _fake_pipeline(result=None, *, raise_with=None):
    """Build a stub pipeline module with the two attributes the job
    references: ``buttondown_publish_idempotent`` and ``ButtondownPublishError``."""
    mod = MagicMock()
    mod.ButtondownPublishError = _FakeButtondownErr
    if raise_with is not None:
        mod.buttondown_publish_idempotent = MagicMock(side_effect=_FakeButtondownErr(raise_with))
    else:
        mod.buttondown_publish_idempotent = MagicMock(return_value=result or {})
    return mod


def _ok_result(**kwargs):
    return _base.JobResult(True, kwargs.get("message", "ok"), data=kwargs.get("data", {}))


def _no_op_compose():
    """Patcher tuple: (compose_archive.run, compose_transcript.run) both
    succeed with an empty result. Tests that don't care about the compose
    steps use this to avoid seeding their full prereq surface."""
    return (
        patch.object(compose_archive, "run", new=AsyncMock(return_value=_ok_result())),
        patch.object(compose_transcript, "run", new=AsyncMock(return_value=_ok_result())),
    )


def _no_op_github(commit_sha="deadbeef" + "0" * 32):
    """Patcher for github_repo.put_tree that returns a fake commit sha."""
    return patch.object(github_repo, "put_tree", new=MagicMock(return_value=commit_sha))


class SendToButtondownTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        os.environ.pop("GITHUB_PAT_TOKEN", None)
        os.environ.pop("GITHUB_REPO_NWO", None)
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
        os.environ["GITHUB_REPO_NWO"] = "test-owner/test-repo"
        return _base.JobContext(deps=fc.deps()), fc

    def _seed_min_workspace(self, n=458):
        """Minimum so the ship can attempt Buttondown — buttondown.md + a
        small archive.md + metadata.json so _collect_ship_files works."""
        self.ws.write_issue_file(n, "buttondown.md", "## Notable\n\nbody")
        self.ws.write_issue_file(n, "archive.md", "---\nnumber: 458\n---\n\nbody\n")
        self.ws.write_issue_file(n, "metadata.json", '{"number": 458, "subject": "WT458"}')

    # ---------- failure-path tests ----------

    def test_refuses_if_no_active_window(self):
        ctx, _fc = self._ctx()
        result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)

    def test_refuses_if_buttondown_md_missing(self):
        """compose-archive succeeds (mocked), but buttondown.md isn't in the
        workspace — the ship blocks before reaching Buttondown's API."""
        self._window()
        # archive.md + metadata.json present so compose-archive (mocked) doesn't
        # complain; buttondown.md deliberately absent.
        self.ws.write_issue_file(458, "archive.md", "---\nnumber: 458\n---\n\nbody\n")
        ca, ct = _no_op_compose()
        ctx, fc = self._ctx()
        with ca, ct:
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no `buttondown.md`", result.message)
        fc.channel.send.assert_awaited()

    def test_compose_archive_failure_blocks_ship(self):
        """If compose-archive can't produce archive.md (missing prereqs), the
        ship never touches Buttondown."""
        self._window()
        # Don't seed anything — compose-archive will refuse with its real
        # missing-list. Use the unpatched compose_archive.run.
        ctx, _fc = self._ctx()
        result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("compose-archive failed", result.message)

    def test_pipeline_error_surfaces_to_channel(self):
        self._window()
        self._seed_min_workspace()
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(raise_with="Buttondown POST failed (422): validation error")
        ca, ct = _no_op_compose()
        with ca, ct, patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("422", result.message)
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("422", sent)

    # ---------- success-path tests ----------

    def test_created_action_posts_success_card(self):
        self._window()
        self._seed_min_workspace()
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(result={
            "action": "created", "id": "new-uuid-001",
            "subject": "Weekly Thing 458 / A, B, C", "slug": "458",
            "body_chars": 16, "description_chars": 1,
            "absolute_url": "https://buttondown.com/weekly-thing/archive/458/",
        })
        os.environ["GITHUB_PAT_TOKEN"] = "github_pat_test"
        ca, ct = _no_op_compose()
        with ca, ct, _no_op_github("abc123" + "0" * 34) as gh, \
             patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["action"], "created")
        self.assertEqual(result.data["buttondown_id"], "new-uuid-001")
        self.assertTrue(result.data["commit_sha"].startswith("abc123"))
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("Created Buttondown draft", sent)
        self.assertIn("https://buttondown.com/emails/new-uuid-001", sent)
        self.assertIn("Weekly Thing 458", sent)
        self.assertIn("website commit", sent)
        # github_repo.put_tree got the expected files.
        gh.assert_called_once()
        files_arg = gh.call_args.args[0]
        paths = {p for p, _ in files_arg}
        self.assertIn("data/issues/458/archive.md", paths)
        self.assertIn("data/issues/458/metadata.json", paths)

    def test_updated_action_says_updated(self):
        self._window()
        self._seed_min_workspace()
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(result={
            "action": "updated", "id": "existing-uuid",
            "subject": "Weekly Thing 458 / A, B, C", "slug": "458",
            "body_chars": 16, "description_chars": 1,
            "absolute_url": "https://buttondown.com/weekly-thing/archive/458/",
        })
        os.environ["GITHUB_PAT_TOKEN"] = "github_pat_test"
        ca, ct = _no_op_compose()
        with ca, ct, _no_op_github(), \
             patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["action"], "updated")
        sent = fc.channel.send.await_args_list[0].args[0]
        self.assertIn("Updated Buttondown draft", sent)
        self.assertIn("https://buttondown.com/emails/existing-uuid", sent)

    def test_github_commit_failure_does_not_fail_ship(self):
        """The email is the user-visible artifact; a GitHub commit hiccup
        shouldn't fail the ship — it surfaces a warning and the result stays ok."""
        self._window()
        self._seed_min_workspace()
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(result={
            "action": "created", "id": "new-uuid",
            "subject": "WT458", "slug": "458",
            "body_chars": 16, "description_chars": 1,
            "absolute_url": "https://buttondown.com/weekly-thing/archive/458/",
        })
        os.environ["GITHUB_PAT_TOKEN"] = "github_pat_test"
        ca, ct = _no_op_compose()
        with ca, ct, \
             patch.object(github_repo, "put_tree", side_effect=RuntimeError("github 500")), \
             patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["commit_sha"], "")
        warnings = [
            c.args[0] for c in fc.channel.send.await_args_list
            if "GitHub commit" in c.args[0]
        ]
        self.assertEqual(len(warnings), 1)
        self.assertIn("github 500", warnings[0])

    def test_missing_github_token_warns_but_does_not_fail_ship(self):
        self._window()
        self._seed_min_workspace()
        ctx, fc = self._ctx()
        fake_pipeline = _fake_pipeline(result={
            "action": "created", "id": "new-uuid",
            "subject": "WT458", "slug": "458",
            "body_chars": 16, "description_chars": 1,
            "absolute_url": "https://buttondown.com/weekly-thing/archive/458/",
        })
        # Deliberately don't set GITHUB_PAT_TOKEN.
        ca, ct = _no_op_compose()
        with ca, ct, \
             patch.object(github_repo, "put_tree", side_effect=github_repo.MissingTokenError("no token")), \
             patch.object(send_to_buttondown, "_import_pipeline_content", return_value=fake_pipeline):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["commit_sha"], "")
        warnings = [
            c.args[0] for c in fc.channel.send.await_args_list
            if "GITHUB_PAT_TOKEN" in c.args[0]
        ]
        self.assertEqual(len(warnings), 1)

    def test_concurrent_run_blocked_by_job_lock(self):
        self._window()
        self._seed_min_workspace()
        ctx, _fc = self._ctx()
        with _base.job_lock([f"{458}/metadata.json"], send_to_buttondown.NAME):
            result = asyncio.run(send_to_buttondown.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)


if __name__ == "__main__":
    unittest.main()
