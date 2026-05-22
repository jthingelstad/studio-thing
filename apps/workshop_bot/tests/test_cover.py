"""Tests for jobs/_cover.py — the cover-block caption renderer
(structured ``cover.json`` preferred, legacy verbatim ``cover.md`` fallback)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _cover  # noqa: E402
from apps.workshop_bot.tools import alt_text  # noqa: E402


class _FakeFiles:
    def __init__(self, files: dict[str, str]):
        self.files = files
        self.writes: list[tuple[int, str, str]] = []

    def read_issue_file(self, issue_number, filename, **kw):
        if filename in self.files:
            return {"found": True, "text": self.files[filename], "size": len(self.files[filename])}
        return {"found": False}

    def write_issue_file(self, issue_number, filename, content, **kw):
        self.writes.append((issue_number, filename, content))
        self.files[filename] = content
        return {"key": filename, "bucket": "test", "url": f"s3://test/{filename}", "size": len(content)}


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


class AltCoverTests(unittest.TestCase):
    """``_cover.alt`` — cover.json.alt is the source of truth; vision
    fills + writes back when missing."""

    def setUp(self):
        # Fresh per-run cap each test so the cover vision call has budget.
        alt_text.begin_run()

    def test_returns_manual_alt_without_vision_call(self):
        cj = json.dumps({"caption": "A creek.", "alt": "operator-supplied"})
        fake = _FakeFiles({"cover.json": cj})
        vision = MagicMock()
        with patch.object(_cover, "s3", fake), \
             patch.object(alt_text, "generate_alt", vision):
            self.assertEqual(_cover.alt(458), "operator-supplied")
        vision.assert_not_called()
        # And no write-back when nothing changed.
        self.assertEqual(fake.writes, [])

    def test_generates_and_writes_back_to_cover_json(self):
        cj = json.dumps({"caption": "A creek.", "location": "MPLS", "timestamp": "May 10"})
        fake = _FakeFiles({"cover.json": cj})
        vision = MagicMock(return_value="Water tumbling over basalt below the falls")
        with patch.object(_cover, "s3", fake), \
             patch.object(alt_text, "generate_alt", vision):
            self.assertEqual(_cover.alt(458), "Water tumbling over basalt below the falls")
        # Vision call got the caption (and not the alt, which didn't exist).
        vision.assert_called_once()
        _, kwargs = vision.call_args
        self.assertEqual(kwargs["caption"], "A creek.")
        self.assertEqual(kwargs["image_url"], "https://files.thingelstad.com/weekly-thing/458/cover.jpg")
        # Wrote the updated cover.json back to S3.
        self.assertEqual(len(fake.writes), 1)
        issue, filename, content = fake.writes[0]
        self.assertEqual((issue, filename), (458, "cover.json"))
        round_trip = json.loads(content)
        self.assertEqual(round_trip["alt"], "Water tumbling over basalt below the falls")
        # Original fields preserved.
        self.assertEqual(round_trip["caption"], "A creek.")
        self.assertEqual(round_trip["location"], "MPLS")
        self.assertEqual(round_trip["timestamp"], "May 10")

    def test_returns_empty_when_no_cover_json(self):
        fake = _FakeFiles({})  # neither cover.json nor cover.md
        vision = MagicMock()
        with patch.object(_cover, "s3", fake), \
             patch.object(alt_text, "generate_alt", vision):
            self.assertEqual(_cover.alt(1), "")
        vision.assert_not_called()
        self.assertEqual(fake.writes, [])

    def test_returns_empty_when_vision_returns_empty(self):
        # Cap exhausted / image fetch failed / vision empty — all surface
        # as "". We should NOT write back the empty.
        fake = _FakeFiles({"cover.json": '{"caption":"x"}'})
        with patch.object(_cover, "s3", fake), \
             patch.object(alt_text, "generate_alt", return_value=""):
            self.assertEqual(_cover.alt(1), "")
        self.assertEqual(fake.writes, [])

    def test_returns_alt_even_when_writeback_fails(self):
        # Best-effort persistence — if the S3 write blows up, the current
        # render still gets the alt; the next run will retry generation.
        cj = json.dumps({"caption": "x"})
        fake = _FakeFiles({"cover.json": cj})
        fake.write_issue_file = MagicMock(side_effect=RuntimeError("S3 boom"))
        with patch.object(_cover, "s3", fake), \
             patch.object(alt_text, "generate_alt", return_value="a fresh alt"):
            self.assertEqual(_cover.alt(1), "a fresh alt")


if __name__ == "__main__":
    unittest.main()
