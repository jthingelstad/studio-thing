"""S3 path validation tests.

The S3 helpers expose write power to the agents. These tests pin the
boundary: anything outside ``weekly-thing/issues/{N}/<filename>`` must
be rejected before a request ever leaves the process.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _install_stubs() -> None:
    if "discord" not in sys.modules:
        discord = types.ModuleType("discord")

        class _Client:
            def __init__(self, *a, **k):
                self.user = None

        class _Intents:
            message_content = False
            guilds = False

            @staticmethod
            def default():
                return _Intents()

        discord.Client = _Client  # type: ignore[attr-defined]
        discord.Intents = _Intents  # type: ignore[attr-defined]
        discord.Message = object  # type: ignore[attr-defined]
        discord.DiscordException = Exception  # type: ignore[attr-defined]
        abc_mod = types.ModuleType("discord.abc")
        abc_mod.Messageable = object  # type: ignore[attr-defined]
        sys.modules["discord"] = discord
        sys.modules["discord.abc"] = abc_mod

    if "anthropic" not in sys.modules:
        anthropic = types.ModuleType("anthropic")

        class _A:
            def __init__(self, *a, **k):
                pass

        anthropic.Anthropic = _A  # type: ignore[attr-defined]
        sys.modules["anthropic"] = anthropic


_install_stubs()


from apps.workshop_bot.tools import s3  # noqa: E402


class ResolveKeyTests(unittest.TestCase):
    """``_resolve_key`` is the chokepoint — every read and write goes
    through it. Testing the rejections is the whole point."""

    def test_happy_path(self):
        self.assertEqual(
            s3._resolve_key(347, "draft.md"),
            "weekly-thing/issues/347/draft.md",
        )

    def test_rejects_path_traversal(self):
        for bad in ("../escape.txt", "..%2F", "../../etc/passwd"):
            with self.subTest(filename=bad):
                with self.assertRaises(s3.S3PathError):
                    s3._resolve_key(347, bad)

    def test_rejects_slashes(self):
        for bad in ("foo/bar.md", "/abs.md", "a\\b.md"):
            with self.subTest(filename=bad):
                with self.assertRaises(s3.S3PathError):
                    s3._resolve_key(347, bad)

    def test_rejects_empty_or_dotfile(self):
        for bad in ("", ".env", ".hiddencrap"):
            with self.subTest(filename=bad):
                with self.assertRaises(s3.S3PathError):
                    s3._resolve_key(347, bad)

    def test_rejects_disallowed_extension(self):
        for bad in ("payload.exe", "image.jpg", "binary.zip"):
            with self.subTest(filename=bad):
                with self.assertRaises(s3.S3PathError):
                    s3._resolve_key(347, bad)

    def test_rejects_bad_issue_number(self):
        for bad in (0, -1, "347", None, 3.14):
            with self.subTest(issue=bad):
                with self.assertRaises(s3.S3PathError):
                    s3._resolve_key(bad, "draft.md")  # type: ignore[arg-type]

    def test_allows_each_extension(self):
        for ext in ("md", "markdown", "txt", "json", "yaml", "yml", "csv", "html"):
            with self.subTest(ext=ext):
                key = s3._resolve_key(1, f"file.{ext}")
                self.assertTrue(key.endswith(f".{ext}"))


class WriteContentValidationTests(unittest.TestCase):
    """``write_issue_file`` shouldn't reach S3 with non-string or oversized content."""

    def test_non_string_rejected(self):
        with self.assertRaises(s3.S3PathError):
            s3.write_issue_file(347, "metadata.json", 12345)  # type: ignore[arg-type]

    def test_oversized_rejected(self):
        big = "a" * (s3.WRITE_MAX_BYTES + 1)
        with self.assertRaises(s3.S3PathError):
            s3.write_issue_file(347, "draft.md", big)


if __name__ == "__main__":
    unittest.main()
