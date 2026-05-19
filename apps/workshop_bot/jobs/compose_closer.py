"""``compose-closer`` — write the "From the Archive" closing paragraph.

Auto-fired by ``create-final`` after Jamie's ✅ on the proposal, before
``final.md`` gets assembled (so the closer ends up inline in
``final.md`` → flows through to ``buttondown.md`` / ``archive.md`` /
``transcript/`` naturally).

Anthropic Sonnet call (not Thingy — Thingy's API is Q&A-only and we
need arbitrary generation here; the framing "From the Archive" lives
in this prompt, not in Thingy's persona). Inputs:

- The current issue draft (final.md → fallback draft.md), so Sonnet
  can pick an archive entry that genuinely resonates with this issue's
  themes.
- The bodies of the last 6 issues' closers (read from
  ``data/issues/{N-6..N-1}/closer.md`` on local disk; skipped silently
  if missing), so Sonnet can avoid repeating an archive entry or theme
  it picked recently.
- An archive inventory — every prior issue's number + subject +
  publish date, read from ``apps/site/_data/emails.json`` — so Sonnet
  has a grounded set of issues to reference by number.

Output is either:
- A 2-to-4-sentence markdown paragraph → written to ``closer.md`` in
  S3 + local ``data/issues/{N}/``.
- The literal string ``SKIP`` → nothing written; create-final
  assembles ``final.md`` without a "From the Archive" section.

Idempotent: re-running on the same issue regenerates the closer (Sonnet
may produce different output). To preserve a specific closer, edit
``data/issues/{N}/closer.md`` directly after this job runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from ..tools import db, s3
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_closer")

NAME = "compose-closer"

REPO = Path(__file__).resolve().parents[3]
ISSUES_ROOT = REPO / "data" / "issues"
EMAILS_JSON = REPO / "apps" / "site" / "_data" / "emails.json"

# Max past closers to pull for anti-repetition. Six covers a comfortable
# "recent history" window without bloating the prompt.
_PRIOR_CLOSER_COUNT = 6

# Max archive entries to surface to Sonnet. The full archive is ~350
# issues; we hand it the whole inventory (number + subject + date) so
# the model has the lookup table inline rather than guessing from training.
_ARCHIVE_INVENTORY_CAP = 500


def _prior_closers(issue_number: int) -> list[tuple[int, str]]:
    """Read up to ``_PRIOR_CLOSER_COUNT`` previous issues' closer bodies
    from the local ``data/issues/{N-k}/closer.md`` files. Returns
    ``[(issue_number, closer_text), …]`` newest-first. Issues without a
    closer.md (most of the back catalog — this is a new section) are
    silently skipped."""
    out: list[tuple[int, str]] = []
    n = int(issue_number)
    for offset in range(1, _PRIOR_CLOSER_COUNT + 1):
        prev = n - offset
        if prev < 1:
            break
        path = ISSUES_ROOT / str(prev) / "closer.md"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            out.append((prev, text))
    return out


def _archive_inventory() -> list[dict[str, Any]]:
    """Load the lightweight issue index from apps/site/_data/emails.json.
    Each entry has at minimum ``number``, ``subject``, ``publish_date``."""
    if not EMAILS_JSON.exists():
        return []
    try:
        data = json.loads(EMAILS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if "number" not in entry:
            continue
        out.append({
            "number": entry.get("number"),
            "subject": (entry.get("subject") or "").strip(),
            "publish_date": (entry.get("publish_date") or "")[:10],  # YYYY-MM-DD only
        })
    return out[:_ARCHIVE_INVENTORY_CAP]


def _format_prior_closers(prior: list[tuple[int, str]]) -> str:
    if not prior:
        return "_(none — this is one of the first issues with a closer.)_"
    parts: list[str] = []
    for num, text in prior:
        parts.append(f"**WT{num}:** {text}")
    return "\n\n".join(parts)


def _format_archive_inventory(rows: list[dict[str, Any]], current_number: int) -> str:
    """One line per issue: ``#NNN — YYYY-MM-DD — Subject``. Sorted by
    number descending (newest first) so the most relevant context for
    "what came before" is at the top of the list."""
    lines: list[str] = []
    sorted_rows = sorted(
        (r for r in rows if isinstance(r.get("number"), int) and r["number"] < current_number),
        key=lambda r: r["number"],
        reverse=True,
    )
    for r in sorted_rows:
        lines.append(f"- #{r['number']} — {r['publish_date']} — {r['subject']}")
    return "\n".join(lines) if lines else "_(no prior issues in inventory)_"


def _build_user_message(
    *,
    issue_number: int,
    publish_date: str,
    baseline_body: str,
    prior: list[tuple[int, str]],
    archive_rows: list[dict[str, Any]],
) -> str:
    return (
        f"You're writing the closer for **The Weekly Thing #{issue_number}**, "
        f"publishing {publish_date}.\n\n"
        f"---\n\n"
        f"## Current issue draft\n\n"
        f"```markdown\n{baseline_body.strip()}\n```\n\n"
        f"---\n\n"
        f"## Past {len(prior)} closer(s) (do not reuse themes or entries from these)\n\n"
        f"{_format_prior_closers(prior)}\n\n"
        f"---\n\n"
        f"## Archive inventory (every prior issue — reference by #N)\n\n"
        f"{_format_archive_inventory(archive_rows, issue_number)}\n\n"
        f"---\n\n"
        f"Output: 2-4 sentences of markdown prose, OR the literal string `SKIP`. "
        f"Nothing else."
    )


def _is_skip(reply: str) -> bool:
    """Tolerant SKIP detection — caps-insensitive, whitespace-stripped,
    accepts trailing punctuation. Anything else (including empty) is
    treated as not-a-skip so the caller can write whatever was returned
    and Jamie can spot a bad reply in #editorial."""
    if not reply:
        return False
    stripped = reply.strip().strip("`'\"").rstrip(".!").strip().lower()
    return stripped == "skip"


