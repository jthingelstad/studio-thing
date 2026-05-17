"""Side-by-side create-final proposal HTML page."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import render  # noqa: E402


def _row(id_: int, section: str, title: str, url: str) -> dict:
    return {"id": id_, "section": section, "title": title, "url": url, "body_md": "x"}


class ProposalHtmlTests(unittest.TestCase):

    def _build(self, *, proposal: dict, rows_by_section: dict):
        # Build the synth maps the same way create-final does — by row
        # position within each section.
        synth_to_row: dict[str, int] = {}
        row_to_synth: dict[int, str] = {}
        for section, prefix in (("notable", "n"), ("brief", "b"), ("journal", "j")):
            for i, row in enumerate(rows_by_section.get(section, []), start=1):
                synth = f"{prefix}{i}"
                synth_to_row[synth] = int(row["id"])
                row_to_synth[int(row["id"])] = synth
        return render.create_final_proposal_html(
            issue_number=349, thesis="Test thesis.",
            rows_by_section=rows_by_section, proposal=proposal,
            synth_to_row=synth_to_row, row_to_synth=row_to_synth,
        )

    def test_renders_two_columns_with_current_and_proposed(self):
        rows = {
            "notable": [_row(1, "notable", "A", "http://a"), _row(2, "notable", "B", "http://b")],
            "brief": [_row(3, "brief", "X", "http://x")],
            "journal": [_row(4, "journal", "P", "http://p")],
        }
        proposal = {
            "thesis": "Test thesis.",
            "notable_order": ["n2", "n1"],
            "brief_order": ["b1"],
            "journal_order": ["j1"],
            "promotions": [],
            "membership_blocks": [],
        }
        page = self._build(proposal=proposal, rows_by_section=rows)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        # Both columns present.
        self.assertIn("Current order", page)
        self.assertIn("Proposed by Eddy", page)
        # SVG canvas for connector lines.
        self.assertIn('id="proposal-connectors"', page)
        # Items appear on both sides with stable data-id (used by JS
        # to draw connector lines between left↔right anchors).
        self.assertIn('data-side="current" data-id="n1"', page)
        self.assertIn('data-side="proposed" data-id="n1"', page)
        self.assertIn('data-side="proposed" data-id="n2"', page)
        # n2 moved (was position 2, now position 1) → highlight class
        # on the proposed side only.
        proposed_n2 = page.find('data-side="proposed" data-id="n2"')
        self.assertGreater(proposed_n2, 0)
        # Look backwards from the data-side attribute for the class list.
        snippet = page[max(0, proposed_n2 - 80):proposed_n2]
        self.assertIn("moved", snippet)
        # Thesis renders.
        self.assertIn("Test thesis.", page)

    def test_promoted_item_strikethrough_on_left_featured_on_right(self):
        rows = {
            "notable": [_row(1, "notable", "Lead piece", "http://a")],
            "brief": [],
            "journal": [_row(10, "journal", "The Big Read", "http://big")],
        }
        proposal = {
            "thesis": "Featuring the journal piece.",
            "notable_order": ["n1"],
            "brief_order": [],
            "journal_order": [],
            "promotions": [{
                "id": "j1", "heading": "Featured: The Big Read",
                "position": "after_notable", "rationale": "central piece",
            }],
            "membership_blocks": [],
        }
        page = self._build(proposal=proposal, rows_by_section=rows)
        # Left column shows j1 with promoted styling.
        left = page.find('data-side="current" data-id="j1"')
        self.assertGreater(left, 0)
        self.assertIn("promoted", page[max(0, left - 80):left])
        # Right column has a featured section near after_notable.
        self.assertIn("Featured: The Big Read", page)
        self.assertIn('data-position="after_notable"', page)
        self.assertIn('data-side="featured" data-id="j1"', page)

    def test_membership_markers_render_inline_pills(self):
        rows = {
            "notable": [_row(1, "notable", "A", "http://a")],
            "brief": [_row(2, "brief", "B", "http://b")],
            "journal": [],
        }
        proposal = {
            "thesis": "x.",
            "notable_order": ["n1"],
            "brief_order": ["b1"],
            "journal_order": [],
            "promotions": [],
            "membership_blocks": [
                {"kind": "cta", "after": "n1", "rationale": "after lead"},
                {"kind": "thanks", "before_haiku": True, "rationale": "end of issue"},
            ],
        }
        page = self._build(proposal=proposal, rows_by_section=rows)
        self.assertIn('class="marker"', page)
        self.assertIn(">cta:1<", page)
        self.assertIn(">thanks:1<", page)
        # cta:1 (after n1) appears in the Notable section of the proposed
        # column; thanks:1 (before_haiku) lands at the end of Briefly.
        notable_block_start = page.find("Proposed by Eddy")
        cta_pos = page.find(">cta:1<", notable_block_start)
        thanks_pos = page.find(">thanks:1<", notable_block_start)
        self.assertGreater(cta_pos, 0)
        self.assertGreater(thanks_pos, cta_pos)

    def test_no_change_proposal_shows_note(self):
        rows = {
            "notable": [_row(1, "notable", "A", "http://a")],
            "brief": [],
            "journal": [],
        }
        proposal = {
            "thesis": "leave it.",
            "notable_order": ["n1"],
            "brief_order": [],
            "journal_order": [],
            "promotions": [],
            "membership_blocks": [],
        }
        page = self._build(proposal=proposal, rows_by_section=rows)
        self.assertIn("No changes proposed", page)

    def test_legend_present(self):
        rows = {"notable": [_row(1, "notable", "A", "http://a")], "brief": [], "journal": []}
        proposal = {
            "thesis": "x.", "notable_order": ["n1"], "brief_order": [], "journal_order": [],
            "promotions": [], "membership_blocks": [],
        }
        page = self._build(proposal=proposal, rows_by_section=rows)
        self.assertIn('class="legend"', page)
        self.assertIn("moved", page)
        self.assertIn("promoted", page)
        self.assertIn("membership marker", page)

    def test_connector_script_present(self):
        rows = {"notable": [_row(1, "notable", "A", "http://a")], "brief": [], "journal": []}
        proposal = {
            "thesis": "x.", "notable_order": ["n1"], "brief_order": [], "journal_order": [],
            "promotions": [], "membership_blocks": [],
        }
        page = self._build(proposal=proposal, rows_by_section=rows)
        # JS reads data-side anchors to draw lines.
        self.assertIn('data-side="current"', page)
        self.assertIn('data-side="proposed"', page)
        self.assertIn("getBoundingClientRect", page)
        self.assertIn("createElementNS", page)


if __name__ == "__main__":
    unittest.main()
