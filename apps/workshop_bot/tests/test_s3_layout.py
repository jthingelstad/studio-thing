"""S3 key layout — flat issue-root keys, subdir prefixes preserved in
listings. (The ``atoms/`` routing + dual-source read layer was retired with
the DB-is-the-draft rip: authored content never touches S3 anymore.)"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools import s3  # noqa: E402


class ResolveKeyTests(unittest.TestCase):
    def test_all_names_resolve_flat_at_issue_root(self):
        for name in (
            "intro.md",
            "haiku.md",
            "archive.md",
            "buttondown.md",
            "metadata.json",
            "cta-1.md",
        ):
            self.assertEqual(s3._resolve_key(458, name), f"weekly-thing/458/{name}", name)

    def test_rejects_bad_issue_number(self):
        with self.assertRaises(s3.S3PathError):
            s3._resolve_key(0, "intro.md")


class ListIssueTests(unittest.TestCase):
    """list_issue reports keys relative to the issue prefix; subdir names
    (``journal/``, ``transcript/``, legacy ``atoms/``) keep their prefix."""

    def setUp(self):
        self._listing: list[dict] = []
        fake_client = MagicMock()

        def fake_list(Bucket, Prefix, MaxKeys, ContinuationToken=None):  # noqa: N803
            return {
                "Contents": [
                    {
                        "Key": item["Key"],
                        "Size": item.get("Size", 0),
                        "LastModified": None,
                        "ETag": item.get("ETag", ""),
                    }
                    for item in self._listing
                ],
                "IsTruncated": False,
            }

        fake_client.list_objects_v2 = fake_list
        self._client_patch = patch.object(s3, "_client", return_value=fake_client)
        self._client_patch.start()

    def tearDown(self):
        self._client_patch.stop()

    def test_subdir_keys_keep_their_prefix(self):
        self._listing = [
            {"Key": "weekly-thing/458/journal/abc.jpg"},
            {"Key": "weekly-thing/458/transcript/000-intro.txt"},
            {"Key": "weekly-thing/458/atoms/intro.md"},  # legacy leftover
            {"Key": "weekly-thing/458/archive.md"},
        ]
        out = s3.list_issue(458)
        filenames = {obj["filename"] for obj in out["objects"]}
        self.assertEqual(
            filenames,
            {"journal/abc.jpg", "transcript/000-intro.txt", "atoms/intro.md", "archive.md"},
        )


if __name__ == "__main__":
    unittest.main()
