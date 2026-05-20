"""S3 layout migration — atoms/ subdir routing + dual-read fallback.

Step 2 of the pipeline refactor moves author-content atoms under
``weekly-thing/{N}/atoms/`` while generated artifacts + immovable
images/audio stay at the issue root. These tests pin the routing,
dual-read, and listing-collapse behavior.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import s3  # noqa: E402


class AtomNameDetectionTests(unittest.TestCase):

    def test_known_atoms(self):
        for name in ("intro.md", "outro.md", "cover.json", "haiku.md",
                     "metadata.json", "thesis.md"):
            self.assertTrue(s3._is_atom_name(name), name)

    def test_numbered_cta_thanks(self):
        for name in ("cta-1.md", "cta-2.md", "thanks-1.md", "thanks-3.md"):
            self.assertTrue(s3._is_atom_name(name), name)

    def test_generated_artifacts_are_not_atoms(self):
        for name in ("draft.md", "draft.html", "final.md", "archive.md",
                     "links.json", "buttondown.md", "buttondown.html",
                     "proposal.html"):
            self.assertFalse(s3._is_atom_name(name), name)

    def test_images_audio_are_not_atoms(self):
        for name in ("cover.jpg", "cover-large.jpg", "weekly-thing-100.mp3"):
            self.assertFalse(s3._is_atom_name(name), name)


class ResolveKeyRoutingTests(unittest.TestCase):

    def test_atoms_route_to_atoms_subdir(self):
        self.assertEqual(
            s3._resolve_key(458, "intro.md"),
            "weekly-thing/458/atoms/intro.md",
        )
        self.assertEqual(
            s3._resolve_key(458, "haiku.md"),
            "weekly-thing/458/atoms/haiku.md",
        )
        self.assertEqual(
            s3._resolve_key(458, "cta-2.md"),
            "weekly-thing/458/atoms/cta-2.md",
        )

    def test_non_atoms_stay_at_root(self):
        self.assertEqual(
            s3._resolve_key(458, "draft.md"),
            "weekly-thing/458/draft.md",
        )
        self.assertEqual(
            s3._resolve_key(458, "archive.md"),
            "weekly-thing/458/archive.md",
        )
        self.assertEqual(
            s3._resolve_key(458, "buttondown.md"),
            "weekly-thing/458/buttondown.md",
        )
        self.assertEqual(
            s3._resolve_key(458, "links.json"),
            "weekly-thing/458/links.json",
        )

    def test_legacy_key_for_atoms_is_root_path(self):
        self.assertEqual(
            s3._resolve_legacy_key(458, "intro.md"),
            "weekly-thing/458/intro.md",
        )
        self.assertEqual(
            s3._resolve_legacy_key(458, "haiku.md"),
            "weekly-thing/458/haiku.md",
        )

    def test_invalid_filename_still_rejected(self):
        for bad in ("../etc/passwd", "atoms/intro.md", "intro/extra.md", ""):
            with self.assertRaises(s3.S3PathError):
                s3._resolve_key(458, bad)


class ReadDualSourceTests(unittest.TestCase):
    """The dual-read behavior of read_issue_file is mocked at the boto
    client layer — the unit test exercises the resolution + fallback
    logic without an S3 round trip."""

    def setUp(self):
        # Patch the boto client used inside read_issue_file with a fake
        # that records key lookups and serves from an in-memory map.
        self._calls: list[str] = []
        self._objects: dict[str, bytes] = {}
        from unittest.mock import patch, MagicMock

        class FakeNoSuchKey(Exception):
            pass

        fake_client = MagicMock()
        fake_client.exceptions.NoSuchKey = FakeNoSuchKey

        def fake_get(Bucket, Key):  # noqa: N803 — mirrors boto's kwargs
            self._calls.append(Key)
            if Key not in self._objects:
                raise FakeNoSuchKey(f"no key {Key}")
            body = self._objects[Key]
            stream = MagicMock()
            stream.read = lambda n: body[:n]
            return {
                "Body": stream,
                "ContentLength": len(body),
                "ContentType": "text/markdown",
                "LastModified": None,
            }

        fake_client.get_object = fake_get
        self._client_patch = patch.object(s3, "_client", return_value=fake_client)
        self._client_patch.start()

    def tearDown(self):
        self._client_patch.stop()

    def test_reads_from_atoms_subdir_when_present(self):
        self._objects["weekly-thing/458/atoms/intro.md"] = b"hello"
        out = s3.read_issue_file(458, "intro.md")
        self.assertTrue(out["found"])
        self.assertEqual(out["text"], "hello")
        self.assertEqual(self._calls, ["weekly-thing/458/atoms/intro.md"])

    def test_falls_back_to_root_for_atoms(self):
        # Atom only present at the legacy root path.
        self._objects["weekly-thing/458/intro.md"] = b"legacy"
        out = s3.read_issue_file(458, "intro.md")
        self.assertTrue(out["found"])
        self.assertEqual(out["text"], "legacy")
        # Both paths attempted, in order.
        self.assertEqual(
            self._calls,
            ["weekly-thing/458/atoms/intro.md", "weekly-thing/458/intro.md"],
        )

    def test_no_fallback_for_non_atoms(self):
        # archive.md isn't an atom — only one key tried.
        out = s3.read_issue_file(458, "archive.md")
        self.assertFalse(out["found"])
        self.assertEqual(self._calls, ["weekly-thing/458/archive.md"])

    def test_atom_missing_at_both_paths_returns_not_found(self):
        out = s3.read_issue_file(458, "intro.md")
        self.assertFalse(out["found"])
        self.assertEqual(
            self._calls,
            ["weekly-thing/458/atoms/intro.md", "weekly-thing/458/intro.md"],
        )


class ListIssueCollapseTests(unittest.TestCase):
    """list_issue collapses the ``atoms/`` prefix in the returned
    filename so callers' "is X in files" checks keep working with bare
    filenames."""

    def setUp(self):
        from unittest.mock import patch, MagicMock

        self._listing: list[dict] = []
        fake_client = MagicMock()

        def fake_list(Bucket, Prefix, MaxKeys, ContinuationToken=None):  # noqa: N803
            return {
                "Contents": [
                    {"Key": item["Key"], "Size": item.get("Size", 0),
                     "LastModified": None, "ETag": item.get("ETag", "")}
                    for item in self._listing
                ],
                "IsTruncated": False,
            }

        fake_client.list_objects_v2 = fake_list
        self._client_patch = patch.object(s3, "_client", return_value=fake_client)
        self._client_patch.start()

    def tearDown(self):
        self._client_patch.stop()

    def test_atom_keys_collapse_to_bare_filename(self):
        self._listing = [
            {"Key": "weekly-thing/458/atoms/intro.md"},
            {"Key": "weekly-thing/458/atoms/haiku.md"},
            {"Key": "weekly-thing/458/draft.md"},
            {"Key": "weekly-thing/458/archive.md"},
        ]
        out = s3.list_issue(458)
        filenames = {obj["filename"] for obj in out["objects"]}
        self.assertEqual(
            filenames, {"intro.md", "haiku.md", "draft.md", "archive.md"},
        )

    def test_journal_and_transcript_keep_their_prefix(self):
        self._listing = [
            {"Key": "weekly-thing/458/journal/abc.jpg"},
            {"Key": "weekly-thing/458/transcript/000-intro.txt"},
            {"Key": "weekly-thing/458/atoms/intro.md"},
        ]
        out = s3.list_issue(458)
        filenames = {obj["filename"] for obj in out["objects"]}
        self.assertEqual(
            filenames,
            {"journal/abc.jpg", "transcript/000-intro.txt", "intro.md"},
        )


if __name__ == "__main__":
    unittest.main()
