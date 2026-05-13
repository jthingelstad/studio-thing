"""Tests for jobs/_cover.py — the cover-block caption renderer
(structured ``cover.json`` preferred, legacy verbatim ``cover.md`` fallback)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _cover  # noqa: E402


class _FakeFiles:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def read_issue_file(self, issue_number, filename, **kw):
        if filename in self.files:
            return {"found": True, "text": self.files[filename], "size": len(self.files[filename])}
        return {"found": False}


class RenderCoverTests(unittest.TestCase):
    def test_json_full_renders_caption_then_date_hardbreak_location(self):
        cj = ('{"caption":"Minnehaha Creek rushing towards the Mississippi River just after the Falls.",'
              '"location":"Minneapolis, MN","timestamp":"May 10, 2026"}')
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": cj})):
            self.assertEqual(
                _cover.render(348),
                "Minnehaha Creek rushing towards the Mississippi River just after the Falls."
                "\n\nMay 10, 2026  \nMinneapolis, MN",
            )

    def test_json_partial_fields(self):
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": '{"caption":"Just a caption."}'})):
            self.assertEqual(_cover.render(1), "Just a caption.")
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": '{"timestamp":"May 1, 2026","location":"Minneapolis, MN"}'})):
            self.assertEqual(_cover.render(1), "May 1, 2026  \nMinneapolis, MN")
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": '{"caption":"Cap.","location":"Here"}'})):
            self.assertEqual(_cover.render(1), "Cap.\n\nHere")

    def test_json_takes_precedence_over_md(self):
        with patch.object(_cover, "s3", _FakeFiles({
            "cover.json": '{"caption":"json caption","location":"L","timestamp":"T"}',
            "cover.md": "the markdown one",
        })):
            self.assertEqual(_cover.render(1), "json caption\n\nT  \nL")

    def test_falls_back_to_md(self):
        with patch.object(_cover, "s3", _FakeFiles({"cover.md": "Docks on the lake.\n\nApril 26, 2026  \nExcelsior, MN"})):
            self.assertEqual(_cover.render(1), "Docks on the lake.\n\nApril 26, 2026  \nExcelsior, MN")

    def test_invalid_or_non_object_json_falls_back(self):
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": "broken {", "cover.md": "fallback"})):
            self.assertEqual(_cover.render(1), "fallback")
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": '["nope"]', "cover.md": "fallback2"})):
            self.assertEqual(_cover.render(1), "fallback2")

    def test_empty_then_empty(self):
        with patch.object(_cover, "s3", _FakeFiles({"cover.json": "{}"})):
            self.assertEqual(_cover.render(1), "")
        with patch.object(_cover, "s3", _FakeFiles({})):
            self.assertEqual(_cover.render(1), "")


if __name__ == "__main__":
    unittest.main()
