"""``send-to-buttondown`` — ship the issue: archive + transcript + audio + email + commit.

The seam where Workshop becomes the canonical source for an issue. One operator
command (``/eddy issue send``) walks the full ship sequence:

1. ``compose-archive`` — assemble the website-shaped ``archive.md`` + ``links.json``
   (writes to S3 workspace and local ``data/issues/{N}/``).
2. ``compose-transcript`` — write the per-block ``transcript/`` directory for
   audio (S3 + local).
3. ``render-audio`` — TTS each transcript block, concat with bumpers + loudnorm,
   upload MP3 to S3, update local ``data/audio/manifest.json`` with the audio_url
   + duration + byte_size for this issue.
4. **POST/PATCH ``buttondown.md`` to Buttondown** as a draft, capturing the
   freshly-minted email id and absolute_url into ``metadata.json``.
5. Re-run ``compose-archive`` so ``archive.md``'s front matter carries the
   absolute_url Buttondown returned.
6. ``github_repo.put_tree`` — single atomic commit on weekly.thingelstad.com
   ``main`` touching ``data/issues/{N}/{archive.md, metadata.json, links.json,
   transcript/NNN-*.txt}`` plus the updated ``data/audio/manifest.json``. The
   push triggers the static-site deploy.yml.
7. Success card in ``#editorial`` with the Buttondown draft link, audio URL,
   and GitHub commit URL.

A :class:`~jobs._base.ProgressMessage` shows step-by-step status in
``#editorial`` while the ship runs (the slow steps are TTS render and the
GitHub commit; the rest are sub-second). The same message gets edited in
place from ⏳ to ✅/❌ markers so Discord shows specific progress instead of
the generic "thinking..." spinner.

Order rationale: render-audio runs *before* Buttondown POST so the MP3 is
live by the time the email body (which can reference the audio URL) ships.
GitHub commit runs *after* Buttondown POST so the email is the user-visible
artifact that never gets blocked by a GitHub hiccup.

Idempotent end-to-end: re-running on the same final.md re-composes archive +
transcript (deterministic — same bytes), audio render no-ops when the script
hash matches the manifest, Buttondown PATCH hits the same draft, and
``github_repo.put_tree`` no-ops when every blob SHA already matches the tree.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from ..tools import db, github_repo, s3
from . import _base, compose_archive, compose_transcript, render_audio

logger = logging.getLogger("workshop.jobs.send_to_buttondown")

NAME = "send-to-buttondown"

REPO = Path(__file__).resolve().parents[3]
ISSUES_ROOT = REPO / "data" / "issues"
AUDIO_MANIFEST = REPO / "data" / "audio" / "manifest.json"


def _import_pipeline_content():
    """Lazy-load ``pipeline/content/content.py`` via ``sys.path``. The
    pipeline isn't a Python package (no ``__init__.py``)."""
    pipeline_content_dir = str(REPO / "pipeline" / "content")
    if pipeline_content_dir not in sys.path:
        sys.path.insert(0, pipeline_content_dir)
    import content  # noqa: F401
    return content


def _draft_url(buttondown_id: str) -> str:
    return f"https://buttondown.com/emails/{buttondown_id}"


