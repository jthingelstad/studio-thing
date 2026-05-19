"""Shared fixtures for content-jobs tests.

Extracted from ``test_content_jobs.py`` so split-out test files (e.g.
``test_pinboard_scan.py``) can import the same in-memory S3 workspace
and the same temp-DB base class without each file duplicating the
boilerplate.

What's here:

- :class:`FakeWorkspace` — an in-memory replacement for the per-issue
  S3 surface (``s3.read_issue_file`` / ``write_issue_file`` /
  ``write_issue_html`` / ``write_workshop_pointer`` / ``list_issue``).
- :func:`patch_s3(ws)` — returns a list of ``unittest.mock.patch.object``
  patchers to start; each test case starts them in ``setUp`` and stops
  in ``tearDown``.
- :class:`DBTestCase` — base class that opens a temp-dir SQLite, runs
  migrations, sets up a fresh ``FakeWorkspace`` + patches, and tears
  everything down.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from apps.workshop_bot.jobs import _base
from apps.workshop_bot.tools import db, s3


class FakeWorkspace:
    """In-memory replacement for ``apps.workshop_bot.tools.s3``'s per-issue
    surface. Each test case constructs a fresh one in ``setUp``; reads /
    writes go through ``self.files`` (keyed by ``(issue_number, filename)``)
    and ``self.workshop_pointer`` (a single dict)."""

    def __init__(self) -> None:
        self.files: dict[tuple[int, str], str] = {}
        self.workshop_pointer: dict | None = None

    def read_issue_file(self, issue_number, filename, *, max_bytes=None):
        key = (int(issue_number), filename)
        if key in self.files:
            return {"key": f"weekly-thing/{issue_number}/{filename}", "found": True,
                    "text": self.files[key], "size": len(self.files[key])}
        return {"key": f"weekly-thing/{issue_number}/{filename}", "found": False}

    def write_issue_file(self, issue_number, filename, content, *, content_type=None, cache_control=None):
        self.files[(int(issue_number), filename)] = content
        return {"key": f"weekly-thing/{issue_number}/{filename}", "written": True,
                "size": len(content), "url": f"https://files.thingelstad.com/weekly-thing/{issue_number}/{filename}"}

    def write_issue_html(self, issue_number, filename, html_text):
        # No CloudFront invalidation in tests.
        return self.write_issue_file(issue_number, filename, html_text)

    def write_workshop_pointer(self, data):
        self.workshop_pointer = data
        return {"key": "weekly-thing/workshop.json", "bucket": "files.thingelstad.com",
                "url": "https://files.thingelstad.com/weekly-thing/workshop.json",
                "size": len(str(data)), "written": True}

    def list_issue(self, issue_number):
        n = int(issue_number)
        objs = [{"filename": fn, "key": f"weekly-thing/{n}/{fn}", "size": len(txt)}
                for (i, fn), txt in self.files.items() if i == n]
        return {"bucket": "files.thingelstad.com", "issue_number": n,
                "prefix": f"weekly-thing/{n}/", "objects": objs}

    def delete_issue_file(self, issue_number, filename):
        key = (int(issue_number), filename)
        self.files.pop(key, None)
        return {"key": f"weekly-thing/{issue_number}/{filename}", "deleted": True}

    # Per-block transcript files live under {N}/transcript/{basename} on S3.
    # In the fake workspace we model them with the same self.files dict using
    # the prefixed key, so list_issue() naturally surfaces them.

    def write_transcript_file(self, issue_number, basename, content):
        key = (int(issue_number), f"transcript/{basename}")
        self.files[key] = content
        return {
            "key": f"weekly-thing/{issue_number}/transcript/{basename}",
            "bucket": "files.thingelstad.com",
            "url": f"https://files.thingelstad.com/weekly-thing/{issue_number}/transcript/{basename}",
            "size": len(content), "written": True,
        }

    def delete_transcript_file(self, issue_number, basename):
        self.files.pop((int(issue_number), f"transcript/{basename}"), None)
        return {
            "key": f"weekly-thing/{issue_number}/transcript/{basename}",
            "deleted": True,
        }

    def list_transcript_files(self, issue_number):
        n = int(issue_number)
        prefix = "transcript/"
        return [
            fn[len(prefix):]
            for (i, fn) in self.files
            if i == n and fn.startswith(prefix)
        ]


def patch_s3(ws: FakeWorkspace):
    """Build the list of patchers that redirect the per-issue ``s3``
    surface to ``ws``. Caller starts/stops them in setUp/tearDown."""
    return [
        patch.object(s3, "read_issue_file", ws.read_issue_file),
        patch.object(s3, "write_issue_file", ws.write_issue_file),
        patch.object(s3, "write_issue_html", ws.write_issue_html),
        patch.object(s3, "write_workshop_pointer", ws.write_workshop_pointer),
        patch.object(s3, "list_issue", ws.list_issue),
        patch.object(s3, "delete_issue_file", ws.delete_issue_file),
        patch.object(s3, "write_transcript_file", ws.write_transcript_file),
        patch.object(s3, "delete_transcript_file", ws.delete_transcript_file),
        patch.object(s3, "list_transcript_files", ws.list_transcript_files),
    ]


class DBTestCase(unittest.TestCase):
    """Temp-DB + FakeWorkspace test base. Opens a temp-dir SQLite,
    points ``WORKSHOP_DB_PATH`` at it, runs migrations, installs the
    in-memory S3 patches, and tears it all down."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmpdir.name) / "test.db")
        db.run_migrations()
        self.ws = FakeWorkspace()
        self._patches = patch_s3(self.ws)
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        if self._orig_db is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig_db
        self._tmpdir.cleanup()


