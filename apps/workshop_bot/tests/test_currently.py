"""Tests for jobs/_currently.py — the ``## Currently`` section renderer
(structured ``currently.json`` preferred, legacy verbatim ``currently.md``
fallback)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _currently  # noqa: E402


class _FakeFiles:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def read_issue_file(self, issue_number, filename, **kw):
        if filename in self.files:
            return {"found": True, "text": self.files[filename], "size": len(self.files[filename])}
        return {"found": False}


def _files(**files):
    return patch.object(_currently, "s3", _FakeFiles(files))


class RenderCurrentlyTests(unittest.TestCase):
    def test_json_object_renders_label_value_lines(self):
        cj = ('{"Listening":" The new Noah Kahan album.",'
              '"Watching":" Shrinking on Apple TV.",'
              '"Printing":" Clash Royale crowns."}')
        with patch.object(_currently, "s3", _FakeFiles({"currently.json": cj})):
            out = _currently.render(348)
        self.assertEqual(
            out,
            "**Listening:** The new Noah Kahan album.\n\n"
            "**Watching:** Shrinking on Apple TV.\n\n"
            "**Printing:** Clash Royale crowns.",
        )

    def test_json_strips_trailing_colon_and_skips_blanks(self):
        cj = '{"Reading:": " A book.", "Eating": "  ", "": "ignored", "Playing": "Tetris"}'
        with patch.object(_currently, "s3", _FakeFiles({"currently.json": cj})):
            self.assertEqual(_currently.render(1), "**Reading:** A book.\n\n**Playing:** Tetris")

    def test_json_takes_precedence_over_md(self):
        with patch.object(_currently, "s3", _FakeFiles({
            "currently.json": '{"Reading":"the JSON one"}',
            "currently.md": "**Reading:** the markdown one",
        })):
            self.assertEqual(_currently.render(1), "**Reading:** the JSON one")

    def test_falls_back_to_md_when_no_json(self):
        with patch.object(_currently, "s3", _FakeFiles({"currently.md": "**Watching:** a verbatim section"})):
            self.assertEqual(_currently.render(1), "**Watching:** a verbatim section")

    def test_invalid_or_non_object_json_falls_back_to_md(self):
        with patch.object(_currently, "s3", _FakeFiles({"currently.json": "not json {", "currently.md": "fallback md"})):
            self.assertEqual(_currently.render(1), "fallback md")
        with patch.object(_currently, "s3", _FakeFiles({"currently.json": '["a","list"]', "currently.md": "fallback md 2"})):
            self.assertEqual(_currently.render(1), "fallback md 2")

    def test_empty_then_empty(self):
        with patch.object(_currently, "s3", _FakeFiles({"currently.json": "{}"})):
            self.assertEqual(_currently.render(1), "")
        with patch.object(_currently, "s3", _FakeFiles({})):
            self.assertEqual(_currently.render(1), "")

    def test_md_is_stripped(self):
        with patch.object(_currently, "s3", _FakeFiles({"currently.md": "\n\n  trimmed  \n"})):
            self.assertEqual(_currently.render(1), "trimmed")


if __name__ == "__main__":
    unittest.main()
