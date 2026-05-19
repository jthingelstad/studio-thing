"""``send-to-buttondown`` — ship the issue: email draft + website commit + transcript.

The seam where Workshop becomes the canonical source for an issue. One operator
command (``/eddy issue send``) walks the full ship sequence:

1. ``compose-archive`` — assemble the website-shaped ``archive.md`` + ``links.json``.
2. ``compose-transcript`` — write the per-block ``transcript/`` directory for
   audio. (Idempotent: deterministic projection from ``archive.md``.)
3. **POST/PATCH ``buttondown.md`` to Buttondown** as a draft, capturing the
   freshly-minted email id and absolute_url into ``metadata.json``.
4. Re-run ``compose-archive`` so ``archive.md``'s front matter carries the
   absolute_url Buttondown returned (no-op on re-ships where it was already set).
5. ``github_repo.put_tree`` — single atomic commit on weekly.thingelstad.com
   ``main`` touching ``data/issues/{N}/{archive.md, metadata.json, links.json,
   transcript/NNN-*.txt}``. The push triggers the existing deploy.yml.
6. Success card in ``#editorial`` with both the Buttondown draft link and the
   GitHub commit URL.

Order rationale: Buttondown first, GitHub second. The email is the
user-visible artifact; if the GitHub commit fails, the email already went and
a re-run of ``/eddy issue send`` completes the website update idempotently.
Reverse order would risk a website update without an email going out.

Idempotent: re-running with no changes does no Buttondown re-create (PATCH
hits the same draft) and ``github_repo.put_tree`` is a no-op when every blob
SHA already matches the tree.

Refuses if any prerequisite is missing — the failure surface threads through
``compose-archive``'s missing-list (``final.md`` / ``haiku.md`` / ``metadata.json``
/ ``intro.md`` / ``cover.jpg``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ..tools import db, github_repo, s3
from . import _base, compose_archive, compose_transcript

logger = logging.getLogger("workshop.jobs.send_to_buttondown")

NAME = "send-to-buttondown"


def _import_pipeline_content():
    """Lazy-load ``pipeline/content/content.py`` via ``sys.path``. The
    pipeline isn't a Python package (no ``__init__.py``)."""
    repo = Path(__file__).resolve().parents[3]
    pipeline_content_dir = str(repo / "pipeline" / "content")
    if pipeline_content_dir not in sys.path:
        sys.path.insert(0, pipeline_content_dir)
    import content  # noqa: F401
    return content


def _draft_url(buttondown_id: str) -> str:
    return f"https://buttondown.com/emails/{buttondown_id}"


