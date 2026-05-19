"""Tests for pipeline/content/content.py — the workshop-as-source build path."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "pipeline" / "content"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("content", SCRIPTS / "content.py")
content = importlib.util.module_from_spec(spec)
spec.loader.exec_module(content)


def _write_canonical_issue(root: Path, number: int, *, body: str, links=None) -> None:
    """Write a complete data/issues/{N}/ trio (archive.md, metadata.json,
    links.json) under ``root``. Mirrors the shape workshop_bot's
    compose-archive job produces in S3."""
    issue_dir = root / str(number)
    issue_dir.mkdir(parents=True, exist_ok=True)
    front_matter = (
        f"buttondown_id: em_{number}\n"
        f"number: {number}\n"
        f"subject: 'Weekly Thing {number} / Test'\n"
        f"publish_date: '2026-05-{10 + number:02d}T12:00:00Z'\n"
        f"slug: '{number}'\n"
        "description: 'Test description.'\n"
        f"image: 'https://files.thingelstad.com/weekly-thing/{number}/cover.jpg'\n"
        f"absolute_url: 'https://buttondown.com/weekly-thing/archive/{number}/'\n"
        "domains: []\n"
        "links: []\n"
        "word_count: 10\n"
    )
    (issue_dir / "archive.md").write_text(f"---\n{front_matter}---\n{body}\n", encoding="utf-8")
    (issue_dir / "metadata.json").write_text(
        json.dumps({
            "number": number, "buttondown_id": f"em_{number}",
            "subject": f"Weekly Thing {number} / Test", "slug": str(number),
            "description": "Test description.",
            "image": f"https://files.thingelstad.com/weekly-thing/{number}/cover.jpg",
            "publish_date": f"2026-05-{10 + number:02d}T12:00:00Z",
            "absolute_url": f"https://buttondown.com/weekly-thing/archive/{number}/",
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (issue_dir / "links.json").write_text(
        json.dumps({
            "notable_links": links or [], "briefly_links": [],
            "domains": [], "word_count": 10,
        }, indent=2) + "\n",
        encoding="utf-8",
    )


class ParseArchiveFileTests(unittest.TestCase):
    def test_strips_current_generated_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "1.md"
            path.write_text(
                f"{content.GENERATED_NOTICE}\n"
                "---\nsubject: Weekly Thing 1\nslug: '1'\nimage: ''\n---\n"
                "Line one\n",
                encoding="utf-8",
            )
            front_matter, body = content.parse_archive_file(path)
        self.assertEqual(front_matter["subject"], "Weekly Thing 1")
        self.assertEqual(body, "Line one")

    def test_strips_legacy_generated_notices(self):
        """Old archive files (in git history) carry "from data/buttondown"; the
        parser still tolerates them so legacy tooling can re-read those bytes."""
        for legacy in content._LEGACY_NOTICES:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "1.md"
                path.write_text(
                    f"{legacy}\n"
                    "---\nsubject: Old\nslug: '1'\n---\n"
                    "Body\n",
                    encoding="utf-8",
                )
                front_matter, body = content.parse_archive_file(path)
                self.assertEqual(front_matter["subject"], "Old")
                self.assertEqual(body, "Body")


class CanonicalReadTests(unittest.TestCase):
    def test_issue_from_canonical_round_trips_front_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_canonical_issue(
                root, 42,
                body="## Notable\n\n### [Thing](http://example.com/x)\n\nA note.",
                links=[{
                    "text": "Thing", "url": "http://example.com/x",
                    "domain": "example.com",
                    "heading_context": "[Thing](http://example.com/x)",
                    "section": "Notable",
                }],
            )
            issue = content.issue_from_canonical(root / "42")
        self.assertEqual(issue["number"], 42)
        self.assertEqual(issue["id"], "em_42")
        self.assertEqual(issue["subject"], "Weekly Thing 42 / Test")
        self.assertIn("Thing", issue["body"])
        self.assertEqual(len(issue["notable_links"]), 1)

    def test_load_issues_canonical_skips_non_directory_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_canonical_issue(root, 1, body="a")
            _write_canonical_issue(root, 2, body="b")
            (root / "stray.txt").write_text("not an issue", encoding="utf-8")
            issues = content._load(root) if False else None  # placeholder to silence linter
            # use the real loader by patching ISSUES_ROOT
            orig = content.ISSUES_ROOT
            try:
                content.ISSUES_ROOT = root
                issues = content.load_issues_canonical()
            finally:
                content.ISSUES_ROOT = orig
        self.assertEqual([i["number"] for i in issues], [1, 2])


class WriteArchiveTests(unittest.TestCase):
    def test_write_archive_md_emits_full_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "archive"
            data_dir = root / "_data"
            orig_archive = content.ARCHIVE_DIR
            orig_data = content.DATA_DIR
            try:
                content.ARCHIVE_DIR = archive_dir
                content.DATA_DIR = data_dir
                issues = [{
                    "id": "em_1", "number": 1, "subject": "WT1",
                    "publish_date": "2026-01-01T12:00:00Z", "slug": "1",
                    "description": "d", "image": "", "absolute_url": "https://x",
                    "domains": [], "links": [], "word_count": 5,
                    "notable_links": [], "briefly_links": [],
                    "body": "Hello",
                }]
                content.write_archive_md(issues)
                content.write_emails_json(issues)
                written = (archive_dir / "1.md").read_text(encoding="utf-8")
            finally:
                content.ARCHIVE_DIR = orig_archive
                content.DATA_DIR = orig_data

        self.assertIn(content.GENERATED_NOTICE, written)
        self.assertIn("permalink: /archive/1/", written)
        self.assertIn("tags: issue", written)
        self.assertIn("buttondown_id: em_1", written)
        self.assertTrue(written.endswith("Hello\n"))


if __name__ == "__main__":
    unittest.main()
