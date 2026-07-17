"""editorial__get_comment + editorial__list_open agent tools."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import db, issue_items  # noqa: E402
from apps.workshop_bot.tools.llm.local_tools import (  # noqa: E402
    t_editorial_get_comment,
    t_editorial_list_open,
)


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


class GetCommentTests(_DBCase):

    def test_returns_item_anchored_comment_with_item_context(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", url="https://x", title="A Long Article", body_md="lots of body",
        )
        c = issue_items.write_comment(
            issue_number=349, scope="item", item_id=a,
            body_md="Lead with this one.", verdict="suggestion",
            anchor_text="lead",
        )
        out = t_editorial_get_comment(None, handle=c["handle"])
        self.assertEqual(out["handle"], "E349-N1")
        self.assertEqual(out["scope"], "item")
        self.assertEqual(out["verdict"], "suggestion")
        self.assertEqual(out["anchor_text"], "lead")
        self.assertEqual(out["body_md"], "Lead with this one.")
        self.assertFalse(out["superseded"])
        self.assertNotIn("replaced_by_handle", out)
        item = out["item"]
        self.assertEqual(item["section"], "notable")
        self.assertEqual(item["title"], "A Long Article")
        self.assertEqual(item["url"], "https://x")
        self.assertIn("lots of body", item["body_preview"])

    def test_section_scoped_has_no_item_context(self):
        c = issue_items.write_comment(
            issue_number=349, scope="section", section="brief",
            body_md="Brief feels tech-heavy this week.",
        )
        out = t_editorial_get_comment(None, handle=c["handle"])
        self.assertEqual(out["handle"], "E349-B1")
        self.assertEqual(out["section"], "brief")
        self.assertNotIn("item", out)

    def test_case_insensitive_handle(self):
        c = issue_items.write_comment(
            issue_number=349, scope="hygiene",
            body_md="Anchor mismatch on N3.",
        )
        out = t_editorial_get_comment(None, handle=c["handle"].lower())
        self.assertEqual(out["handle"], c["handle"])

    def test_missing_handle_returns_error(self):
        out = t_editorial_get_comment(None, handle="E999-Z1")
        self.assertIn("error", out)
        self.assertIn("E999-Z1", out["error"])

    def test_empty_handle_returns_error(self):
        out = t_editorial_get_comment(None, handle="")
        self.assertIn("error", out)

    def test_superseded_comment_exposes_replacement_handle(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", body_md="x",
        )
        c1 = issue_items.write_comment(
            issue_number=349, scope="item", item_id=a, body_md="v1",
        )
        c2 = issue_items.write_comment(
            issue_number=349, scope="item", item_id=a, body_md="v2",
        )
        issue_items.supersede(c1["id"], c2["id"])
        out = t_editorial_get_comment(None, handle=c1["handle"])
        self.assertTrue(out["superseded"])
        self.assertEqual(out["replaced_by_handle"], c2["handle"])
        # The body is still v1 (the original comment survives in history).
        self.assertEqual(out["body_md"], "v1")


class ListOpenTests(_DBCase):

    def _seed(self):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-23", 7)
        db.set_issue_window(issue_number=349, pub_date=w["pub_date"],
                            end_date=w["end_date"], start_date=w["start_date"],
                            day_count=w["day_count"], set_by="test")
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", title="A", body_md="x",
        )
        issue_items.write_comment(
            issue_number=349, scope="item", item_id=a,
            body_md="Lead with this one — the framing is strong.",
        )
        issue_items.write_comment(
            issue_number=349, scope="hygiene",
            body_md="Anchor text on N3 doesn't match the destination domain — worth a quick fix.",
        )

    def test_defaults_to_in_flight_issue(self):
        self._seed()
        out = t_editorial_list_open(None)
        self.assertEqual(out["issue_number"], 349)
        self.assertEqual(out["count"], 2)
        handles = sorted(c["handle"] for c in out["comments"])
        self.assertEqual(handles, ["E349-N1", "E349-X1"])

    def test_explicit_issue_number(self):
        self._seed()
        out = t_editorial_list_open(None, issue_number=349)
        self.assertEqual(out["issue_number"], 349)
        self.assertEqual(out["count"], 2)

    def test_no_window_no_arg_returns_error(self):
        out = t_editorial_list_open(None)
        self.assertIn("error", out)

    def test_snippets_truncated(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", body_md="x",
        )
        long_body = "a" * 500
        issue_items.write_comment(
            issue_number=349, scope="item", item_id=a, body_md=long_body,
        )
        out = t_editorial_list_open(None, issue_number=349)
        snippet = out["comments"][0]["snippet"]
        self.assertTrue(snippet.endswith("…"))
        self.assertLessEqual(len(snippet), 141 + 1)


if __name__ == "__main__":
    unittest.main()
