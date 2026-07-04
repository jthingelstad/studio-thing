"""Tests for the issue-assembly flow: start_issue, sync-issue chaining,
issue_status, the DB-based section_status, and Eddy's on-demand review job
(``eddy-review``). The DB is the draft — the retired update-draft projection
(template fills, draft.md, no-op short-circuit, draft.html) has no tests
because it has no code. Shared fixtures come from ``tests/_fixtures.py``."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, eddy_review, issue_status, start_issue, sync_issue  # noqa: E402
from apps.workshop_bot.tools import content_store, db, issue_items  # noqa: E402
from apps.workshop_bot.tools.content import draft as draft_mod  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
)


def _no_sync(n, window):
    """Stand-in for issue_items_sync.sync_all — no HTTP in unit tests."""
    return {"pinboard": {"observed": 0}, "microblog": {"observed": 0}}


class StartIssueTests(_DBTestCase):
    def test_start_issue_records_window_and_chains_sync(self):
        ctx = _base.JobContext(trigger="manual")
        with patch.object(sync_issue.issue_items_sync, "sync_all", _no_sync):
            # 2026-05-16 is a Saturday.
            result = asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-16", day_count=7))
        self.assertTrue(result.ok, result.message)
        win = db.get_active_issue_window()
        self.assertIsNotNone(win)
        self.assertEqual(win["issue_number"], 458)
        self.assertEqual(win["pub_date"], "2026-05-16")
        self.assertEqual(win["end_date"], "2026-05-15")
        # No draft.md seeding, no Shortcuts pointer — the DB is the draft.
        self.assertNotIn((458, "draft.md"), self.ws.files)
        self.assertIn("sync-issue", result.message)

    def test_start_issue_rejects_non_saturday(self):
        ctx = _base.JobContext()
        result = asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-17", day_count=7))
        self.assertFalse(result.ok)
        self.assertIn("Sunday", result.message)

    def test_start_issue_rejects_bad_number(self):
        ctx = _base.JobContext()
        result = asyncio.run(start_issue.run(ctx, number=0, pub_date="2026-05-16", day_count=7))
        self.assertFalse(result.ok)

    def test_start_issue_replaces_active_window(self):
        ctx = _base.JobContext()
        with patch.object(sync_issue.issue_items_sync, "sync_all", _no_sync):
            asyncio.run(start_issue.run(ctx, number=458, pub_date="2026-05-16", day_count=7))
            asyncio.run(start_issue.run(ctx, number=459, pub_date="2026-05-23", day_count=7))
        win = db.get_active_issue_window()
        self.assertEqual(win["issue_number"], 459)

    def test_start_issue_schedules_mon_and_wed_currently_nudges(self):
        ctx = _base.JobContext()
        with patch.object(sync_issue.issue_items_sync, "sync_all", _no_sync):
            result = asyncio.run(start_issue.run(
                ctx, number=458, pub_date="2026-05-16", day_count=7, set_by="jamie"))
        self.assertTrue(result.ok, result.message)
        nudges = result.data.get("currently_nudges") or []
        rows = [db.get_follow_up(int(i)) for i in nudges]
        self.assertTrue(all(r is not None for r in rows))


class SyncIssueTests(_DBTestCase):
    def test_no_window_errors(self):
        result = asyncio.run(sync_issue.run(_base.JobContext()))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)

    def test_sync_reports_counts_and_source_errors(self):
        db.set_issue_window(issue_number=458, pub_date="2026-05-16",
                            end_date="2026-05-15", start_date="2026-05-08",
                            day_count=7, set_by="t")
        issue_items.upsert_item(issue_number=458, section="notable",
                                source="pinboard", source_id="p1", body_md="x")

        def _sync(n, window):
            return {"pinboard": {"observed": 3},
                    "microblog": {"error": "boom"}}

        with patch.object(sync_issue.issue_items_sync, "sync_all", _sync):
            result = asyncio.run(sync_issue.run(_base.JobContext()))
        self.assertFalse(result.ok)          # a source error marks the run
        self.assertIn("3 pinboard items", result.message)
        self.assertIn("microblog error: boom", result.message)
        self.assertIn("1 Notable", result.message)


class IssueStatusTests(_DBTestCase):
    def test_no_window(self):
        result = asyncio.run(issue_status.run(_base.JobContext()))
        self.assertFalse(result.ok)

    def test_reports_presence(self):
        db.set_issue_window(issue_number=458, pub_date="2026-05-16",
                            end_date="2026-05-15", start_date="2026-05-08",
                            day_count=7, set_by="t")
        content_store.write_issue(458, "intro.md", "Hello.")
        issue_items.upsert_item(issue_number=458, section="notable",
                                source="pinboard", source_id="p1", body_md="x")
        result = asyncio.run(issue_status.run(_base.JobContext()))
        self.assertTrue(result.ok, result.message)
        st = result.data["section_status"]
        self.assertTrue(st["intro_present"])
        self.assertEqual(st["sections"]["notable"]["item_count"], 1)


class DraftSectionStatusTests(_DBTestCase):
    """section_status computes from the DB — issue_items rows, the content
    store, currently_entries — plus the S3 listing for binaries."""

    def _window(self):
        db.set_issue_window(issue_number=458, pub_date="2026-05-16",
                            end_date="2026-05-15", start_date="2026-05-08",
                            day_count=7, set_by="t")

    def test_counts_come_from_rows(self):
        self._window()
        for i in range(3):
            issue_items.upsert_item(issue_number=458, section="notable",
                                    source="pinboard", source_id=f"n{i}", body_md="x")
        issue_items.upsert_item(issue_number=458, section="journal",
                                source="microblog", source_id="j1", body_md="x")
        st = draft_mod.section_status(458, list_objects=set())
        self.assertEqual(st["sections"]["notable"]["item_count"], 3)
        self.assertEqual(st["sections"]["journal"]["item_count"], 1)
        self.assertFalse(st["sections"]["brief"]["present"])

    def test_excluded_rows_do_not_count(self):
        self._window()
        a = issue_items.upsert_item(issue_number=458, section="notable",
                                    source="pinboard", source_id="n1", body_md="x")
        issue_items.set_excluded(a, True)
        st = draft_mod.section_status(458, list_objects=set())
        self.assertEqual(st["sections"]["notable"]["item_count"], 0)

    def test_assets_and_ship_ready(self):
        self._window()
        for name, body in (("haiku.md", "a / b / c"), ("metadata.json", "{}"),
                           ("intro.md", "Hello.")):
            content_store.write_issue(458, name, body)
        for section, sid in (("notable", "n1"), ("brief", "b1")):
            issue_items.upsert_item(issue_number=458, section=section,
                                    source="pinboard", source_id=sid, body_md="x")
        issue_items.upsert_item(issue_number=458, section="journal",
                                source="microblog", source_id="j1", body_md="x")
        st = draft_mod.section_status(458, list_objects={"cover.jpg"})
        self.assertTrue(st["ship_ready"], st["required_missing"])
        self.assertTrue(st["cover_present"])
        # Missing cover flips ship_ready.
        st2 = draft_mod.section_status(458, list_objects=set())
        self.assertIn("cover.jpg", st2["required_missing"])

    def test_currently_from_db(self):
        self._window()
        db.currently_add_type("Building")
        db.currently_set_entry(458, "Building", "the atom editor")
        st = draft_mod.section_status(458, list_objects=set())
        self.assertTrue(st["currently_present"])
        self.assertIn("Building", st["currently_content"])


class EddyReviewJobTests(_DBTestCase):
    """The on-demand ``eddy-review`` job — DB-rendered body → Opus review →
    editorial_comments rows."""

    def _window_with_content(self):
        db.set_issue_window(issue_number=458, pub_date="2026-05-16",
                            end_date="2026-05-15", start_date="2026-05-08",
                            day_count=7, set_by="t")
        issue_items.upsert_item(issue_number=458, section="notable",
                                source="pinboard", source_id="n1",
                                url="https://a", title="A", body_md="blurb")

    def test_no_window_errors(self):
        result = asyncio.run(eddy_review.run(_base.JobContext()))
        self.assertFalse(result.ok)

    def test_no_team_errors_and_leaves_comments(self):
        self._window_with_content()
        prior = issue_items.write_comment(
            issue_number=458, scope="issue", body_md="prior guidance")
        result = asyncio.run(eddy_review.run(_base.JobContext()))
        self.assertFalse(result.ok)
        # Review never ran — prior comments untouched.
        still = issue_items.get_comment_by_handle(prior["handle"])
        self.assertIsNone(still.get("closed_at"))

    def test_pass_reply_closes_prior_open_comments(self):
        self._window_with_content()
        item = issue_items.list_items(458, section="notable")[0]
        prior = issue_items.write_comment(
            issue_number=458, scope="item", item_id=item["id"],
            body_md="trim the second sentence")
        fc = _FakeBotChannel(persona="eddy", reply="PASS")
        result = asyncio.run(eddy_review.run(_base.JobContext(deps=fc.deps())))
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["pass"])
        self.assertEqual(issue_items.list_open_comments(458), [])
        still = issue_items.get_comment_by_handle(prior["handle"])
        self.assertIsNotNone(still.get("closed_at"))

    def test_anchored_review_writes_comments(self):
        self._window_with_content()
        reply = ("## Notable\n\n"
                 "- <!-- target:n1 --> Tighten the blurb.\n\n"
                 "<!-- target:hygiene --> Alt text missing on the cover.")
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        result = asyncio.run(eddy_review.run(_base.JobContext(deps=fc.deps())))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["comments"], 2)
        open_comments = issue_items.list_open_comments(458)
        scopes = sorted(c["scope"] for c in open_comments)
        self.assertEqual(scopes, ["hygiene", "item"])
        fc.bot.core.assert_awaited()
        # Opus is the default review model.
        self.assertEqual(fc.bot.core.await_args.kwargs.get("model"), "opus")

    def test_review_model_env_override(self):
        with patch.dict(os.environ, {"WORKSHOP_EDDY_DRAFT_REVIEW_MODEL": "sonnet"}):
            self.assertEqual(eddy_review._review_model(), "sonnet")
        self.assertEqual(eddy_review._review_model(), "opus")

    def test_prompt_carries_hygiene_walk(self):
        # The hygiene walk lives in the prompt itself — pin it so a future
        # edit can't silently drop the hygiene lens or the target markers.
        from apps.workshop_bot.tools.llm import anthropic_client
        anthropic_client._prompt_cache.pop("eddy-draft-review", None)
        prompt = anthropic_client.load_prompt("eddy-draft-review")
        self.assertIn("## Hygiene", prompt)
        self.assertIn("<!-- target:n2 -->", prompt)
        for token in ("Anchor / heading hype", "Tonal lurch around links",
                      "Sales-talk in your own writing", "Alt-text",
                      "anchor/domain mismatch"):
            self.assertIn(token, prompt)


if __name__ == "__main__":
    unittest.main()
