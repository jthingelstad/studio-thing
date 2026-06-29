"""Tests for Scout's machine-readable production feed."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import production_state, scout_production_feed  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()


def _task_by_slug(production: dict, slug: str) -> dict:
    suffix = f":{slug}"
    for task in production["tasks"]:
        if task["task_key"].endswith(suffix):
            return task
    raise AssertionError(f"missing task ending {suffix}")


class ScoutProductionFeedTests(_DBCase):
    def test_feed_returns_no_productions_without_active_work(self):
        feed = scout_production_feed.build_feed(
            generated_at=datetime(2026, 6, 18, 12, tzinfo=ZoneInfo("America/Chicago"))
        )
        self.assertEqual(feed["schema_version"], 1)
        self.assertEqual(feed["productions"], [])

    def test_newsletter_build_maps_missing_content_review_and_gate(self):
        db.set_issue_window(
            issue_number=350,
            pub_date="2026-06-20",
            end_date="2026-06-19",
            start_date="2026-06-12",
            day_count=7,
            set_by="test",
        )
        state = {
            "issue_number": 350,
            "phase": "build",
            "pub_date": "2026-06-20",
            "sections": {
                "notable": {"present": False, "placeholder": False},
                "journal": {"present": True, "placeholder": True},
                "brief": {"present": False, "placeholder": False},
            },
            "intro_present": False,
            "cover_present": False,
            "build_ready": False,
            "open_comments": 2,
        }
        with patch(
            "apps.workshop_bot.jobs.scout_production_feed.production_state.build_state",
            return_value=state,
        ):
            production = scout_production_feed.newsletter_productions()[0]

        self.assertEqual(production["production_type"], "newsletter")
        self.assertEqual(production["production_id"], "WT350")
        self.assertEqual(production["phase"], "build")
        self.assertEqual(production["due_at"], "2026-06-20T07:00:00-05:00")

        expected_suffixes = {
            "intro",
            "cover",
            "section-notable",
            "section-journal",
            "section-brief",
            "review-notes",
            "mark-built",
        }
        self.assertEqual(
            {task["task_key"].split(":")[-1] for task in production["tasks"]},
            expected_suffixes,
        )
        self.assertEqual(_task_by_slug(production, "intro")["title"], "Write WT350 intro")
        self.assertEqual(_task_by_slug(production, "review-notes")["status"], "open")
        self.assertEqual(_task_by_slug(production, "mark-built")["status"], "blocked")

    def test_newsletter_build_ready_marks_built_ready(self):
        db.set_issue_window(
            issue_number=351,
            pub_date="2026-06-27",
            end_date="2026-06-26",
            start_date="2026-06-19",
            day_count=7,
            set_by="test",
        )
        state = {
            "issue_number": 351,
            "phase": "build",
            "pub_date": "2026-06-27",
            "sections": {
                "notable": {"present": True, "placeholder": False},
                "journal": {"present": True, "placeholder": False},
                "brief": {"present": True, "placeholder": False},
            },
            "intro_present": True,
            "cover_present": True,
            "build_ready": True,
            "open_comments": 0,
        }
        with patch(
            "apps.workshop_bot.jobs.scout_production_feed.production_state.build_state",
            return_value=state,
        ):
            production = scout_production_feed.newsletter_productions()[0]
        self.assertEqual(len(production["tasks"]), 1)
        self.assertEqual(_task_by_slug(production, "mark-built")["status"], "ready")

    def test_newsletter_publish_maps_envelope_channels_and_put_to_bed(self):
        db.set_issue_window(
            issue_number=352,
            pub_date="2026-07-04",
            end_date="2026-07-03",
            start_date="2026-06-26",
            day_count=7,
            set_by="test",
        )
        db.set_issue_phase(352, "publish")
        state = {
            "issue_number": 352,
            "phase": "publish",
            "pub_date": "2026-07-04",
            "subject": "",
            "description": "",
            "haiku_present": False,
            "cta_files": [],
            "recompose_needed": True,
            "thesis_failed": True,
            "echoes_failed": False,
            "email_shipped": False,
            "audio_shipped": False,
            "gates": {
                production_state.BTN_EMAIL: False,
                production_state.BTN_WEBSITE: False,
                production_state.BTN_PODCAST: True,
            },
        }
        with patch(
            "apps.workshop_bot.jobs.scout_production_feed.production_state.publish_state",
            return_value=state,
        ):
            production = scout_production_feed.newsletter_productions()[0]

        self.assertEqual(production["phase"], "publish")
        self.assertEqual(_task_by_slug(production, "metadata")["source_command"], "/eddy issue subject")
        self.assertEqual(_task_by_slug(production, "publish-buttondown")["status"], "blocked")
        self.assertEqual(_task_by_slug(production, "publish-audio")["status"], "ready")
        self.assertEqual(_task_by_slug(production, "publish-website")["status"], "blocked")
        self.assertEqual(_task_by_slug(production, "put-to-bed")["status"], "blocked")

    def test_feed_accepts_future_production_mappers(self):
        def blog_mapper():
            return [{
                "production_type": "blog_post",
                "production_id": "post-1",
                "title": "A future blog post",
                "phase": "draft",
                "due_at": None,
                "source": "test",
                "status": "open",
                "tasks": [],
            }]

        feed = scout_production_feed.build_feed(mappers={"blog_post": blog_mapper})
        self.assertEqual(feed["productions"][0]["production_type"], "blog_post")
        self.assertEqual(feed["productions"][0]["production_id"], "post-1")


if __name__ == "__main__":
    unittest.main()