def _read(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    return ""


def _collect_ship_files(issue_number: int) -> list[tuple[str, bytes]]:
    """Read every ship artifact for issue_number from S3 and pair each with
    its repo-relative destination path. Returns the input to put_tree."""
    files: list[tuple[str, bytes]] = []

    archive_md = _read(issue_number, "archive.md")
    if not archive_md.strip():
        raise RuntimeError("archive.md is missing or empty after compose-archive — refusing to ship.")
    files.append((f"data/issues/{issue_number}/archive.md", archive_md.encode("utf-8")))

    metadata_json = _read(issue_number, "metadata.json")
    if not metadata_json.strip():
        raise RuntimeError("metadata.json is missing or empty — refusing to ship.")
    files.append((f"data/issues/{issue_number}/metadata.json", metadata_json.encode("utf-8")))

    links_json = _read(issue_number, "links.json")
    if links_json.strip():
        files.append((f"data/issues/{issue_number}/links.json", links_json.encode("utf-8")))

    # transcript/ is optional — Workshop-shipped issues should always have it
    # after compose-transcript, but a defensive empty-list check keeps a
    # transcript-less issue from blocking the ship (audio falls through to
    # the legacy transform on the website side).
    try:
        transcript_basenames = s3.list_transcript_files(issue_number)
    except Exception:  # noqa: BLE001
        transcript_basenames = []
    for basename in sorted(transcript_basenames):
        content = _read(issue_number, f"transcript/{basename}")
        if not content.strip():
            continue
        files.append((
            f"data/issues/{issue_number}/transcript/{basename}",
            content.encode("utf-8"),
        ))

    return files


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — run `/eddy issue start` first.")
    n = int(window["issue_number"])

    asset = f"{n}/metadata.json"
    try:
        with _base.job_lock([asset], NAME):
            # ----- Step 1: compose-archive -----
            archive_result = await compose_archive.run(ctx)
            if not archive_result.ok:
                # compose_archive already posted its missing-list to #editorial.
                return _base.JobResult(
                    False,
                    f"❌ ship blocked: compose-archive failed — {archive_result.message}",
                    data={"issue_number": n, "stage": "compose-archive"},
                )

            # ----- Step 2: compose-transcript -----
            transcript_result = await compose_transcript.run(ctx)
            if not transcript_result.ok:
                return _base.JobResult(
                    False,
                    f"❌ ship blocked: compose-transcript failed — {transcript_result.message}",
                    data={"issue_number": n, "stage": "compose-transcript"},
                )

            # ----- Step 3: buttondown.md sanity + Buttondown POST/PATCH -----
            pub_res = await asyncio.to_thread(s3.read_issue_file, n, "buttondown.md")
            if not (pub_res.get("found") and isinstance(pub_res.get("text"), str) and pub_res["text"].strip()):
                msg = (
                    f"❌ `send-to-buttondown` for **WT{n}** can't run — no `buttondown.md` "
                    "in the workspace. Run `/eddy issue publish` first."
                )
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
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
                return _base.JobResult(
                    False, msg, data={"issue_number": n, "stage": "buttondown POST/PATCH"},
                )

            action = bd_result["action"]
            bid = bd_result["id"]
            absolute_url = bd_result.get("absolute_url", "") or ""

            # ----- Step 4: refresh archive.md so front matter carries absolute_url -----
            # buttondown_publish_idempotent persisted absolute_url to metadata.json;
            # re-running compose-archive rebuilds archive.md with the field present.
            # On a re-ship where absolute_url was already there, this is a no-op
            # (identical bytes).
            refresh_result = await compose_archive.run(ctx)
            if not refresh_result.ok:
                # Email already went out — surface the refresh failure but
                # don't fail the ship.
                logger.warning(
                    "send-to-buttondown: post-ship compose-archive refresh failed for WT%d: %s",
                    n, refresh_result.message,
                )

            # ----- Step 5: github_repo.put_tree -----
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
            except github_repo.MissingTokenError:
                await ctx.post(
                    "DISCORD_CHANNEL_EDITORIAL",
                    f"⚠️ Buttondown ship for **WT{n}** succeeded, but `GITHUB_PAT_TOKEN` "
                    "isn't set — the website commit was skipped. Set the env var and re-run "
                    "`/eddy issue send` to commit the archive files.",
                    persona="eddy",
                )
            except Exception as exc:  # noqa: BLE001 — bound to surface, not crash the ship
                logger.exception("send-to-buttondown: GitHub commit failed for WT%d", n)
                await ctx.post(
                    "DISCORD_CHANNEL_EDITORIAL",
                    f"⚠️ Buttondown ship for **WT{n}** succeeded, but the GitHub commit "
                    f"failed: `{exc}`. Re-run `/eddy issue send` once the issue is "
                    "resolved — it's idempotent on the Buttondown side.",
                    persona="eddy",
                )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `send-to-buttondown` already running ({exc.holder_desc}).")

    # ----- Step 6: success card -----
    draft_url = _draft_url(bid)
    head_emoji = "✅" if action == "created" else "♻️"
    head_verb = "Created" if action == "created" else "Updated"
    lines = [f"{head_emoji} {head_verb} Buttondown draft for **WT{n}** — `{bd_result['subject']}`"]
    lines.append(f"📨 [open in Buttondown]({draft_url}) — review, schedule, and send when you're ready.")
    if commit_url:
        lines.append(f"🌐 [website commit]({commit_url}) — `{commit_sha[:7]}` on main.")
    elif commit_sha:
        lines.append(f"🌐 website commit: `{commit_sha[:7]}` on main.")
    lines.append("_Re-run `/eddy issue send` any time to push edits — Buttondown PATCH + GitHub re-commit are both idempotent._")
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
            "commit_sha": commit_sha,
            "commit_url": commit_url,
        },
    )