def filled_final(
    *,
    notable: str = "### [A](http://a)\n\nx",
    brief: str = "A blurb. → **[B](http://b)**",
    journal: str = "[Tuesday @ 3:02 PM](https://x.example/p)\n\nt",
    intro: str = "",
    currently: str = "",
    cover: str = "",
    outro: str = "",
    haiku: str = "",
) -> str:
    """Build a starter-template-shaped final.md with the three required
    blocks filled. Atoms (intro / currently / cover / outro / haiku)
    default to empty — pass them explicitly when a test needs them to
    appear in the assembled output.

    In the row-backed model, ``final.md`` carries the atoms inlined
    (the assembler reads them from their files at create-final time
    and bakes them in); this fixture mirrors that shape so tests can
    feed a single ``final.md`` text and exercise the build-publish
    transform without re-doing the create-final assembly path."""
    d = _base.starter_template()
    d = _base.replace_block(d, "notable", notable)
    d = _base.replace_block(d, "brief", brief)
    d = _base.replace_block(d, "journal", journal)
    if intro:
        d = _base.replace_block(d, "intro", intro)
    if currently:
        d = _base.replace_block(d, "currently", currently)
    if cover:
        d = _base.replace_block(d, "cover", cover)
    if outro:
        d = _base.replace_block(d, "outro", outro)
    if haiku:
        d = _base.replace_block(d, "haiku", haiku)
    return d


class FakeBotChannel:
    """A persona bot + a channel, enough for the compose / build-publish
    interactive jobs that need a ``bot.core`` mock + a ``channel.send``
    mock. ``deps()`` returns a ``Deps``-ish stub with ``.team.bots[<persona>]``
    pointing at this bot."""

    def __init__(self, persona: str = "eddy", reply: str = '{"options": []}') -> None:
        self.persona = persona
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.bot = MagicMock()
        self.bot.user = object()
        self.bot.get_channel = MagicMock(return_value=self.channel)
        self.bot.core = AsyncMock(return_value=(reply, {"iterations": 1}))

    def deps(self):
        team = MagicMock()
        team.bots = {self.persona: self.bot}
        d = MagicMock()
        d.team = team
        return d
