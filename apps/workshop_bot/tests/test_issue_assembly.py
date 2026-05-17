"""issue_assembly — atoms + section bodies → final.md / publish.md."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import issue_assembly  # noqa: E402


SAMPLE_ATOMS = {
    "intro": "Welcome to the issue.",
    "currently": "**Listening:** music",
    "cover": '<img src="https://x/cover.jpg" alt="cover" />\n\nA caption.',
    "outro": "Outro prose.",
    "haiku": "**line one  \nline two  \nline three**",
}


SAMPLE_SECTIONS = {
    "notable": "### [Item A](https://a)\n\nCommentary A.\n\n\n### [Item B](https://b)\n\nCommentary B.",
    "journal": "[Saturday @ 4:00 PM](https://j1)\n\nStatus post.",
    "brief": "Quick take. → **[Brief A](https://ba)**",
}


class AssembleFinalTests(unittest.TestCase):

    def test_layout_with_no_features(self):
        out = issue_assembly.assemble_final(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=[],
        )
        # Block markers present for every section.
        for name in ("intro", "currently", "cover", "notable", "journal", "brief", "outro", "haiku"):
            self.assertIn(f"<!-- block:{name} -->", out)
            self.assertIn(f"<!-- /block:{name} -->", out)
        # Headings live above their blocks (Currently / Notable / Journal / Briefly).
        self.assertRegex(out, r"## Currently\n\n<!-- block:currently -->")
        self.assertRegex(out, r"## Notable\n\n<!-- block:notable -->")
        self.assertRegex(out, r"## Journal\n\n<!-- block:journal -->")
        self.assertRegex(out, r"## Briefly\n\n<!-- block:brief -->")
        # Outro and haiku close.
        self.assertIn("A haiku to leave you with…", out)
        self.assertIn("Check out the [Weekly Thing on Reddit]", out)

    def test_features_splice_after_named_parent(self):
        features = [
            ("after_notable", "## Featured · Team Post\n\nPromoted body."),
        ]
        out = issue_assembly.assemble_final(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=features,
        )
        # The featured section appears AFTER the notable block close and
        # BEFORE the next ``---`` (which precedes Journal).
        notable_close = out.find("<!-- /block:notable -->")
        feature_idx = out.find("## Featured · Team Post")
        journal_head = out.find("## Journal")
        self.assertLess(notable_close, feature_idx)
        self.assertLess(feature_idx, journal_head)

    def test_two_features_at_same_position(self):
        features = [
            ("after_notable", "## Featured · A\n\nbody A"),
            ("after_notable", "## Featured · B\n\nbody B"),
        ]
        out = issue_assembly.assemble_final(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=features,
        )
        # Both featured sections splice in order, separated by ``---``.
        a_idx = out.find("## Featured · A")
        b_idx = out.find("## Featured · B")
        self.assertLess(a_idx, b_idx)
        between = out[a_idx:b_idx]
        self.assertIn("---", between)

    def test_empty_section_blocks_stay_present(self):
        bodies = {"notable": "", "journal": "", "brief": ""}
        out = issue_assembly.assemble_final(
            atoms=SAMPLE_ATOMS, section_bodies=bodies, features=[],
        )
        # The blocks still appear (empty), preserving file shape.
        self.assertIn("<!-- block:notable -->\n<!-- /block:notable -->", out)
        self.assertIn("<!-- block:journal -->\n<!-- /block:journal -->", out)

    def test_ends_with_newline(self):
        out = issue_assembly.assemble_final(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=[],
        )
        self.assertTrue(out.endswith("\n"))


class AssemblePublishTests(unittest.TestCase):

    def test_strips_block_markers_and_prepends_editor_mode(self):
        out = issue_assembly.assemble_publish(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=[],
            issue_number=349,
        )
        self.assertTrue(out.startswith("<!-- buttondown-editor-mode: plaintext -->"))
        self.assertNotIn("<!-- block:", out)
        self.assertNotIn("<!-- /block:", out)

    def test_marker_substitution(self):
        bodies = dict(SAMPLE_SECTIONS)
        bodies["notable"] = bodies["notable"] + "\n\n<!-- cta:1 -->"
        called: list[str] = []
        def sub(m):
            called.append(m.group(0))
            return "[LIQUID CTA]"
        out = issue_assembly.assemble_publish(
            atoms=SAMPLE_ATOMS, section_bodies=bodies, features=[],
            issue_number=349, marker_substitution=sub,
        )
        self.assertEqual(called, ["<!-- cta:1 -->"])
        self.assertIn("[LIQUID CTA]", out)

    def test_pixel_block_appended(self):
        pixel = "{% if medium == 'email' %}<img />{% endif %}"
        out = issue_assembly.assemble_publish(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=[],
            issue_number=349, pixel_block=pixel,
        )
        self.assertTrue(out.rstrip().endswith(pixel))

    def test_feature_section_appears_in_publish_at_correct_position(self):
        features = [("after_notable", "## Featured · Team\n\nbody")]
        out = issue_assembly.assemble_publish(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=features,
            issue_number=349,
        )
        # Notable section ends before featured, featured ends before Journal.
        notable_idx = out.find("## Notable")
        feature_idx = out.find("## Featured · Team")
        journal_idx = out.find("## Journal")
        self.assertGreater(notable_idx, 0)
        self.assertGreater(feature_idx, notable_idx)
        self.assertGreater(journal_idx, feature_idx)


if __name__ == "__main__":
    unittest.main()