def _collect_ship_files(issue_number: int) -> list[tuple[str, bytes]]:
    """Read every ship artifact for issue_number from the local repo and
    pair each with its repo-relative destination path. Returns the input to
    put_tree. compose-archive + compose-transcript mirror to local during
    their normal operation, and render-audio updates data/audio/manifest.json
    locally, so this can read straight from disk."""
    files: list[tuple[str, bytes]] = []
    issue_dir = ISSUES_ROOT / str(issue_number)

    archive_path = issue_dir / "archive.md"
    if not archive_path.exists():
        raise RuntimeError(
            f"archive.md is missing locally after compose-archive — refusing to ship. "
            f"Expected {archive_path}."
        )
    files.append((f"data/issues/{issue_number}/archive.md", archive_path.read_bytes()))

    metadata_path = issue_dir / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError(f"metadata.json missing at {metadata_path} — refusing to ship.")
    files.append((f"data/issues/{issue_number}/metadata.json", metadata_path.read_bytes()))

    links_path = issue_dir / "links.json"
    if links_path.exists():
        files.append((f"data/issues/{issue_number}/links.json", links_path.read_bytes()))

    # closer.md (The Closer paragraph) is optional — present
    # when compose-closer wrote one during create-final, absent when
    # compose-closer returned SKIP or hasn't run yet. The closer text is
    # already inline in archive.md / final.md / buttondown.md via the
    # assembler's splice; this commits the raw asset so editors who pull
    # the repo have the canonical paragraph as a standalone file too.
    closer_path = issue_dir / "closer.md"
    if closer_path.exists():
        files.append((f"data/issues/{issue_number}/closer.md", closer_path.read_bytes()))

    transcript_dir = issue_dir / "transcript"
    if transcript_dir.is_dir():
        for path in sorted(transcript_dir.glob("*.txt")):
            files.append((
                f"data/issues/{issue_number}/transcript/{path.name}",
                path.read_bytes(),
            ))

    # data/audio/manifest.json carries the entry render-audio just wrote
    # (audio_url / duration / byte_size / script hash / bumper hashes). The
    # site build reads this file at deploy time to inject audio_* into
    # apps/site/archive/{N}.md's front matter.
    if AUDIO_MANIFEST.exists():
        files.append(("data/audio/manifest.json", AUDIO_MANIFEST.read_bytes()))

    return files


def _initial_progress(n: int) -> str:
    return (
        f"🚀 Shipping **WT{n}**…\n"
        f"⏳ `compose-archive`\n"
        f"⏳ `compose-transcript`\n"
        f"⏳ `render-audio` _(slowest step — TTS + bumpers + S3 upload)_\n"
        f"⏳ Buttondown draft\n"
        f"⏳ GitHub commit"
    )


