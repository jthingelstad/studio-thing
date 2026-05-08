"""Persona scratchpad path validation tests.

The persona-scoped S3 helpers expose write power to the agents under each
persona's private prefix. These tests pin the boundary: anything outside
``personas/{persona}/{relative}`` must be rejected before a request ever
leaves the process. Critically, a persona must never be able to resolve
to another persona's prefix.
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


from apps.workshop_bot.tools import persona_s3  # noqa: E402


class ResolveKeyTests(unittest.TestCase):
    """``_resolve_key`` is the chokepoint — every read and write goes
    through it. Testing the rejections is the whole point."""

    def test_happy_path_simple(self):
        self.assertEqual(
            persona_s3._resolve_key("marky", "campaigns/dd-2026-05-15.json"),
            "personas/marky/campaigns/dd-2026-05-15.json",
        )

    def test_happy_path_deeper(self):
        self.assertEqual(
            persona_s3._resolve_key("eddy", "notes/2026/05/observations.md"),
            "personas/eddy/notes/2026/05/observations.md",
        )

    def test_happy_path_bare_filename(self):
        self.assertEqual(
            persona_s3._resolve_key("patty", "scratch.md"),
            "personas/patty/scratch.md",
        )

    def test_rejects_traversal(self):
        for bad in ("../patty/secret.md", "campaigns/../../escape.md", "..", "../..", "x/../y.md"):
            with self.subTest(path=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key("marky", bad)

    def test_rejects_dot_component(self):
        for bad in ("./foo.md", "foo/./bar.md"):
            with self.subTest(path=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key("marky", bad)

    def test_rejects_absolute_path(self):
        for bad in ("/etc/passwd", "/abs/foo.md", "\\windows\\evil.md"):
            with self.subTest(path=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key("marky", bad)

    def test_rejects_consecutive_slashes(self):
        with self.assertRaises(persona_s3.S3PathError):
            persona_s3._resolve_key("marky", "campaigns//foo.json")

    def test_rejects_trailing_slash(self):
        with self.assertRaises(persona_s3.S3PathError):
            persona_s3._resolve_key("marky", "campaigns/")

    def test_rejects_empty_path(self):
        for bad in ("", "  ", "/"):
            with self.subTest(path=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key("marky", bad)

    def test_rejects_no_extension(self):
        with self.assertRaises(persona_s3.S3PathError):
            persona_s3._resolve_key("marky", "campaigns/Makefile")

    def test_rejects_disallowed_extension(self):
        for bad in ("payload.exe", "image.jpg", "binary.zip", "campaigns/foo.png"):
            with self.subTest(path=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key("marky", bad)

    def test_allows_each_extension(self):
        for ext in ("md", "markdown", "txt", "json", "yaml", "yml", "csv", "html"):
            with self.subTest(ext=ext):
                key = persona_s3._resolve_key("eddy", f"notes/file.{ext}")
                self.assertTrue(key.endswith(f".{ext}"))

    def test_rejects_invalid_persona(self):
        for bad in ("", "  ", "unknown", "marky/eddy", "1bad", "../etc"):
            with self.subTest(persona=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key(bad, "foo.md")

    def test_persona_normalized_to_lower(self):
        """Input is lowercased + stripped before validation — friendly defense."""
        self.assertEqual(
            persona_s3._resolve_key("MARKY", "foo.md"),
            "personas/marky/foo.md",
        )
        self.assertEqual(
            persona_s3._resolve_key("  eddy  ", "foo.md"),
            "personas/eddy/foo.md",
        )

    def test_rejects_non_string_persona(self):
        for bad in (None, 123, [], {}):
            with self.subTest(persona=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key(bad, "foo.md")  # type: ignore[arg-type]

    def test_rejects_non_string_path(self):
        for bad in (None, 123, [], {}):
            with self.subTest(path=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3._resolve_key("marky", bad)  # type: ignore[arg-type]

    def test_persona_isolation(self):
        """Marky cannot resolve to a path under Patty's prefix even by trying."""
        # The persona name is supplied by the ContextVar at the tool layer;
        # _resolve_key is honest about it. But the relative path can never
        # contain '..' to escape, and can never start with another persona name
        # in a way that escapes the {persona}/ scope.
        marky_key = persona_s3._resolve_key("marky", "patty/secret.md")
        # Marky asking for a "patty/secret.md" path lands at
        # personas/marky/patty/secret.md — under Marky's namespace, not
        # Patty's. That's the right behavior.
        self.assertTrue(marky_key.startswith("personas/marky/"))
        self.assertNotIn("personas/patty/", marky_key)


class WriteContentValidationTests(unittest.TestCase):
    """``write_persona_file`` shouldn't reach S3 with non-string or oversized content."""

    def test_non_string_rejected(self):
        with self.assertRaises(persona_s3.S3PathError):
            persona_s3.write_persona_file("marky", "campaigns/c.json", 12345)  # type: ignore[arg-type]

    def test_oversized_rejected(self):
        big = "a" * (persona_s3.WRITE_MAX_BYTES + 1)
        with self.assertRaises(persona_s3.S3PathError):
            persona_s3.write_persona_file("marky", "notes/big.md", big)


class ListPrefixValidationTests(unittest.TestCase):
    """``list_persona`` must reject ``..`` in its sub-prefix."""

    def test_rejects_traversal_in_prefix(self):
        for bad in ("../patty", "campaigns/..", ".."):
            with self.subTest(prefix=bad):
                with self.assertRaises(persona_s3.S3PathError):
                    persona_s3.list_persona("marky", prefix=bad)


if __name__ == "__main__":
    unittest.main()
