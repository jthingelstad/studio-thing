"""``render-audio`` — TTS + bumpers + loudnorm for the in-flight issue.

Workshop_bot side of audio rendering. The ship sequence calls this between
compose-transcript and the Buttondown POST so the MP3 is live at its public
URL by the time Jamie sees the success card — no "wait for CI before
scheduling Buttondown" caveat.

Reads transcripts from ``data/issues/{N}/transcript/`` (compose-transcript
mirrors them there). Wraps ``pipeline/audio/audio.build_issue`` so the
underlying TTS / chunking / S3 upload / manifest update logic stays in one
place; the workshop side only orchestrates.

Idempotent: ``build_issue``'s ``body_is_up_to_date`` / ``final_is_up_to_date``
gates skip the render when the transcript hash matches the manifest and the
S3 MP3 is intact. Re-running a ship is silent on the audio side too.

Note on ``apps/site/archive/{N}.md``: ``build_issue`` reads it for the
ID3 metadata + cover image URL. For a freshly-shipped issue that file
doesn't exist yet, so this job runs ``pipeline/content/content.py build``
first to materialize it (without ``audio_url`` — that gets injected the
next time the build runs after this job updates the manifest).
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.render_audio")

NAME = "render-audio"

REPO = Path(__file__).resolve().parents[3]
AUDIO_MANIFEST = REPO / "data" / "audio" / "manifest.json"
TRANSCRIPT_DIR_TPL = REPO / "data" / "issues"
ARCHIVE_DIR = REPO / "apps" / "site" / "archive"


def _import_audio_pipeline():
    """Lazy-load pipeline/audio/ — not a Python package, so we add it to
    sys.path on demand rather than restructuring the audio tree."""
    audio_dir = REPO / "pipeline" / "audio"
    if str(audio_dir) not in sys.path:
        sys.path.insert(0, str(audio_dir))
    import audio  # noqa: F401
    import bumpers  # noqa: F401
    import manifest  # noqa: F401

    return audio, bumpers, manifest


def _materialize_apps_site_archive(issue_number: int) -> None:
    """Run ``pipeline/content/content.py build`` so the canonical
    apps/site/archive/{N}.md exists for the audio pipeline's frontmatter
    read. Builds the full archive (fast — sub-second for 349 issues)."""
    subprocess.run(
        [sys.executable, str(REPO / "pipeline" / "content" / "content.py"), "build"],
        check=True,
        cwd=REPO,
        capture_output=True,
    )


def _ensure_bumpers(bumpers_mod, manifest: dict) -> bool:
    """build_issue refuses if intro/outro bumper MP3s are missing. Render
    them on demand — deterministic text-keyed renders, so this is a no-op
    if they already exist and the text + voice match the manifest's
    ``_bumpers`` block.

    ``manifest`` is the audio manifest (mutated in place when a bumper
    actually re-renders so ``set_bumper_state`` can stamp the new hash).
    Returns True if anything was rendered."""
    return bool(bumpers_mod.ensure_bumpers(manifest))


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — run `/eddy issue start` first."
        )
    n = int(window["issue_number"])

    transcript_dir = TRANSCRIPT_DIR_TPL / str(n) / "transcript"
    if not transcript_dir.is_dir() or not any(transcript_dir.glob("*.txt")):
        msg = (
            f"⛔ `render-audio` for **WT{n}** can't run — no per-block transcripts "
            f"under `{transcript_dir.relative_to(REPO)}`. Run `compose-transcript` first."
        )
        await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
        return _base.JobResult(False, msg, data={"issue_number": n})

    asset = "data/audio/manifest.json"
    try:
        with _base.job_lock([asset], NAME):
            audio_mod, bumpers_mod, manifest_mod = _import_audio_pipeline()

            # Make sure apps/site/archive/{N}.md exists for the ID3 + cover lookup.
            _materialize_apps_site_archive(n)

            # Read the manifest first — ensure_bumpers needs it (it stamps
            # the bumper hash + voice into manifest["_bumpers"]) and so
            # does build_issue. One read, one write at the end picks up
            # both mutations.
            manifest_data = manifest_mod.read_manifest()
            _ensure_bumpers(bumpers_mod, manifest_data)

            # build_issue mutates manifest_data in place with the new entry;
            # we write it back so the workshop ship's GitHub commit picks up
            # the change.
            changed = audio_mod.build_issue(
                str(n),
                manifest_data,
                dry_run=False,
                force=False,
                reassemble_only=False,
            )
            manifest_mod.write_manifest(manifest_data)

            entry = manifest_data.get(str(n), {})

    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `render-audio` is already running ({exc.holder_desc})."
        )
    except Exception as exc:  # noqa: BLE001 — surface the error rather than crash the ship
        logger.exception("render-audio failed for WT%d", n)
        msg = f"❌ `render-audio` for **WT{n}** failed: `{exc}`"
        await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
        return _base.JobResult(False, msg, data={"issue_number": n})

    audio_url = entry.get("audio_url", "")
    duration_s = entry.get("audio_duration_seconds")
    byte_size = entry.get("audio_byte_size")
    action = "rendered" if changed else "already up to date"

    return _base.JobResult(
        True,
        f"audio {action} for #{n}"
        + (f" — {duration_s}s, {byte_size}B" if duration_s and byte_size else ""),
        data={
            "issue_number": n,
            "audio_url": audio_url,
            "duration_seconds": duration_s,
            "byte_size": byte_size,
            "changed": changed,
        },
    )
