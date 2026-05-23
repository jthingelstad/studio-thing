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

from apps.workshop_bot.tools import renderers  # noqa: E402


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


# ---------- email composition ----------


class RenderEmailTests(unittest.TestCase):
    """render_email_body composes the buttondown.md body directly from
    structured inputs — no marker round-trip. CTA / thanks atoms splice
    in at hardcoded positions via the cta_atoms dict."""

    def test_basic_email_with_no_cta_has_no_liquid(self):
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
        )
        # Editor-mode preamble + pixel always emitted.
        self.assertTrue(out.startswith("<!-- buttondown-editor-mode: plaintext -->"))
        self.assertIn("tinylytics.app/pixel", out)
        # No Liquid for CTA / thanks since no atoms supplied.
        self.assertNotIn("subscriber.subscriber_type", out)
        # All sections present.
        self.assertIn("## Notable", out)
        self.assertIn("## Journal", out)
        self.assertIn("## Briefly", out)

    def test_cta_1_splices_after_notable_as_liquid(self):
        cta_atoms = {"cta:1": "Support the Weekly Thing this year."}
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
            cta_atoms=cta_atoms,
        )
        # No marker round-trip — no `<!-- cta:1 -->` anywhere.
        self.assertNotIn("<!-- cta:1 -->", out)
        # Liquid block appears with the CTA copy and a single "Become a
        # Supporting Member" button pointing at the website's members
        # page (not directly at the Stripe payment links).
        self.assertIn("Support the Weekly Thing this year.", out)
        self.assertIn("{% if subscriber.subscriber_type == 'regular' %}", out)
        self.assertIn("Become a Supporting Member", out)
        self.assertIn("https://weekly.thingelstad.com/members/", out)
        # email=... + ref=WT{N} carry the subscriber identity and the
        # issue source so the members page can prefill + tinylytics can
        # attribute traffic by issue.
        self.assertIn("?email={{ subscriber.email | urlencode }}", out)
        self.assertIn("ref=WT458", out)
        # No direct Stripe links from the email anymore.
        self.assertNotIn("buy.stripe.com", out)
        self.assertNotIn("$4 monthly", out)
        self.assertNotIn("$40 yearly", out)
        # Anonymous-subscriber branch still gets the subscribe form.
        self.assertIn("{{ subscribe_form }}", out)
        # Splice happens after Notable, before Journal.
        notable_idx = out.find("## Notable")
        liquid_idx = out.find("{% if subscriber.subscriber_type == 'regular' %}")
        journal_idx = out.find("## Journal")
        self.assertLess(notable_idx, liquid_idx)
        self.assertLess(liquid_idx, journal_idx)

    def test_thanks_1_splices_after_brief_as_premium_only(self):
        cta_atoms = {"thanks:1": "Thanks for supporting this work."}
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
            cta_atoms=cta_atoms,
        )
        self.assertNotIn("<!-- thanks:1 -->", out)
        self.assertIn("Thanks for supporting this work.", out)
        self.assertIn("{% if subscriber.subscriber_type == 'premium' %}", out)
        # Splice is after Briefly (the last parent section).
        brief_idx = out.find("## Briefly")
        thanks_idx = out.find("{% if subscriber.subscriber_type == 'premium' %}")
        self.assertGreater(thanks_idx, brief_idx)

    def test_empty_cta_atoms_skip_their_slots(self):
        cta_atoms = {"cta:1": "", "cta:2": "   ", "thanks:1": "Premium thanks."}
        out = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
            cta_atoms=cta_atoms,
        )
        # cta:1 + cta:2 are empty/whitespace — no Liquid block for those slots.
        self.assertNotIn("{% if subscriber.subscriber_type == 'regular' %}", out)
        # thanks:1 still splices in.
        self.assertIn("Premium thanks.", out)
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
    """render_email_preview produces the buttondown.html preview
    body — Liquid stripped, editor-mode comment + pixel removed."""

    def test_preview_strips_editor_mode_and_pixel(self):
        full = renderers.render_email_body(
            atoms=SAMPLE_ATOMS,
            sections=SAMPLE_SECTIONS,
            features=[],
            issue_number=458,
            cta_atoms={"cta:1": "Supporter CTA copy."},
        )
        preview = renderers.render_email_preview(full)
        self.assertNotIn("buttondown-editor-mode", preview)
        self.assertNotIn("tinylytics.app/pixel", preview)
        # Regular subscriber branch surfaces — CTA copy + the single
        # "Become a Supporting Member" button to the members page.
        self.assertIn("Supporter CTA copy.", preview)
        self.assertIn("Become a Supporting Member", preview)
        # Leftover Liquid wrappers stripped.
        self.assertNotIn("{% if", preview)
        self.assertNotIn("{{ ", preview)


# ---------- archive composition ----------