def _clean_closer(reply: str) -> str:
    """Strip surrounding whitespace + accidental code-fence wrappers; return
    the closer paragraph as it should land in closer.md."""
    text = (reply or "").strip()
    if text.startswith("```"):
        # Strip the first/last code-fence lines if present.
        lines = text.splitlines()
        if lines and lines[0].lstrip("`").strip().lower() in ("", "markdown", "md"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


async def run(
    ctx: "_base.JobContext",
    *,
    baseline_body: Optional[str] = None,
) -> "_base.JobResult":
    """Generate (or skip) the From-the-Archive closer for the in-flight
    issue. ``baseline_body``, if supplied, is the just-assembled body
    create-final uses internally before it adds the closer; otherwise
    we fall back to reading final.md or draft.md from S3."""
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — run `/eddy issue start` first.",
        )
    n = int(window["issue_number"])
    publish_date = (window.get("pub_date") or "")[:10] or "(unknown date)"

    if baseline_body is None:
        baseline_body = await asyncio.to_thread(_llm_job.final_or_draft, n)
    if not baseline_body or not baseline_body.strip():
        return _base.JobResult(
            False, f"❌ no body available for WT{n} — run `/eddy issue final` or `/eddy issue update` first.",
        )

    bot, channel, reason = _llm_job.resolve_bot_and_channel(
        ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL",
    )
    if bot is None:
        return _base.JobResult(
            True, f"(compose-closer skipped — {reason})",
            data={"skipped": False, "closer_written": False},
        )

    asset = f"{n}/closer.md"
    try:
        with _base.job_lock([asset], NAME):
            try:
                base_prompt = anthropic_client.load_prompt("eddy-compose-closer")
            except OSError as exc:
                logger.warning("compose-closer: prompt missing: %s", exc)
                return _base.JobResult(
                    False, f"❌ compose-closer prompt missing: `{exc}`",
                )

            prior = await asyncio.to_thread(_prior_closers, n)
            archive_rows = await asyncio.to_thread(_archive_inventory)
            user_body = _build_user_message(
                issue_number=n,
                publish_date=publish_date,
                baseline_body=baseline_body[: _llm_job.ISSUE_BODY_CAP],
                prior=prior,
                archive_rows=archive_rows,
            )
            user_msg = f"{base_prompt}\n\n---\n\n{user_body}"[: _llm_job.CREATE_FINAL_BODY_CAP]

            with db.AgentRun("eddy", trigger="compose-closer") as agent_run:
                reply, meta = await bot.core(latest=user_msg, history=[], model="sonnet")
                agent_run.record_meta(meta)
                agent_run.records_written = 1 if reply else 0

            if not reply or not reply.strip():
                msg = f"❌ compose-closer for WT{n}: empty reply from Eddy."
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n})

            if _is_skip(reply):
                # Don't write closer.md — create-final's assembler will
                # render final.md without a "From the Archive" section.
                # Also clean up any prior closer.md so the issue's
                # current state reflects the SKIP.
                try:
                    s3.delete_issue_file(n, "closer.md")
                except Exception:  # noqa: BLE001 — closer.md may not exist
                    pass
                local_closer = ISSUES_ROOT / str(n) / "closer.md"
                if local_closer.exists():
                    try:
                        local_closer.unlink()
                    except OSError:
                        pass
                msg = f"📭 compose-closer for **WT{n}**: SKIP (no archive resonance this issue)."
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(
                    True, msg, data={"issue_number": n, "skipped": True, "closer_written": False},
                )

            text = _clean_closer(reply)
            if not text:
                msg = f"❌ compose-closer for WT{n}: reply was empty after cleanup."
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n})

            # Write to S3 workspace + mirror locally (the create-final +
            # ship paths read from local).
            s3.write_issue_file(n, "closer.md", text + "\n")
            local_dir = ISSUES_ROOT / str(n)
            local_dir.mkdir(parents=True, exist_ok=True)
            (local_dir / "closer.md").write_text(text + "\n", encoding="utf-8")
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `compose-closer` already running ({exc.holder_desc}).",
        )

    word_count = len(text.split())
    msg = (
        f"📚 compose-closer for **WT{n}**: {word_count}-word From the Archive paragraph written.\n"
        f"> {text}"
    )
    await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
    return _base.JobResult(
        True,
        f"compose-closer for WT{n}: written ({word_count} words).",
        data={
            "issue_number": n, "skipped": False, "closer_written": True,
            "closer": text, "word_count": word_count,
        },
    )
