"""``compose-transcript`` — write per-block TTS prose files for the audio pipeline.

The audio sibling of ``compose-archive``. Reads the issue's ``archive.md`` from
S3, runs the same prose-rendering pipeline ``pipeline/audio/script/modern.py``
uses, then splits the rendered script at its natural semantic boundaries (the
``split_into_blocks`` boundaries — preamble, section intros, link cues,
journal-entry cues, quote blocks, closing) and writes each block as its own
file under ``s3://files.thingelstad.com/weekly-thing/{N}/transcript/NNN-{slug}.txt``.

Why per-block files: the audio pipeline TTSes each file as its own utterance
when this directory exists, so the natural breath placement falls at the
editorial block boundaries instead of arbitrary MAX_CHARS packing seams.
Small issues that would have packed into one TTS chunk no longer get read flat.

Pure Python, no LLM. Wipes and regenerates the ``transcript/`` directory on
each run — idempotent on identical ``archive.md`` + metadata. Refuses (PASSes
loudly) if ``archive.md`` isn't in the workspace (run ``/eddy issue archive``
first, or just rely on the auto-fire from ``send-to-buttondown``).
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import yaml

from ..tools import s3
from . import _base

logger = logging.getLogger("workshop.jobs.compose_transcript")

NAME = "compose-transcript"

REPO = Path(__file__).resolve().parents[3]

# Per-block writes carry a slug derived from the block's first line, capped so
# S3 keys stay sane. Pure-text fallback when the slug derivation can't extract
# anything meaningful.
_MAX_SLUG_LEN = 40
_SLUG_FALLBACK = "block"


def _import_audio_helpers():
    """Reach into the audio pipeline for the script-rendering primitives.
    pipeline/audio/ isn't a proper package — its files use ``from script import …``
    so we add it to sys.path on demand rather than restructuring the audio tree."""
    audio_dir = REPO / "pipeline" / "audio"
    if str(audio_dir) not in sys.path:
        sys.path.insert(0, str(audio_dir))
    from script import body_to_audio_script  # noqa: E402
    from synthesize import split_into_blocks  # noqa: E402

    return body_to_audio_script, split_into_blocks


def _read(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    return ""


def _parse_archive_frontmatter(archive_md: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.+?)\n---\n(.*)$", archive_md, re.DOTALL)
    if not m:
        raise ValueError("archive.md is missing YAML front matter")
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, m.group(2)


def _slugify(line: str) -> str:
    """Build a stable filename slug from a block's first line. Examples:
    - "Now, the Notable section." → "now-the-notable-section"
    - "Link one. \"OpenAI's Codex App\"" → "link-one-openais-codex-app"
    - "Quote." → "quote"
    """
    text = line.strip().lower()
    text = re.sub(r"[\"']", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if not text:
        return _SLUG_FALLBACK
    return text[:_MAX_SLUG_LEN].rstrip("-")


def _block_filenames(blocks: list[str]) -> list[tuple[str, str]]:
    """Pair each block with its zero-padded filename. NNN prefix preserves
    order on filesystem-sorted reads; slug is descriptive but not load-bearing."""
    out: list[tuple[str, str]] = []
    for index, block in enumerate(blocks):
        first_line = block.splitlines()[0] if block else ""
        slug = _slugify(first_line)
        out.append((f"{index:03d}-{slug}.txt", block))
    return out


def _list_existing_transcript_basenames(issue_number: int) -> list[str]:
    try:
        return s3.list_transcript_files(issue_number)
    except Exception:  # noqa: BLE001
        return []


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    """Build the transcript/ directory of per-block files for the in-flight issue."""
    from ..tools import db

    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — run `/eddy issue start` first."
        )
    n = int(window["issue_number"])

    asset = f"{n}/transcript/"
    try:
        with _base.job_lock([asset], NAME):
            archive_raw = _read(n, "archive.md")
            if not archive_raw.strip():
                msg = (
                    f"⛔ `compose-transcript` for **WT{n}** can't run — "
                    "no `archive.md` in the workspace. Run `/eddy issue send` "
                    "(or `compose-archive` if running stand-alone) first."
                )
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n})

            try:
                fm, body = _parse_archive_frontmatter(archive_raw)
            except ValueError as exc:
                msg = f"⛔ `compose-transcript` for **WT{n}** can't parse `archive.md`: {exc}"
                return _base.JobResult(False, msg, data={"issue_number": n})

            body_to_audio_script, split_into_blocks = _import_audio_helpers()
            script = body_to_audio_script(body, fm)
            blocks = split_into_blocks(script)
            if not blocks:
                return _base.JobResult(
                    False,
                    f"❌ `compose-transcript` produced zero blocks for WT{n}; check archive.md content.",
                    data={"issue_number": n},
                )

            named = _block_filenames(blocks)

            # Wipe stale transcript files so a re-run with fewer blocks doesn't
            # leave orphans behind. Only delete from the transcript/ prefix.
            new_names = {name for name, _ in named}
            for existing in _list_existing_transcript_basenames(n):
                if existing not in new_names:
                    try:
                        s3.delete_transcript_file(n, existing)
                    except Exception:  # noqa: BLE001
                        logger.warning("compose-transcript: couldn't delete stale %s", existing)

            for name, block in named:
                s3.write_transcript_file(n, name, block.rstrip() + "\n")

    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `compose-transcript` is already running ({exc.holder_desc})."
        )

    return _base.JobResult(
        True,
        f"transcript/ written for #{n} ({len(named)} block(s)).",
        data={
            "issue_number": n,
            "block_count": len(named),
            "filenames": [name for name, _ in named],
        },
    )