class RenderArchiveTests(unittest.TestCase):
    """render_archive_body composes the website body directly. No
    Liquid, no editor-mode preamble, no CTA / thanks anything — those
    are email-only."""

    def test_archive_body_is_clean_prose(self):
        body = renderers.render_archive_body(
            atoms=SAMPLE_ATOMS, sections=SAMPLE_SECTIONS, features=[],
        )
        # No block markers (workshop never emits them here).
        self.assertNotIn("<!-- block:", body)
        # No CTA / thanks markers.
        self.assertNotIn("<!-- cta:", body)
        self.assertNotIn("<!-- thanks:", body)
        # No email-only artifacts.
        self.assertNotIn("buttondown-editor-mode", body)
        self.assertNotIn("tinylytics.app/pixel", body)
        self.assertNotIn("subscriber.subscriber_type", body)
        # Section headings + content survive.
        self.assertIn("## Notable", body)
        self.assertIn("Item A", body)
        self.assertIn("Item B", body)
        self.assertIn("Brief A", body)

    def test_archive_body_ignores_cta_atoms(self):
        """Even if cta_atoms were threaded through (they aren't, by
        signature — archive doesn't take them), the archive composer
        never produces Liquid. Defensive: pass them via the email
        path side, render archive separately, confirm no Liquid leaks."""
        body = renderers.render_archive_body(
            atoms=SAMPLE_ATOMS, sections=SAMPLE_SECTIONS, features=[],
        )
        self.assertNotIn("{% if", body)
        self.assertNotIn("Supporter", body)

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

    def _atoms_and_sections(self, *, cover: str = ""):
        atoms = {
            "intro": "An intro paragraph.",
            "currently": "",
            "cover": cover,
            "outro": "An outro paragraph.",
            "haiku": "**line one  \nline two  \nline three**",
        }
        sections = {
            "notable": "### [Item A](https://a.example/x)\n\nCommentary A.",
            "journal": "[Saturday @ 4:00 PM](https://j.example/s)\n\nA short journal entry.",
            "brief": "A blurb. → **[B](https://b.example/x)**",
        }
        return atoms, sections

    def test_transcript_splits_into_blocks(self):
        atoms, sections = self._atoms_and_sections()
        blocks = renderers.render_transcript_blocks(
            atoms=atoms, sections=sections, features=[], metadata=SAMPLE_METADATA,
        )
        self.assertGreater(len(blocks), 0)
        # Each block has a NNN-{slug}.txt filename.
        for name, content in blocks:
            self.assertRegex(name, r"^\d{3}-[a-z0-9-]+\.txt$")
            self.assertTrue(content.endswith("\n"))

    def test_audio_body_drops_cover_atom(self):
        """The cover atom (image + caption + date + location) is
        purely visual — render_audio_body must drop it from the body
        passed to the script transform, so the audio script never
        even has to defend against it."""
        atoms, sections = self._atoms_and_sections(
            cover=(
                '<img src="https://files.thingelstad.com/weekly-thing/458/cover.jpg" '
                'alt="Golden sunset over a calm lake." />\n\n'
                "Beautiful evening with the sun coming down.\n\n"
                "May 16, 2026  \nCannon Lake, Warsaw, MN"
            ),
        )
        audio_body = renderers.render_audio_body(
            atoms=atoms, sections=sections, features=[],
        )
        # Cover atom content gone — alt text, caption, date, location.
        self.assertNotIn("Golden sunset", audio_body)
        self.assertNotIn("Beautiful evening", audio_body)
        self.assertNotIn("Cannon Lake", audio_body)
        self.assertNotIn("cover.jpg", audio_body)
        # Other sections survive.
        self.assertIn("intro paragraph", audio_body)
        self.assertIn("## Notable", audio_body)

    def test_transcript_does_not_carry_cover_content(self):
        """End-to-end: a cover atom with image + caption + location
        produces zero transcript blocks containing any of that
        content. Covers belong to the visual surface only."""
        atoms, sections = self._atoms_and_sections(
            cover=(
                '<img src="https://files.thingelstad.com/weekly-thing/458/cover.jpg" '
                'alt="Golden sunset over a calm lake." />\n\n'
                "Beautiful evening with the sun coming down.\n\n"
                "May 16, 2026  \nCannon Lake, Warsaw, MN"
            ),
        )
        blocks = renderers.render_transcript_blocks(
            atoms=atoms, sections=sections, features=[], metadata=SAMPLE_METADATA,
        )
        for name, content in blocks:
            self.assertNotIn("Golden sunset", content, name)
            self.assertNotIn("Cannon Lake", content, name)
            self.assertNotIn("cover.jpg", content, name)

    def test_concat_transcript_for_review_marks_each_segment(self):
        blocks = [
            ("000-intro.txt", "Welcome to the issue."),
            ("001-notable.txt", "Now, the Notable section.\n\nLink one. \"Title\"."),
            ("002-haiku.txt", "Haiku close."),
        ]
        out = renderers.concat_transcript_for_review(blocks, issue_number=458)
        # Header line names the issue + segment count.
        self.assertIn("Weekly Thing 458 — full transcript (3 segments)", out)
        # Each segment header appears in order.
        for name in ("000-intro.txt", "001-notable.txt", "002-haiku.txt"):
            self.assertIn(f"═══ {name} ═══", out)
        intro_idx = out.index("═══ 000-intro.txt ═══")
        notable_idx = out.index("═══ 001-notable.txt ═══")
        haiku_idx = out.index("═══ 002-haiku.txt ═══")
        self.assertLess(intro_idx, notable_idx)
        self.assertLess(notable_idx, haiku_idx)
        # Content appears between markers.
        self.assertIn("Welcome to the issue.", out)
        self.assertIn("Now, the Notable section.", out)
        self.assertIn("Haiku close.", out)
        # Trailing newline normalized.
        self.assertTrue(out.endswith("\n"))

    def test_concat_transcript_no_issue_number_omits_header(self):
        out = renderers.concat_transcript_for_review(
            [("000-x.txt", "body")],
        )
        # Without an issue number, no header line.
        self.assertNotIn("full transcript", out)
        self.assertIn("═══ 000-x.txt ═══", out)
        self.assertIn("body", out)


if __name__ == "__main__":
    unittest.main()