def _progress(
    n: int,
    *,
    archive: str = "⏳",
    archive_detail: str = "",
    transcript: str = "⏳",
    transcript_detail: str = "",
    audio: str = "⏳",
    audio_detail: str = "_(slowest step — TTS + bumpers + S3 upload)_",
    buttondown: str = "⏳",
    buttondown_detail: str = "",
    commit: str = "⏳",
    commit_detail: str = "",
    header: Optional[str] = None,
) -> str:
    head = header or f"🚀 Shipping **WT{n}**…"
    return (
        f"{head}\n"
        f"{archive} `compose-archive`{(' — ' + archive_detail) if archive_detail else ''}\n"
        f"{transcript} `compose-transcript`{(' — ' + transcript_detail) if transcript_detail else ''}\n"
        f"{audio} `render-audio`{(' ' + audio_detail) if audio_detail else ''}\n"
        f"{buttondown} Buttondown draft{(' — ' + buttondown_detail) if buttondown_detail else ''}\n"
        f"{commit} GitHub commit{(' — ' + commit_detail) if commit_detail else ''}"
    )


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — run `/eddy issue start` first.")
    n = int(window["issue_number"])

    progress = await ctx.progress(
        "DISCORD_CHANNEL_EDITORIAL", _initial_progress(n), persona="eddy"
    )

    async def _refresh(**kwargs) -> None:
        if progress is not None:
            await progress.update(_progress(n, **kwargs))

    asset = f"{n}/metadata.json"
    archive_detail = ""
    transcript_detail = ""
    audio_detail = ""
    audio_url = ""

    try:
        with _base.job_lock([asset], NAME):
            # ----- Step 1: compose-archive -----
            archive_result = await compose_archive.run(ctx)
            if not archive_result.ok:
                await _refresh(
                    header=f"❌ Ship failed for **WT{n}** at `compose-archive`",
                    archive="❌", archive_detail="see #editorial above",
                )
                return _base.JobResult(
                    False,
                    f"❌ ship blocked: compose-archive failed — {archive_result.message}",
                    data={"issue_number": n, "stage": "compose-archive"},
                )
            archive_data = archive_result.data or {}
            archive_detail = (
                f"{archive_data.get('word_count', '?')}w, "
                f"{archive_data.get('link_count', '?')} links, "
                f"{archive_data.get('domain_count', '?')} domains"
            )
            await _refresh(archive="✅", archive_detail=archive_detail)

            # ----- Step 2: compose-transcript -----
            transcript_result = await compose_transcript.run(ctx)
            if not transcript_result.ok:
                await _refresh(
                    header=f"❌ Ship failed for **WT{n}** at `compose-transcript`",
                    archive="✅", archive_detail=archive_detail,
                    transcript="❌", transcript_detail="see #editorial above",
                )
                return _base.JobResult(
                    False,
                    f"❌ ship blocked: compose-transcript failed — {transcript_result.message}",
                    data={"issue_number": n, "stage": "compose-transcript"},
                )
            transcript_data = transcript_result.data or {}
            transcript_detail = f"{transcript_data.get('block_count', '?')} blocks"
            await _refresh(
                archive="✅", archive_detail=archive_detail,
                transcript="✅", transcript_detail=transcript_detail,
            )

            # ----- Step 3: render-audio (slowest step — TTS + S3 upload) -----
            await _refresh(
                archive="✅", archive_detail=archive_detail,
                transcript="✅", transcript_detail=transcript_detail,
                audio="🎙️", audio_detail="_(rendering…)_",
            )
            audio_result = await render_audio.run(ctx)
            if not audio_result.ok:
                await _refresh(
                    header=f"❌ Ship failed for **WT{n}** at `render-audio`",
                    archive="✅", archive_detail=archive_detail,
                    transcript="✅", transcript_detail=transcript_detail,
                    audio="❌", audio_detail="see #editorial above",
                )
                return _base.JobResult(
                    False,
                    f"❌ ship blocked: render-audio failed — {audio_result.message}",
                    data={"issue_number": n, "stage": "render-audio"},
                )
            audio_data = audio_result.data or {}
            audio_url = audio_data.get("audio_url", "")
            duration_s = audio_data.get("duration_seconds")
            byte_size = audio_data.get("byte_size")
            if duration_s and byte_size:
                mb = byte_size / (1024 * 1024)
                mins, secs = divmod(int(duration_s), 60)
                audio_detail = f"{mins}:{secs:02d}, {mb:.1f}MB"
            else:
                audio_detail = "rendered" if audio_data.get("changed") else "up to date"
            await _refresh(
                archive="✅", archive_detail=archive_detail,
                transcript="✅", transcript_detail=transcript_detail,
                audio="✅", audio_detail=audio_detail,
            )

            # ----- Step 4: buttondown.md sanity + Buttondown POST/PATCH -----
            pub_res = await asyncio.to_thread(s3.read_issue_file, n, "buttondown.md")
            if not (pub_res.get("found") and isinstance(pub_res.get("text"), str) and pub_res["text"].strip()):
                msg = (
                    f"❌ `send-to-buttondown` for **WT{n}** can't run — no `buttondown.md` "
                    "in the workspace. Run `/eddy issue publish` first."
                )
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                await _refresh(
                    header=f"❌ Ship failed for **WT{n}** — `buttondown.md` missing",
                    archive="✅", archive_detail=archive_detail,
                    transcript="✅", transcript_detail=transcript_detail,
                    audio="✅", audio_detail=audio_detail,
                    buttondown="❌", buttondown_detail="no buttondown.md",
                )
                return _base.JobResult(
                    False, msg, data={"issue_number": n, "stage": "buttondown.md missing"},
                )

            pipeline_content = await asyncio.to_thread(_import_pipeline_content)
            try:
                bd_result: dict[str, Any] = await asyncio.to_thread(
                    pipeline_content.buttondown_publish_idempotent, str(n),
                )
            except pipeline_content.ButtondownPublishError as exc:
                msg = f"❌ Buttondown ship for **WT{n}** failed: {exc}"
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                await _refresh(
                    header=f"❌ Ship failed for **WT{n}** at Buttondown POST",
                    archive="✅", archive_detail=archive_detail,
                    transcript="✅", transcript_detail=transcript_detail,
                    audio="✅", audio_detail=audio_detail,
                    buttondown="❌", buttondown_detail="see #editorial above",
                )
                return _base.JobResult(
                    False, msg, data={"issue_number": n, "stage": "buttondown POST/PATCH"},
                )

            action = bd_result["action"]
            bid = bd_result["id"]
            absolute_url = bd_result.get("absolute_url", "") or ""
            buttondown_detail = f"{action} `{bid}`"
            await _refresh(
                archive="✅", archive_detail=archive_detail,
                transcript="✅", transcript_detail=transcript_detail,
                audio="✅", audio_detail=audio_detail,
                buttondown="✅", buttondown_detail=buttondown_detail,
            )

            # ----- Step 5: refresh archive.md so front matter carries absolute_url -----
            refresh_result = await compose_archive.run(ctx)
            if not refresh_result.ok:
                logger.warning(
                    "send-to-buttondown: post-ship compose-archive refresh failed for WT%d: %s",
                    n, refresh_result.message,
                )

            # ----- Step 6: github_repo.put_tree -----
            commit_url = ""
            commit_sha = ""
            try:
                files = await asyncio.to_thread(_collect_ship_files, n)
                subject = bd_result.get("subject") or f"WT{n}"
                commit_sha = await asyncio.to_thread(
                    github_repo.put_tree,
                    files,
                    f"Ship WT{n} — {subject}",
                )
                commit_url = (
                    f"https://github.com/{github_repo._repo()}/commit/{commit_sha}"
                )
                await _refresh(
                    archive="✅", archive_detail=archive_detail,
                    transcript="✅", transcript_detail=transcript_detail,
                    audio="✅", audio_detail=audio_detail,
                    buttondown="✅", buttondown_detail=buttondown_detail,
                    commit="✅", commit_detail=f"`{commit_sha[:7]}`",
                )
            except github_repo.MissingTokenError:
                await ctx.post(
                    "DISCORD_CHANNEL_EDITORIAL",
                    f"⚠️ Ship for **WT{n}** succeeded through Buttondown + audio, but "
                    "`GITHUB_PAT_TOKEN` isn't set — the website commit was skipped. "
                    "Set the env var and re-run `/eddy issue send`.",
                    persona="eddy",
                )
                await _refresh(
                    archive="✅", archive_detail=archive_detail,
                    transcript="✅", transcript_detail=transcript_detail,
                    audio="✅", audio_detail=audio_detail,
                    buttondown="✅", buttondown_detail=buttondown_detail,
                    commit="⚠️", commit_detail="GITHUB_PAT_TOKEN not set",
                )
            except Exception as exc:  # noqa: BLE001 — bound to surface, not crash the ship
                logger.exception("send-to-buttondown: GitHub commit failed for WT%d", n)
                await ctx.post(
                    "DISCORD_CHANNEL_EDITORIAL",
                    f"⚠️ Ship for **WT{n}** succeeded through Buttondown + audio, but the "
                    f"GitHub commit failed: `{exc}`. Re-run `/eddy issue send` once "
                    "the issue is resolved — every step before this one is idempotent.",
                    persona="eddy",
                )
                await _refresh(
                    archive="✅", archive_detail=archive_detail,
                    transcript="✅", transcript_detail=transcript_detail,
                    audio="✅", audio_detail=audio_detail,
                    buttondown="✅", buttondown_detail=buttondown_detail,
                    commit="⚠️", commit_detail=f"failed: {exc}",
                )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `send-to-buttondown` already running ({exc.holder_desc}).")

    # ----- Step 7: success card -----
    draft_url = _draft_url(bid)
    head_emoji = "✅" if action == "created" else "♻️"
    head_verb = "Created" if action == "created" else "Updated"
    lines = [f"{head_emoji} {head_verb} Buttondown draft for **WT{n}** — `{bd_result['subject']}`"]
    lines.append(f"📨 [open in Buttondown]({draft_url}) — review, schedule, and send when you're ready.")
    if audio_url:
        lines.append(f"🎧 [audio]({audio_url}) — {audio_detail}.")
    if commit_url:
        lines.append(f"🌐 [website commit]({commit_url}) — `{commit_sha[:7]}` on main.")
    elif commit_sha:
        lines.append(f"🌐 website commit: `{commit_sha[:7]}` on main.")
    lines.append("_Re-run `/eddy issue send` any time to push edits — every step is idempotent._")
    await ctx.post("DISCORD_CHANNEL_EDITORIAL", "\n".join(lines), persona="eddy")
    return _base.JobResult(
        True,
        f"`send-to-buttondown` for WT{n}: {action} (id=`{bid}`)"
        f"{f', commit {commit_sha[:7]}' if commit_sha else ' (no website commit)'}.",
        data={
            "issue_number": n,
            "action": action,
            "buttondown_id": bid,
            "draft_url": draft_url,
            "absolute_url": absolute_url,
            "audio_url": audio_url,
            "commit_sha": commit_sha,
            "commit_url": commit_url,
        },
    )
