"""issue_items_sync — Pinboard + micro.blog → rows projection."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import db, issue_items, issue_items_sync  # noqa: E402


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


# ---------------- Pinboard ----------------

WINDOW = {"start_date": "2026-05-15", "end_date": "2026-05-22"}


def _pin_item(*, sid: str, url: str, title: str, desc: str = "", brief: bool = False) -> dict:
    return {
        "url": url,
        "title": title,
        "description": desc,
        "tags": "_brief" if brief else "",
        "added": "2026-05-16T14:00:00Z",
        "added_date": "2026-05-16",
        "hash": sid,
        "pinboard_url": f"https://pinboard.in/u:jamie/b:{sid}/",
    }


class PinboardSyncTests(_DBCase):
    def test_populates_notable_and_brief_with_positions(self):
        candidates = {
            "notable": [
                _pin_item(sid="h1", url="https://a", title="A"),
                _pin_item(sid="h2", url="https://b", title="B", desc="commentary"),
            ],
            "brief": [
                _pin_item(sid="h3", url="https://c", title="C", brief=True),
            ],
        }
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=candidates,
        ):
            out = issue_items_sync.sync_pinboard(349, WINDOW)
        self.assertEqual(out, {"observed": 3, "pruned": 0})
        notable = issue_items.list_items(349, section="notable")
        brief = issue_items.list_items(349, section="brief")
        self.assertEqual([r["title"] for r in notable], ["A", "B"])
        self.assertEqual([r["position"] for r in notable], [1, 2])
        self.assertEqual(brief[0]["title"], "C")
        self.assertEqual(brief[0]["metadata"]["is_brief_tagged"], True)
        self.assertEqual(notable[1]["body_md"], "commentary")

    def test_prune_removes_disappeared_items(self):
        first = {
            "notable": [
                _pin_item(sid="h1", url="https://a", title="A"),
                _pin_item(sid="h2", url="https://b", title="B"),
            ],
            "brief": [],
        }
        second = {
            "notable": [
                _pin_item(sid="h1", url="https://a", title="A"),
                # h2 deleted upstream
            ],
            "brief": [],
        }
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=first,
        ):
            issue_items_sync.sync_pinboard(349, WINDOW)
        self.assertEqual(len(issue_items.list_items(349, section="notable")), 2)
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=second,
        ):
            out = issue_items_sync.sync_pinboard(349, WINDOW)
        self.assertEqual(out, {"observed": 1, "pruned": 1})
        survivors = issue_items.list_items(349, section="notable")
        self.assertEqual([r["title"] for r in survivors], ["A"])

    def test_prune_preserves_promoted_rows(self):
        # An item Eddy promoted earlier must survive even if Pinboard
        # drops it (the editorial decision outweighs the upstream churn;
        # next review can flag the absence).
        candidates = {
            "notable": [_pin_item(sid="h1", url="https://a", title="A")],
            "brief": [],
        }
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=candidates,
        ):
            issue_items_sync.sync_pinboard(349, WINDOW)
        # Eddy promotes h1.
        h1 = issue_items.list_items(349, section="notable")[0]["id"]
        issue_items.promote(h1, promoted_position="after_notable", promoted_heading="Featured")
        # Upstream drops it.
        empty = {"notable": [], "brief": []}
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=empty,
        ):
            out = issue_items_sync.sync_pinboard(349, WINDOW)
        self.assertEqual(out["pruned"], 0)
        self.assertEqual(len(issue_items.promoted_items(349)), 1)

    def test_prune_unanchors_editorial_comment_before_delete(self):
        # editorial_comments.item_id is an FK to issue_items(id) with no
        # ON DELETE action — pruning a stale item that has a draft-review
        # comment anchored to it must NULL out the FK first, not let the
        # DELETE blow up with "FOREIGN KEY constraint failed".
        first = {
            "notable": [
                _pin_item(sid="h1", url="https://a", title="A"),
                _pin_item(sid="h2", url="https://b", title="B"),
            ],
            "brief": [],
        }
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=first,
        ):
            issue_items_sync.sync_pinboard(349, WINDOW)
        # Anchor an editorial comment on h2.
        h2 = [r for r in issue_items.list_items(349, section="notable") if r["title"] == "B"][0][
            "id"
        ]
        comment = issue_items.write_comment(
            issue_number=349,
            scope="item",
            item_id=h2,
            body_md="anchor text would go here",
        )
        # Upstream drops h2.
        second = {
            "notable": [_pin_item(sid="h1", url="https://a", title="A")],
            "brief": [],
        }
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=second,
        ):
            out = issue_items_sync.sync_pinboard(349, WINDOW)
        self.assertEqual(out, {"observed": 1, "pruned": 1})
        # Comment row survives, but item_id is nulled.
        survivor = issue_items.get_comment_by_handle(comment["handle"])
        self.assertIsNotNone(survivor)
        self.assertIsNone(survivor["item_id"])
        self.assertEqual(survivor["body_md"], "anchor text would go here")

    def test_retag_moves_item_between_sections(self):
        first = {
            "notable": [_pin_item(sid="h1", url="https://a", title="A")],
            "brief": [],
        }
        # Jamie adds _brief tag.
        second = {
            "notable": [],
            "brief": [_pin_item(sid="h1", url="https://a", title="A", brief=True)],
        }
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=first,
        ):
            issue_items_sync.sync_pinboard(349, WINDOW)
        h1 = issue_items.list_items(349, section="notable")[0]["id"]
        with patch(
            "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
            return_value=second,
        ):
            out = issue_items_sync.sync_pinboard(349, WINDOW)
        self.assertEqual(out["pruned"], 0)  # same hash, just moved
        self.assertEqual(len(issue_items.list_items(349, section="notable")), 0)
        brief = issue_items.list_items(349, section="brief")
        self.assertEqual(brief[0]["id"], h1)  # same row, moved
        self.assertEqual(brief[0]["section"], "brief")


# ---------------- micro.blog ----------------


def _mb_post(
    *,
    url: str,
    title: str = "",
    content_md: str = "",
    published: str = "2026-05-16T14:00:00Z",
    categories: list[str] | None = None,
) -> dict:
    return {
        "url": url,
        "title": title,
        "published": published,
        "content_md": content_md,
        "categories": list(categories or []),
    }


class MicroblogSyncTests(_DBCase):
    def test_populates_journal_with_label_metadata(self):
        posts = [
            _mb_post(
                url="https://www.thingelstad.com/2026/05/16/foo",
                title="A titled post",
                content_md="hello",
                published="2026-05-16T21:00:00Z",  # 4pm CT Saturday
            ),
            _mb_post(
                url="https://www.thingelstad.com/2026/05/17/bar",
                content_md="status only",
                published="2026-05-17T15:30:00Z",  # 10:30am CT Sunday
            ),
        ]
        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                return_value=posts,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.journal_images.rehost_in_markdown",
                side_effect=lambda md, n: md,  # no-op (no images to rehost in fixtures)
            ),
        ):
            out = issue_items_sync.sync_microblog(349, WINDOW)
        self.assertEqual(out, {"observed": 2, "pruned": 0, "featured": 0, "alts_filled": []})
        journal = issue_items.list_items(349, section="journal")
        self.assertEqual([r["title"] for r in journal], ["A titled post", None])
        self.assertEqual([r["body_md"] for r in journal], ["hello", "status only"])
        # Label format check (Saturday @ 4:00 PM / Sunday @ 10:30 AM)
        labels = [r["metadata"]["label"] for r in journal]
        self.assertEqual(labels, ["Saturday @ 4:00 PM", "Sunday @ 10:30 AM"])
        # Categories empty in fixtures → metadata.categories === [].
        for row in journal:
            self.assertEqual(row["metadata"].get("categories"), [])
        # Neither post was Featured, so no rows got promoted.
        for row in journal:
            self.assertFalse(row.get("is_promoted"))

    def test_rehost_failure_falls_back_to_raw(self):
        posts = [
            _mb_post(
                url="https://www.thingelstad.com/2026/05/16/foo",
                content_md="![](https://oops.example/img.jpg)",
            ),
        ]

        def _boom(md, n):
            raise RuntimeError("download failed")

        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                return_value=posts,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.journal_images.rehost_in_markdown",
                side_effect=_boom,
            ),
        ):
            out = issue_items_sync.sync_microblog(349, WINDOW)
        self.assertEqual(out["observed"], 1)
        row = issue_items.list_items(349, section="journal")[0]
        # Body falls back to raw — better a dead image than no entry.
        self.assertEqual(row["body_md"], "![](https://oops.example/img.jpg)")

    # ---------- Featured-category promotion ----------

    def test_featured_category_promotes_row_above_notable(self):
        """A micro.blog post tagged with ``Featured`` should land in the
        Journal section AS A PROMOTED ROW — is_promoted=1,
        promoted_position='before_notable', promoted_heading=post title."""
        posts = [
            _mb_post(
                url="https://www.thingelstad.com/2026/05/16/big",
                title="The Big Featured Post",
                content_md="A long-form piece.",
                published="2026-05-16T15:00:00Z",
                categories=["Featured", "Tech"],
            ),
            _mb_post(
                url="https://www.thingelstad.com/2026/05/17/regular",
                content_md="A normal note.",
                published="2026-05-17T15:00:00Z",
                categories=[],
            ),
        ]
        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                return_value=posts,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.journal_images.rehost_in_markdown",
                side_effect=lambda md, n: md,
            ),
        ):
            out = issue_items_sync.sync_microblog(349, WINDOW)
        self.assertEqual(out, {"observed": 2, "pruned": 0, "featured": 1, "alts_filled": []})
        journal = issue_items.list_items(349, section="journal", include_promoted=True)
        by_url = {r["url"]: r for r in journal}
        featured = by_url["https://www.thingelstad.com/2026/05/16/big"]
        regular = by_url["https://www.thingelstad.com/2026/05/17/regular"]
        self.assertEqual(featured["is_promoted"], 1)
        self.assertEqual(featured["promoted_position"], "before_notable")
        self.assertEqual(featured["promoted_heading"], "The Big Featured Post")
        self.assertEqual(regular["is_promoted"], 0)
        self.assertIsNone(regular["promoted_position"])
        # Categories captured in metadata for downstream tools (audit, debug).
        self.assertEqual(featured["metadata"].get("categories"), ["Featured", "Tech"])
        self.assertEqual(regular["metadata"].get("categories"), [])

    def test_untagging_clears_prior_featured_promotion(self):
        """If a row was Featured-tagged previously and Jamie removes the
        tag, a fresh sync clears the promotion (idempotent re-sync)."""
        # First sync: post is Featured.
        posts = [
            _mb_post(
                url="https://www.thingelstad.com/2026/05/16/big",
                title="The Big Post",
                content_md="x",
                published="2026-05-16T15:00:00Z",
                categories=["Featured"],
            ),
        ]
        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                return_value=posts,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.journal_images.rehost_in_markdown",
                side_effect=lambda md, n: md,
            ),
        ):
            issue_items_sync.sync_microblog(349, WINDOW)
        row = issue_items.list_items(349, section="journal", include_promoted=True)[0]
        self.assertEqual(row["is_promoted"], 1)

        # Re-sync with the same post but no Featured category — promotion clears.
        posts[0]["categories"] = []
        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                return_value=posts,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.journal_images.rehost_in_markdown",
                side_effect=lambda md, n: md,
            ),
        ):
            out = issue_items_sync.sync_microblog(349, WINDOW)
        self.assertEqual(out["featured"], 0)
        row = issue_items.list_items(349, section="journal", include_promoted=True)[0]
        self.assertEqual(row["is_promoted"], 0)
        self.assertIsNone(row["promoted_position"])
        self.assertIsNone(row["promoted_heading"])

    def test_featured_heading_falls_back_to_first_line_when_no_title(self):
        """A note-style Featured post (no title) uses the first line of
        the body for its H2 heading."""
        posts = [
            _mb_post(
                url="https://www.thingelstad.com/2026/05/16/x",
                title="",  # no title — note-style entry
                content_md="A meaningful first line.\n\nMore body.",
                published="2026-05-16T15:00:00Z",
                categories=["Featured"],
            ),
        ]
        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                return_value=posts,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.journal_images.rehost_in_markdown",
                side_effect=lambda md, n: md,
            ),
        ):
            issue_items_sync.sync_microblog(349, WINDOW)
        row = issue_items.list_items(349, section="journal", include_promoted=True)[0]
        self.assertEqual(row["is_promoted"], 1)
        self.assertEqual(row["promoted_heading"], "A meaningful first line.")


# ---------------- sync_all ----------------


class SyncAllTests(_DBCase):
    def test_failures_in_one_source_dont_block_the_other(self):
        # Pinboard works; micro.blog raises.
        candidates = {
            "notable": [_pin_item(sid="h1", url="https://a", title="A")],
            "brief": [],
        }
        with (
            patch(
                "apps.workshop_bot.tools.issue_items_sync.pinboard.issue_window_candidates",
                return_value=candidates,
            ),
            patch(
                "apps.workshop_bot.tools.issue_items_sync.microblog.posts_in_window",
                side_effect=RuntimeError("micropub 500"),
            ),
        ):
            out = issue_items_sync.sync_all(349, WINDOW)
        self.assertEqual(out["pinboard"]["observed"], 1)
        self.assertEqual(out["microblog"]["observed"], 0)
        self.assertIn("error", out["microblog"])
        # Pinboard rows landed despite the micro.blog error.
        self.assertEqual(len(issue_items.list_items(349, section="notable")), 1)


if __name__ == "__main__":
    unittest.main()
