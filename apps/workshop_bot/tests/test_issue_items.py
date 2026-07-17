"""issue_items + editorial_comments — CRUD, reorder, promotions, handles."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tests._fixtures import TempDBTestCase as _DBCase  # noqa: E402
from apps.workshop_bot.tools import db, issue_items  # noqa: E402

# ---------------- upsert + list ----------------

class UpsertTests(_DBCase):

    def test_inserts_new_row_and_assigns_position(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", url="https://x", title="A", body_md="hi",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="def", url="https://y", title="B", body_md="ho",
        )
        rows = issue_items.list_items(349, section="notable")
        self.assertEqual([r["id"] for r in rows], [a, b])
        self.assertEqual([r["position"] for r in rows], [1, 2])

    def test_upsert_existing_preserves_position(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", url="https://x", title="A", body_md="hi",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="def", url="https://y", title="B", body_md="ho",
        )
        # Re-upsert ``a`` with a new title; position must stay 1.
        a2 = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", url="https://x", title="A renamed", body_md="hi",
        )
        self.assertEqual(a, a2)
        item_a = issue_items.get_item(a)
        item_b = issue_items.get_item(b)
        self.assertEqual(item_a["position"], 1)
        self.assertEqual(item_a["title"], "A renamed")
        self.assertEqual(item_b["position"], 2)

    def test_renderer_strips_membership_markers_from_body_md(self):
        # A row with a stale ``<!-- cta:1 -->`` marker embedded in body_md
        # (the WT348 manual-seed regression) must render without the
        # marker — placement is editorial state, not row content.
        a = issue_items.upsert_item(
            issue_number=348, section="notable", source="manual",
            source_id="wt348-n1", url="https://example.com/a",
            title="A", body_md="Commentary here.\n\n\n<!-- cta:1 -->",
        )
        from apps.workshop_bot.tools import issue_items_render
        rendered = issue_items_render._render_notable_item(
            issue_items.get_item(a)
        )
        self.assertNotIn("<!-- cta:", rendered)
        self.assertIn("Commentary here.", rendered)

    def test_upsert_dedups_by_url_when_source_identity_changes(self):
        # Regression: WT348 had manually-seeded rows with source='manual'
        # and source_id='wt348-n4'. The next sync_pinboard run upserted
        # using source='pinboard' / a bookmark hash for source_id —
        # canonical key didn't match, and a duplicate row landed alongside
        # the seed. The exercise harness caught the count doubling from
        # 4/11/15 → 8/22/30.
        seeded = issue_items.upsert_item(
            issue_number=348, section="notable", source="manual",
            source_id="wt348-n1", url="https://example.com/a",
            title="A", body_md="seed body",
        )
        refreshed = issue_items.upsert_item(
            issue_number=348, section="notable", source="pinboard",
            source_id="hash-of-bookmark", url="https://example.com/a",
            title="A (refreshed)", body_md="pinboard body",
        )
        # Must be the same row id — no duplicate.
        self.assertEqual(seeded, refreshed)
        rows = issue_items.list_items(348, section="notable")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # Identity was re-keyed to canonical source/source_id.
        self.assertEqual(row["source"], "pinboard")
        self.assertEqual(row["source_id"], "hash-of-bookmark")
        # Upstream fields refreshed.
        self.assertEqual(row["title"], "A (refreshed)")
        self.assertEqual(row["body_md"], "pinboard body")

    def test_upsert_can_move_item_between_sections(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", url="https://x", title="A", body_md="hi",
        )
        issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="abc", url="https://x", title="A", body_md="hi",
        )
        item = issue_items.get_item(a)
        self.assertEqual(item["section"], "brief")

    def test_section_change_reassigns_position_to_end_of_new_section(self):
        # Seed notable so the moved item must get a fresh position there.
        _a_notable = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="n1", body_md="x",
        )
        b_brief = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b1", body_md="x",
        )
        # Move b1 into notable; should get position 2 (after a_notable),
        # not its old brief position 1.
        issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="b1", body_md="x",
        )
        moved = issue_items.get_item(b_brief)
        self.assertEqual(moved["section"], "notable")
        self.assertEqual(moved["position"], 2)
        # Brief is empty now.
        self.assertEqual(issue_items.list_items(349, section="brief"), [])

    def test_rejects_unknown_section_or_source(self):
        with self.assertRaises(ValueError):
            issue_items.upsert_item(
                issue_number=349, section="bogus", source="pinboard",
                source_id="x",
            )
        with self.assertRaises(ValueError):
            issue_items.upsert_item(
                issue_number=349, section="notable", source="bogus",
                source_id="x",
            )

    def test_metadata_round_trips(self):
        item_id = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="https://www.thingelstad.com/2026/05/12/foo",
            url="https://x", title="", body_md="body",
            metadata={"label": "Tuesday @ 9:00 PM", "images": ["a.jpg"]},
        )
        item = issue_items.get_item(item_id)
        self.assertEqual(item["metadata"], {"label": "Tuesday @ 9:00 PM", "images": ["a.jpg"]})

    def test_list_filters_promoted(self):
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p2", body_md="y",
        )
        issue_items.promote(a, promoted_position="after_notable", promoted_heading="Featured")
        all_journal = issue_items.list_items(349, section="journal")
        unpromoted = issue_items.list_items(349, section="journal", include_promoted=False)
        self.assertEqual([r["id"] for r in all_journal], [a, b])
        self.assertEqual([r["id"] for r in unpromoted], [b])
        promoted = issue_items.promoted_items(349)
        self.assertEqual([r["id"] for r in promoted], [a])


# ---------------- editor columns (atom editor, build 1) ----------------

class EditorColumnsTests(_DBCase):

    def _pin(self, source_id, section="brief", title="T", body="b"):
        return issue_items.upsert_item(
            issue_number=349, section=section, source="pinboard",
            source_id=source_id, url=f"https://x/{source_id}",
            title=title, body_md=body,
        )

    def test_section_override_flips_effective_section(self):
        issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="n1", url="https://n/1", title="N", body_md="n",
        )
        b = self._pin("b1")
        issue_items.set_section_override(b, "notable")
        notable = issue_items.list_items(349, section="notable")
        self.assertEqual([r["id"] for r in notable][-1], b)
        self.assertEqual(issue_items.list_items(349, section="brief"), [])
        # Flipped item appended at end of the target list, not interleaved.
        self.assertEqual(notable[-1]["position"], 2)
        # Clear reverts to the sync-owned section.
        issue_items.set_section_override(b, None)
        self.assertEqual(
            [r["id"] for r in issue_items.list_items(349, section="brief")], [b])

    def test_override_and_excluded_survive_sync_upsert(self):
        b = self._pin("b1", body="original")
        issue_items.set_section_override(b, "notable")
        issue_items.set_body_override(b, "edited in Studio")
        e = self._pin("b2")
        issue_items.set_excluded(e, True)
        # Simulate the daily sync refresh: same (issue, source, source_id).
        issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b1", url="https://x/b1", title="T", body_md="refreshed",
        )
        issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b2", url="https://x/b2", title="T", body_md="refreshed",
        )
        flipped = issue_items.get_item(b)
        self.assertEqual(flipped["section_override"], "notable")   # survived
        self.assertEqual(flipped["body_md"], "edited in Studio")   # render uses override
        self.assertEqual(flipped["source_body_md"], "refreshed")   # sync owns source body
        self.assertTrue(flipped["body_overridden"])
        self.assertEqual(issue_items.get_item(e)["excluded"], 1)   # survived
        self.assertEqual(
            [r["id"] for r in issue_items.list_items(349, section="notable")], [b])

    def test_body_override_can_clear_to_source_body(self):
        b = self._pin("b1", body="original")
        issue_items.set_body_override(b, "edited")
        self.assertEqual(issue_items.get_item(b)["body_md"], "edited")
        issue_items.set_body_override(b, None)
        row = issue_items.get_item(b)
        self.assertEqual(row["body_md"], "original")
        self.assertFalse(row["body_overridden"])

    def test_excluded_hidden_from_render_paths_but_listable(self):
        a = self._pin("b1")
        bb = self._pin("b2")
        issue_items.set_excluded(a, True)
        self.assertEqual(
            [r["id"] for r in issue_items.list_items(349, section="brief")], [bb])
        both = issue_items.list_items(349, section="brief", include_excluded=True)
        self.assertEqual([r["id"] for r in both], [a, bb])
        # A deselected promoted item doesn't render either.
        issue_items.promote(a, promoted_position="before_notable", promoted_heading="F")
        self.assertEqual(issue_items.promoted_items(349), [])

    def test_reorder_validates_against_effective_view(self):
        a = self._pin("b1")
        bb = self._pin("b2")
        c = self._pin("b3")
        issue_items.set_excluded(c, True)
        # Excluded row is not part of the permutation.
        issue_items.reorder(349, "brief", [bb, a])
        self.assertEqual(
            [r["id"] for r in issue_items.list_items(349, section="brief")], [bb, a])
        with self.assertRaises(issue_items.ReorderError):
            issue_items.reorder(349, "brief", [bb, a, c])

    def test_set_override_validates(self):
        with self.assertRaises(ValueError):
            issue_items.set_section_override(9999, "notable")
        b = self._pin("b1")
        with self.assertRaises(ValueError):
            issue_items.set_section_override(b, "bogus")
        with self.assertRaises(ValueError):
            issue_items.set_excluded(9999, True)
        with self.assertRaises(ValueError):
            issue_items.set_body_override(9999, "x")


# ---------------- reorder ----------------

class ReorderTests(_DBCase):

    def _seed_three(self):
        ids = []
        for sid in ("a", "b", "c"):
            ids.append(issue_items.upsert_item(
                issue_number=349, section="brief", source="pinboard",
                source_id=sid, title=sid.upper(), body_md=f"body {sid}",
            ))
        return ids

    def test_simple_reverse(self):
        a, b, c = self._seed_three()
        issue_items.reorder(349, "brief", [c, b, a])
        rows = issue_items.list_items(349, section="brief")
        self.assertEqual([r["id"] for r in rows], [c, b, a])
        self.assertEqual([r["position"] for r in rows], [1, 2, 3])

    def test_rejects_missing_id(self):
        a, b, c = self._seed_three()
        with self.assertRaises(issue_items.ReorderError) as cm:
            issue_items.reorder(349, "brief", [a, b])
        self.assertIn("missing", str(cm.exception))

    def test_rejects_extra_id(self):
        a, b, c = self._seed_three()
        with self.assertRaises(issue_items.ReorderError) as cm:
            issue_items.reorder(349, "brief", [a, b, c, 999])
        self.assertIn("don't exist", str(cm.exception))

    def test_rejects_duplicate(self):
        a, b, c = self._seed_three()
        with self.assertRaises(issue_items.ReorderError) as cm:
            issue_items.reorder(349, "brief", [a, b, b])
        self.assertIn("duplicate", str(cm.exception))

    def test_reorder_ignores_promoted_items(self):
        # Promoted items aren't in the per-section reorder list.
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p2", body_md="y",
        )
        c = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p3", body_md="z",
        )
        issue_items.promote(b, promoted_position="after_notable", promoted_heading="Feature")
        issue_items.reorder(349, "journal", [c, a])  # only the non-promoted ids
        rows = issue_items.list_items(349, section="journal", include_promoted=False)
        self.assertEqual([r["id"] for r in rows], [c, a])

    def test_reorder_rejects_promoted_id_in_order(self):
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p2", body_md="y",
        )
        issue_items.promote(b, promoted_position="after_notable", promoted_heading="Feature")
        with self.assertRaises(issue_items.ReorderError):
            issue_items.reorder(349, "journal", [a, b])


# ---------------- promotions ----------------

class PromotionTests(_DBCase):

    def test_promote_unpromote_roundtrip(self):
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        issue_items.promote(a, promoted_position="after_journal", promoted_heading="Featured")
        item = issue_items.get_item(a)
        self.assertEqual(item["is_promoted"], 1)
        self.assertEqual(item["promoted_position"], "after_journal")
        self.assertEqual(item["promoted_heading"], "Featured")
        issue_items.unpromote(a)
        item = issue_items.get_item(a)
        self.assertEqual(item["is_promoted"], 0)
        self.assertIsNone(item["promoted_position"])

    def test_rejects_bad_position(self):
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        with self.assertRaises(ValueError):
            issue_items.promote(a, promoted_position="bogus", promoted_heading="Featured")

    def test_rejects_empty_heading(self):
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        with self.assertRaises(ValueError):
            issue_items.promote(a, promoted_position="after_journal", promoted_heading="   ")

    def test_clear_promotions(self):
        a = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p1", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="p2", body_md="y",
        )
        issue_items.promote(a, promoted_position="after_notable", promoted_heading="A")
        issue_items.promote(b, promoted_position="after_brief", promoted_heading="B")
        issue_items.clear_promotions(349)
        self.assertEqual(issue_items.promoted_items(349), [])


# ---------------- compact + clear ----------------

class CompactClearTests(_DBCase):

    def test_compact_after_simulated_delete(self):
        ids = []
        for sid in ("a", "b", "c"):
            ids.append(issue_items.upsert_item(
                issue_number=349, section="brief", source="pinboard",
                source_id=sid, body_md=sid,
            ))
        # Simulate a delete by clearing the issue and re-creating only two.
        # (compact_positions is the safety net for whatever path leaves gaps.)
        issue_items.clear_issue(349)
        a = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="a", body_md="a",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b", body_md="b",
        )
        # Manually create a gap, then compact.
        with db.connect() as conn:
            conn.execute("UPDATE issue_items SET position = 5 WHERE id = ?", (b,))
        issue_items.compact_positions(349, "brief")
        rows = issue_items.list_items(349, section="brief")
        self.assertEqual([r["position"] for r in rows], [1, 2])
        self.assertEqual([r["id"] for r in rows], [a, b])


# ---------------- editorial comments ----------------

class EditorialCommentTests(_DBCase):

    def test_item_scope_assigns_handle_with_section_letter(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="abc", body_md="x",
        )
        c = issue_items.write_comment(
            issue_number=349, scope="item", item_id=a,
            body_md="Lead with this one.", verdict="suggestion",
        )
        self.assertEqual(c["handle"], "E349-N1")
        self.assertEqual(c["section"], "notable")  # derived from item

    def test_handle_ordinals_per_letter(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="journal", source="microblog",
            source_id="b", body_md="x",
        )
        c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        c2 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        c3 = issue_items.write_comment(issue_number=349, scope="item", item_id=b, body_md="…")
        c4 = issue_items.write_comment(issue_number=349, scope="hygiene", body_md="…")
        c5 = issue_items.write_comment(issue_number=349, scope="issue", body_md="…")
        self.assertEqual(c1["handle"], "E349-N1")
        self.assertEqual(c2["handle"], "E349-N2")
        self.assertEqual(c3["handle"], "E349-J1")
        self.assertEqual(c4["handle"], "E349-X1")
        self.assertEqual(c5["handle"], "E349-W1")

    def test_handle_uniqueness_constraint(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        # Manually inserting a duplicate handle blows up — UNIQUE index guard.
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            issue_items.write_comment(
                issue_number=349, scope="item", item_id=a, body_md="…",
                handle=c1["handle"],
            )

    def test_supersede_chains(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v1")
        c2 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v2")
        issue_items.supersede(c1["id"], c2["id"])
        open_ones = issue_items.list_open_comments(349)
        self.assertEqual([c["id"] for c in open_ones], [c2["id"]])
        # Old handle still resolves to the original row — history preserved.
        old = issue_items.get_comment_by_handle(c1["handle"])
        self.assertIsNotNone(old)
        self.assertEqual(old["body_md"], "v1")

    def test_supersede_all_open(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        b = issue_items.upsert_item(
            issue_number=349, section="brief", source="pinboard",
            source_id="b", body_md="y",
        )
        _c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="…")
        _c2 = issue_items.write_comment(issue_number=349, scope="item", item_id=b, body_md="…")
        _c3 = issue_items.write_comment(issue_number=349, scope="hygiene", body_md="…")
        # New pass starts with c4 — supersede everything else.
        c4 = issue_items.write_comment(issue_number=349, scope="hygiene", body_md="fresh pass")
        replaced = issue_items.supersede_all_open(349, by_id=c4["id"])
        self.assertEqual(replaced, 3)  # c1, c2, c3 all marked
        open_ones = issue_items.list_open_comments(349)
        self.assertEqual([c["id"] for c in open_ones], [c4["id"]])

    def test_close_all_open_comments_drops_them_from_open_set(self):
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v1")
        c2 = issue_items.write_comment(issue_number=349, scope="hygiene", body_md="v2")
        # Before close: both open.
        self.assertEqual(
            sorted(c["id"] for c in issue_items.list_open_comments(349)),
            sorted([c1["id"], c2["id"]]),
        )
        closed_count = issue_items.close_all_open_comments(349)
        self.assertEqual(closed_count, 2)
        # After close: drawer is empty even though the rows still exist.
        self.assertEqual(issue_items.list_open_comments(349), [])
        # History still resolves by handle.
        still = issue_items.get_comment_by_handle(c1["handle"])
        self.assertIsNotNone(still)
        self.assertEqual(still["body_md"], "v1")
        self.assertIsNotNone(still.get("closed_at"))

    def test_close_is_idempotent_when_nothing_open(self):
        # Calling close twice in a row should be a clean no-op the
        # second time (the PASS path runs every update-draft).
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v")
        self.assertEqual(issue_items.close_all_open_comments(349), 1)
        self.assertEqual(issue_items.close_all_open_comments(349), 0)

    def test_close_doesnt_touch_already_superseded(self):
        # A row that was already superseded by a follow-on comment is
        # already filtered out of list_open_comments — close shouldn't
        # re-stamp its closed_at.
        a = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        c1 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v1")
        c2 = issue_items.write_comment(issue_number=349, scope="item", item_id=a, body_md="v2")
        issue_items.supersede(c1["id"], c2["id"])
        issue_items.close_all_open_comments(349)
        # c1 is superseded (not closed); c2 is now closed.
        c1_now = issue_items.get_comment_by_handle(c1["handle"])
        c2_now = issue_items.get_comment_by_handle(c2["handle"])
        self.assertIsNone(c1_now.get("closed_at"))
        self.assertIsNotNone(c2_now.get("closed_at"))

    def test_handles_never_collide_across_issues(self):
        a349 = issue_items.upsert_item(
            issue_number=349, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        a350 = issue_items.upsert_item(
            issue_number=350, section="notable", source="pinboard",
            source_id="a", body_md="x",
        )
        c349 = issue_items.write_comment(issue_number=349, scope="item", item_id=a349, body_md="…")
        c350 = issue_items.write_comment(issue_number=350, scope="item", item_id=a350, body_md="…")
        self.assertEqual(c349["handle"], "E349-N1")
        self.assertEqual(c350["handle"], "E350-N1")

    def test_rejects_item_scope_without_item_id(self):
        with self.assertRaises(ValueError):
            issue_items.write_comment(issue_number=349, scope="item", body_md="x")

    def test_section_scope_requires_section(self):
        with self.assertRaises(ValueError):
            issue_items.write_comment(
                issue_number=349, scope="section", body_md="x",
            )

    def test_section_scope_uses_section_letter(self):
        c = issue_items.write_comment(
            issue_number=349, scope="section", section="brief",
            body_md="Brief is leaning too tech-heavy.",
        )
        self.assertEqual(c["handle"], "E349-B1")


if __name__ == "__main__":
    unittest.main()
