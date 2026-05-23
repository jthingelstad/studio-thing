"""``compose-closer`` — write **Echoes**, Thingy's archive note.

(Internal name stays ``compose-closer`` / ``closer.md``; the reader-facing
section heading is **Echoes**.) Echoes is the section that closes every issue: Thingy (the public
librarian persona — see ``prompts/shared/thingy-voice-reference.md``)
writes a 2–4 sentence note connecting the current issue to the
nine-year archive. The note runs in Thingy's voice (third-person about
Jamie), not Jamie's voice — that's the deliberate handoff at the bottom
of every issue.

Auto-fired by ``create-final`` after Jamie's ✅ on the proposal, before
``final.md`` gets assembled (so the closer ends up inline in
``final.md`` → flows through to ``buttondown.md`` / ``archive.md`` /
``transcript/`` naturally).

The job offers Thingy **two candidate sets** in the prompt — she picks
one mode based on whichever has the stronger signal:

- **Mode 1 — Thematic Resonance** (preferred when the connection is
  real). Top-K archive passages retrieved via Thingy's own ``/retrieve``
  endpoint (Bedrock Cohere embed → vector search → Cohere rerank
  against the pre-embedded corpus). Sourced through
  ``tools/thingy_retrieve.py``. This is Thingy-grade semantic
  retrieval, not the in-process BM25 corpus the other agents use, and
  the quality bar for The Closer is built around it.
- **Mode 2 — Anniversary Echo** (always-available fallback). For each
  offset in ``_ANNIVERSARY_OFFSETS`` (one, five, eight years back), the
  job finds the issue published nearest to that date in
  ``apps/site/_data/emails.json`` and pulls a ~1500-char body preview
  from ``data/issues/{N}/archive.md``. The prompt asks Thingy to pull a
  specific detail from one of these issues.

Inputs to the Sonnet call:

- The current issue draft (final.md → fallback draft.md).
- The bodies of the last 6 closers (``data/issues/{N-k}/closer.md``,
  newest-first; silently skipped if missing) — anti-repetition.
- Semantic snippets (Mode 1 candidates).
- Anniversary candidates (Mode 2 candidates).

Output is either:

- A 2-to-4-sentence markdown paragraph (≈40–80 words) in **Thingy's
  voice** (third-person about Jamie), with the referenced issue(s)
  rendered as markdown links (``[WT###](https://weekly.thingelstad.
  com/archive/N/)``) → written to ``closer.md`` in S3 + local
  ``data/issues/{N}/``. The prompt asks the model to include the
  links; we also post-process to linkify any bare ``WT N`` / ``Weekly
  Thing N`` references it slipped past the prompt.
- A SKIP line (``SKIP — no strong archive connection this week.``)
  → nothing written; create-final assembles ``final.md`` without a
  The Closer section.

Fails loud on retrieval failure (Lambda unreachable, secret missing,
non-2xx) — degrading silently to inventory-only or BM25 would defeat
the quality bar this job is built around. Anniversary candidates alone
(without semantic snippets) is not considered an acceptable fallback —
Mode 1 is the higher-quality mode and we don't want to silently force
Mode 2 by hiding a retrieval failure.

Idempotent: re-running on the same issue regenerates the closer (the
model may produce different output). To preserve a specific closer,
edit ``data/issues/{N}/closer.md`` directly after this job runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..tools import db, s3, thingy_retrieve
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_closer")

NAME = "compose-closer"

REPO = Path(__file__).resolve().parents[3]
ISSUES_ROOT = REPO / "data" / "issues"

# Used by _anniversary_candidates() to look up issue numbers + dates.
EMAILS_JSON = REPO / "apps" / "site" / "_data" / "emails.json"

# Public archive URL — used to convert "Weekly Thing N" references in the
# closer body into clickable markdown links.
_ARCHIVE_URL_TPL = "https://weekly.thingelstad.com/archive/{n}/"

# Max past closers to pull for anti-repetition. Six covers a comfortable
# "recent history" window without bloating the prompt.
_PRIOR_CLOSER_COUNT = 6

# How many passages to retrieve from Thingy. 20 gives Sonnet a thick
# pool to pick from (≈ 6 distinct issues represented on average; the
# rerank inside Thingy biases hard toward the best matches at the top),
# while staying under Thingy's internal `numberOfResults` ceiling and
# keeping the prompt at a manageable ~10–15 KB after preview-cap.
_ARCHIVE_SNIPPET_COUNT = 20
# Per-passage body cap. The Lambda already trims to ~1200 chars in
# compactSource; this is a defence-in-depth cap so a config drift on the
# Lambda side can't blow up the prompt.
_SNIPPET_PREVIEW_CHARS = 800

# Anniversary lookback offsets (years). Mirrors the "Mode 2" candidates
# in the compose-closer prompt — one near year ago, five years back,
# eight years back. Eight is the deep cut for a nine-year archive.
_ANNIVERSARY_OFFSETS = (1, 5, 8)
# How many chars of body to include per anniversary candidate. Bigger
# than the semantic snippets because the model has only three of these
# and needs enough material to find one specific detail to surface.
_ANNIVERSARY_PREVIEW_CHARS = 1500

# Matches bare "Weekly Thing N" or "WT N" / "WTN" references in the
# closer body. ``\b`` anchors prevent matching inside longer tokens.
# Used by _linkify_archive_refs after masking existing markdown links so
# we never double-wrap text that's already inside [..](..).
_ISSUE_REF_RE = re.compile(r"\b(Weekly Thing|WT)\s?(\d{1,4})\b")
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")


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


def _parse_pub_date(value: str) -> Optional[datetime]:
    """Parse an emails.json ``publish_date`` (``YYYY-MM-DDTHH:MM:SSZ``)
    into a naive datetime. Returns ``None`` on any parse failure rather
    than raising — the anniversary lookup tolerates missing dates by
    skipping that entry."""
    if not value:
        return None
    raw = value.strip()
    # Strip trailing 'Z' so fromisoformat accepts the value on older Python.
    if raw.endswith("Z"):
        raw = raw[:-1]
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _read_archive_body_preview(issue_number: int, char_cap: int) -> str:
    """Return the first ``char_cap`` characters of the issue's
    ``archive.md`` body (front matter stripped). Used for anniversary
    candidates so the model has real content to anchor a citation on,
    not just the subject line. Returns ``""`` if the file is missing."""
    path = ISSUES_ROOT / str(issue_number) / "archive.md"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    # Strip YAML front matter so the preview is the actual body.
    body_match = re.match(r"^---\n.+?\n---\n(.*)$", text, re.DOTALL)
    body = body_match.group(1) if body_match else text
    body = body.strip()
    if len(body) > char_cap:
        body = body[:char_cap].rstrip() + "…"
    return body


def _anniversary_candidates(
    publish_date: str,
    current_number: int,
) -> list[dict[str, Any]]:
    """Find the issue published nearest each anniversary offset
    (1, 5, 8 years before ``publish_date``). Returns up to three
    candidates, each with ``issue_number``, ``subject``, ``publish_date``,
    ``years_ago``, and ``body_preview`` (≈1500 chars from archive.md).

    Empty list if ``emails.json`` is missing or unparseable, or if
    ``publish_date`` doesn't parse. Duplicate issues across offsets are
    deduped — a 5-year and 8-year lookup that resolve to the same
    closest issue only shows up once."""
    if not EMAILS_JSON.exists():
        return []
    try:
        rows = json.loads(EMAILS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    current = _parse_pub_date(publish_date)
    if current is None:
        return []

    # Pre-parse every entry's date once.
    indexed: list[tuple[int, datetime, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        num = row.get("number")
        if not isinstance(num, int) or num == current_number or num >= current_number:
            continue
        when = _parse_pub_date(row.get("publish_date") or "")
        if when is None:
            continue
        indexed.append((num, when, (row.get("subject") or "").strip()))

    if not indexed:
        return []

    seen_numbers: set[int] = set()
    out: list[dict[str, Any]] = []
    for years in _ANNIVERSARY_OFFSETS:
        # Approximate year arithmetic — leap-year drift is irrelevant
        # for "nearest issue" since issues are weekly and the window
        # naturally hits within a few days of the target.
        target = current - timedelta(days=365 * years)
        best = min(indexed, key=lambda row: abs((row[1] - target).total_seconds()))
        num, when, subject = best
        if num in seen_numbers:
            continue
        seen_numbers.add(num)
        out.append({
            "issue_number": num,
            "subject": subject,
            "publish_date": when.strftime("%Y-%m-%d"),
            "years_ago": years,
            "body_preview": _read_archive_body_preview(num, _ANNIVERSARY_PREVIEW_CHARS),
        })
    return out


def _retrieve_passages(query: str, current_number: int) -> list[dict[str, Any]]:
    """Fetch the top archive passages for ``query`` via Thingy's
    ``/retrieve`` endpoint (Bedrock embed + Cohere rerank). Drops any
    passage from the current in-flight issue (the model shouldn't cite
    the issue it's closing). Raises ``thingy_retrieve.ThingyRetrieveError``
    on any failure — see module docstring for why this is fail-loud."""
    passages = thingy_retrieve.retrieve(query, k=_ARCHIVE_SNIPPET_COUNT)
    return [
        p for p in passages
        if not (isinstance(p, dict) and p.get("issue_number") == current_number)
    ]


def _format_prior_closers(prior: list[tuple[int, str]]) -> str:
    if not prior:
        return "_(none — this is one of the first issues with a closer.)_"
    parts: list[str] = []
    for num, text in prior:
        parts.append(f"**WT{num}:** {text}")
    return "\n\n".join(parts)


def _format_archive_snippets(passages: list[dict[str, Any]]) -> str:
    """Render passages as a list the model can ground references on.
    One block per passage: header line carrying the issue number +
    subject + date + section, then the snippet text indented as a
    blockquote so it reads as quoted source material rather than as
    instruction. Issue numbers are repeated in the header so the model
    can drop them straight into the markdown link in its reply."""
    if not passages:
        return "_(retrieval returned no passages — the model has nothing grounded to draw on.)_"
    blocks: list[str] = []
    for p in passages:
        num = p.get("issue_number")
        subject = (p.get("subject") or "").strip()
        date = (p.get("publish_date") or "")[:10]
        section = (p.get("section") or "").strip()
        text = (p.get("text") or "").strip()
        if len(text) > _SNIPPET_PREVIEW_CHARS:
            text = text[:_SNIPPET_PREVIEW_CHARS].rstrip() + "…"
        # Collapse internal whitespace so multi-paragraph snippets don't
        # blow up the blockquote line count.
        text = re.sub(r"\s+", " ", text)
        header_bits = [f"**WT{num}**"]
        if subject:
            header_bits.append(subject)
        if date:
            header_bits.append(date)
        if section:
            header_bits.append(section)
        header = " — ".join(header_bits)
        blocks.append(f"### {header}\n\n> {text}")
    return "\n\n".join(blocks)


def _format_anniversary_candidates(
    candidates: list[dict[str, Any]],
) -> str:
    """Render anniversary candidates as labelled blocks. Each shows the
    years-ago framing, issue number, subject, publish date, and a body
    preview the model can mine for a specific detail to surface."""
    if not candidates:
        return "_(no anniversary candidates available — the archive doesn't reach back this far yet.)_"
    blocks: list[str] = []
    for c in candidates:
        years = c.get("years_ago")
        num = c.get("issue_number")
        subject = c.get("subject") or ""
        date = c.get("publish_date") or ""
        preview = (c.get("body_preview") or "").strip()
        # Collapse interior whitespace so the preview reads as flowing
        # text, not a multi-section layout.
        preview = re.sub(r"\n{3,}", "\n\n", preview)
        header = f"### {years} year(s) ago — **WT{num}** — {subject} — {date}"
        if preview:
            blocks.append(f"{header}\n\n{preview}")
        else:
            blocks.append(f"{header}\n\n_(body unavailable in local archive — cite carefully or skip.)_")
    return "\n\n---\n\n".join(blocks)


def _build_user_message(
    *,
    issue_number: int,
    publish_date: str,
    baseline_body: str,
    prior: list[tuple[int, str]],
    passages: list[dict[str, Any]],
    anniversaries: list[dict[str, Any]],
) -> str:
    return (
        f"You're writing **Echoes** (Thingy's archive note) for **The Weekly "
        f"Thing #{issue_number}**, publishing {publish_date}.\n\n"
        f"---\n\n"
        f"## Current issue draft\n\n"
        f"```markdown\n{baseline_body.strip()}\n```\n\n"
        f"---\n\n"
        f"## Past {len(prior)} closer(s) (do not reuse themes or entries from these)\n\n"
        f"{_format_prior_closers(prior)}\n\n"
        f"---\n\n"
        f"## Semantic snippets — Mode 1 candidates\n\n"
        f"Top-{len(passages)} archive passages for this issue's draft, ranked by "
        f"Bedrock embed + Cohere rerank. Use these for **thematic resonance** "
        f"(Mode 1): pick 1–3 that genuinely echo a thread in the current "
        f"issue. Don't cite anything not shown here.\n\n"
        f"{_format_archive_snippets(passages)}\n\n"
        f"---\n\n"
        f"## Anniversary candidates — Mode 2 candidates\n\n"
        f"The issue published nearest each anniversary offset (one, five, "
        f"eight years before this one). Use these for **anniversary echo** "
        f"(Mode 2): pick one and surface a specific detail from its body "
        f"preview.\n\n"
        f"{_format_anniversary_candidates(anniversaries)}\n\n"
        f"---\n\n"
        f"Now write the Echoes note: 2-5 sentences (≈60-110 words) in Thingy's "
        f"voice (third-person Jamie), OR the literal SKIP line. Every cited "
        f"issue must be a markdown link "
        f"`[WT###](https://weekly.thingelstad.com/archive/N/)`. Open with the "
        f"closer itself — no meta-commentary about which candidate set you "
        f"chose or its quality. Nothing else."
    )


def _linkify_archive_refs(text: str) -> str:
    """Convert any bare ``Weekly Thing N`` / ``WT N`` references in
    ``text`` into markdown links to the public archive. References that
    are already inside a markdown link (``[…](…)``) are preserved
    untouched. Safety net for the cases where the model writes plain
    text despite the prompt asking for a link."""
    if not text:
        return text
    placeholders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00LINK{len(placeholders) - 1}\x00"

    masked = _MD_LINK_RE.sub(_stash, text)

    def _linkify(match: re.Match[str]) -> str:
        label = match.group(0)
        num = match.group(2)
        url = _ARCHIVE_URL_TPL.format(n=num)
        return f"[{label}]({url})"

    linked = _ISSUE_REF_RE.sub(_linkify, masked)
    for idx, original in enumerate(placeholders):
        linked = linked.replace(f"\x00LINK{idx}\x00", original)
    return linked


def _is_skip(reply: str) -> bool:
    """Tolerant SKIP detection — caps-insensitive, whitespace-stripped.
    Accepts the bare ``SKIP`` legacy form **and** the new explicit form
    the prompt asks for: ``SKIP — no strong archive connection this
    week.``. Anything else (including empty) is treated as not-a-skip
    so the caller can write whatever was returned and Jamie can spot a
    bad reply in #editorial."""
    if not reply:
        return False
    stripped = reply.strip().strip("`'\"").lower()
    if stripped == "skip":
        return True
    # Strip trailing terminator first so "SKIP." reads as a bare SKIP too.
    bare = stripped.rstrip(".!").strip()
    if bare == "skip":
        return True
    # The explicit form: "SKIP — no strong archive connection this week."
    # plus minor variants the model might emit (en dash vs hyphen, case,
    # trailing period).
    return bool(re.match(r"^skip\s*[—\-:]", stripped))


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
            try:
                passages = await asyncio.to_thread(
                    _retrieve_passages,
                    baseline_body[: _llm_job.ISSUE_BODY_CAP],
                    n,
                )
            except thingy_retrieve.ThingyRetrieveError as exc:
                # Fail loud — quality bar requires real semantic
                # retrieval. The closer is an optional section, so a
                # retrieval outage just blocks this one job; the rest
                # of create-final keeps moving (final.md without a
                # The Closer section is a valid issue shape).
                msg = (
                    f"❌ compose-closer for WT{n}: Thingy retrieval unavailable "
                    f"(`{exc}`). Closer skipped — final.md will assemble without "
                    f"a The Closer section."
                )
                logger.warning("compose-closer thingy_retrieve failed: %s", exc)
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(
                    False, msg,
                    data={"issue_number": n, "retrieval_failed": True},
                )
            anniversaries = await asyncio.to_thread(
                _anniversary_candidates, publish_date, n,
            )
            user_body = _build_user_message(
                issue_number=n,
                publish_date=publish_date,
                baseline_body=baseline_body[: _llm_job.ISSUE_BODY_CAP],
                prior=prior,
                passages=passages,
                anniversaries=anniversaries,
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
                # render final.md without a The Closer section.
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

            # Linkify any bare "Weekly Thing N" / "WT N" references the
            # model didn't wrap in a markdown link itself.
            text = _linkify_archive_refs(text)

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
        f"📚 compose-closer for **WT{n}**: {word_count}-word Echoes note written.\n"
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
