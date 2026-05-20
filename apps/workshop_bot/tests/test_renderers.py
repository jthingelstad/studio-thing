"""Byte-parity tests for the pure renderers in tools/renderers.py.

The renderers are intended to replace the existing pipeline
(build_publish.py + compose_archive.py + compose_transcript.py) with a
single set of pure functions consuming (atoms + sections + features +
metadata). For Step 1 of the migration the renderers internally
delegate to the same assembler helpers the existing jobs use, so byte
parity is by construction; these tests pin that invariant down so any
later refactor that changes output bytes surfaces immediately.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import issue_assembly, renderers  # noqa: E402


SAMPLE_ATOMS = {
    "intro": "Welcome to the issue.",
    "currently": "**Listening:** music",
    "cover": '<img src="https://x/cover.jpg" alt="cover" />\n\nA caption.',
    "outro": "Outro prose.",
    "haiku": "**line one  \nline two  \nline three**",
}


SAMPLE_SECTIONS = {
    "notable": "### [Item A](https://a.example/x)\n\nCommentary A.\n\n\n### [Item B](https://b.example/y)\n\nCommentary B.",
    "journal": "[Saturday @ 4:00 PM](https://j.example/s)\n\nStatus post.",
    "brief": "Quick take. → **[Brief A](https://ba.example/n)**",
}


SAMPLE_METADATA = {
    "number": 458,
    "buttondown_id": "em_abc",
    "subject": "Weekly Thing 458 / Test",
    "slug": "458",
    "description": "topics, more topics, even more topics.",
    "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
    "publish_date": "2026-05-16T12:00:00Z",
    "absolute_url": "https://buttondown.com/weekly-thing/archive/458/",
}


# ---------- email parity ----------


class RenderEmailParityTests(unittest.TestCase):
    """render_email_body matches assemble_publish byte-for-byte for the
    same inputs."""

    def test_basic_email_matches_assemble_publish(self):
        old = issue_assembly.assemble_publish(
            atoms=SAMPLE_ATOMS,
            section_bodies=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
            pixel_block=renderers.pixel_block(458),
            marker_substitution=None,
        )
        new = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
        )
        self.assertEqual(new, old)

    def test_email_with_cta_atoms_substitutes_to_liquid(self):
        sections_with_marker = {
            **SAMPLE_SECTIONS,
            "notable": SAMPLE_SECTIONS["notable"] + "\n\n<!-- cta:1 -->",
        }
        cta_atoms = {"cta:1": "Support the Weekly Thing this year."}
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=sections_with_marker,
            features=[],
            issue_number=458,
            cta_atoms=cta_atoms,
        )
        self.assertNotIn("<!-- cta:1 -->", out)
        self.assertIn("Support the Weekly Thing this year.", out)
        self.assertIn("{% if subscriber.subscriber_type == 'regular' %}", out)
        # Stripe buttons + subscribe form both branches present.
        self.assertIn("$4 monthly", out)
        self.assertIn("$40 yearly", out)
        self.assertIn("{{ subscribe_form }}", out)

    def test_email_with_thanks_atoms_substitutes_to_premium_only(self):
        sections_with_marker = {
            **SAMPLE_SECTIONS,
            "brief": SAMPLE_SECTIONS["brief"] + "\n\n<!-- thanks:1 -->",
        }
        cta_atoms = {"thanks:1": "Thanks for supporting this work."}
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=sections_with_marker,
            features=[],
            issue_number=458,
            cta_atoms=cta_atoms,
        )
        self.assertNotIn("<!-- thanks:1 -->", out)
        self.assertIn("Thanks for supporting this work.", out)
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", out)

    def test_email_carries_editor_mode_and_pixel(self):
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS, sections=SAMPLE_SECTIONS, features=[], issue_number=458,
        )
        self.assertTrue(out.startswith("<!-- buttondown-editor-mode: plaintext -->"))
        self.assertIn("tinylytics.app/pixel", out)
        self.assertIn("{% if medium == 'email' %}", out)

    def test_email_without_pixel_when_disabled(self):
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS, sections=SAMPLE_SECTIONS, features=[],
            issue_number=458, include_pixel=False,
        )
        self.assertNotIn("tinylytics.app/pixel", out)

    def test_features_splice_at_named_positions(self):
        features = [
            ("after_notable", "## Featured · Promoted post\n\nPromoted body."),
        ]
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=features,
            issue_number=458,
        )
        notable_idx = out.find("## Notable")
        feature_idx = out.find("## Featured · Promoted post")
        journal_idx = out.find("## Journal")
        self.assertGreater(feature_idx, notable_idx)
        self.assertLess(feature_idx, journal_idx)


class RenderEmailPreviewTests(unittest.TestCase):
    """render_email_preview matches build_publish._for_preview behavior."""

    def test_preview_strips_editor_mode_and_pixel(self):
        sections_with_marker = {
            **SAMPLE_SECTIONS,
            "notable": SAMPLE_SECTIONS["notable"] + "\n\n<!-- cta:1 -->",
        }
        full = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=sections_with_marker,
            features=[],
            issue_number=458,
            cta_atoms={"cta:1": "Supporter CTA copy."},
        )
        preview = renderers.render_email_preview(full)
        self.assertNotIn("buttondown-editor-mode", preview)
        self.assertNotIn("tinylytics.app/pixel", preview)
        # Regular subscriber branch surfaces — CTA copy + Stripe + buttons.
        self.assertIn("Supporter CTA copy.", preview)
        self.assertIn("$4 monthly", preview)
        # Leftover Liquid wrappers stripped.
        self.assertNotIn("{% if", preview)
        self.assertNotIn("{{ ", preview)


# ---------- archive parity ----------


class RenderArchiveParityTests(unittest.TestCase):
    """render_archive_body matches the body shape compose_archive
    produces from the same final.md inputs."""

    def test_archive_body_strips_block_and_cta_markers(self):
        sections_with_marker = {
            **SAMPLE_SECTIONS,
            "notable": SAMPLE_SECTIONS["notable"] + "\n\n<!-- cta:1 -->",
            "brief": SAMPLE_SECTIONS["brief"] + "\n\n<!-- thanks:1 -->",
        }
        body = renderers.render_archive_body(
            atoms=SAMPLE_ATOMS, sections=sections_with_marker, features=[],
        )
        # No block markers.
        self.assertNotIn("<!-- block:", body)
        # No cta/thanks markers.
        self.assertNotIn("<!-- cta:", body)
        self.assertNotIn("<!-- thanks:", body)
        # No editor-mode preamble.
        self.assertNotIn("buttondown-editor-mode", body)
        # No tinylytics pixel.
        self.assertNotIn("tinylytics.app/pixel", body)
        # Section headings + content survive.
        self.assertIn("## Notable", body)
        self.assertIn("Item A", body)
        self.assertIn("Item B", body)
        self.assertIn("Brief A", body)

    def test_archive_body_byte_equality_with_legacy_pipeline(self):
        """The legacy pipeline composes final.md via assemble_final,
        then compose_archive's _build_archive_body strips block markers
        + cta/thanks markers. The new render_archive_body shortcuts
        that — both should produce the same body bytes."""
        # Build final.md via the legacy assembler.
        final_md = issue_assembly.assemble_final(
            atoms=SAMPLE_ATOMS, section_bodies=SAMPLE_SECTIONS, features=[],
        )
        # Apply the legacy archive-body transform.
        legacy_body = issue_assembly._strip_block_markers(final_md)
        legacy_body = renderers._ARCHIVE_MARKER_RE.sub("\n", legacy_body)
        legacy_body = re.sub(r"\n{3,}", "\n\n", legacy_body)
        legacy_body = legacy_body.strip() + "\n"

        # New direct path.
        new_body = renderers.render_archive_body(
            atoms=SAMPLE_ATOMS, sections=SAMPLE_SECTIONS, features=[],
        )
        self.assertEqual(new_body, legacy_body)

    def test_render_archive_includes_frontmatter_and_links(self):
        archive_md, links_json = renderers.render_archive(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            metadata=SAMPLE_METADATA,
        )
        # Frontmatter present.
        self.assertTrue(archive_md.startswith("---\n"))
        self.assertIn("number: 458", archive_md)
        self.assertIn("buttondown_id: em_abc", archive_md)
        self.assertIn("subject: Weekly Thing 458 / Test", archive_md)
        # Body separator + content.
        self.assertIn("---\n", archive_md)
        self.assertIn("## Notable", archive_md)
        # Links JSON structure.
        self.assertIn("notable_links", links_json)
        self.assertIn("briefly_links", links_json)
        self.assertIn("domains", links_json)
        self.assertIn("word_count", links_json)
        # Notable + briefly links extracted from sample sections.
        self.assertEqual(len(links_json["notable_links"]), 2)
        self.assertEqual(len(links_json["briefly_links"]), 1)


# ---------- transcript ----------


class RenderTranscriptTests(unittest.TestCase):

    def test_transcript_splits_into_blocks(self):
        # Build a simple archive.md the audio pipeline can parse.
        atoms = {
            "intro": "An intro paragraph.",
            "currently": "",
            "cover": "",
            "outro": "An outro paragraph.",
            "haiku": "**line one  \nline two  \nline three**",
        }
        sections = {
            "notable": "### [Item A](https://a.example/x)\n\nCommentary A.",
            "journal": "[Saturday @ 4:00 PM](https://j.example/s)\n\nA short journal entry.",
            "brief": "A blurb. → **[B](https://b.example/x)**",
        }
        archive_md, _links = renderers.render_archive(
            atoms=atoms, sections=sections, features=[], metadata=SAMPLE_METADATA,
        )
        blocks = renderers.render_transcript_blocks(archive_md)
        self.assertGreater(len(blocks), 0)
        # Each block has a NNN-{slug}.txt filename.
        for name, content in blocks:
            self.assertRegex(name, r"^\d{3}-[a-z0-9-]+\.txt$")
            self.assertTrue(content.endswith("\n"))

    def test_transcript_raises_on_missing_frontmatter(self):
        with self.assertRaises(ValueError):
            renderers.render_transcript_blocks("body with no frontmatter")


if __name__ == "__main__":
    unittest.main()
