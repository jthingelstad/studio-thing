"""``compose-echoes`` — write **Echoes**, the archive note that closes
every issue.

Reader-facing section heading is ``## Echoes``; the on-disk atom name
matches (``echoes.md``, under ``atoms/`` like the other composed
atoms).

Echoes runs in an archive-librarian voice: third-person about Jamie, not
Jamie's first person. It's the deliberate handoff at the foot of every
issue from Jamie's voice to the archive's.

**Trigger:** auto-fired inside ``mark-built`` (the Build → Publish
phase transition), alongside ``compose-envelope``. Runs over the
*frozen* content. Was previously triggered by
``reorder`` on ✅; that ran over mid-edit state, which produced echoes
that didn't reflect the shipped issue.

**Mandatory.** No SKIP path — Echoes ships in every issue. If neither
the thematic-resonance mode nor the anniversary mode produces
something strong on a given week, the prompt still asks for the
strongest available framing rather than silence. Quality bar is held
by (1) running on Opus (the single highest-leverage voice surface),
(2) failing loud on retrieval failure (no silent BM25 fallback), and
(3) feeding the recent Echoes verbatim so the model can calibrate
voice from real samples and avoid theme repetition.

The job offers Eddy **two candidate sets** in the prompt; he picks
the stronger one for this issue:

- **Mode 1 — Thematic Resonance** (preferred when the connection is
  real). Top-K archive passages retrieved via Librarian's ``/retrieve``
  endpoint (Bedrock Cohere embed → vector search → Cohere rerank).
  Sourced through ``tools/thingy_retrieve.py``. Librarian semantic
  retrieval, not the in-process BM25 corpus.
- **Mode 2 — Anniversary Echo** (always-available fallback). For each
  offset in ``_ANNIVERSARY_OFFSETS`` (one, five, eight years back), the
  job finds the issue published nearest to that date and pulls a body
  preview. The prompt asks for a specific detail.

Inputs to the Opus call:

- The current issue draft (atoms + assembled body via
  ``_llm_job.draft_body``) — the shared anchor for every Publish-phase
  job, so Echoes can specifically echo what *this* week is doing rather
  than surface-match.
- The bodies of the last 6 echoes (``data/issues/{N-k}/echoes.md``,
  newest-first; silently skipped if missing) — calibrates voice +
  prevents theme repetition.
- Semantic snippets (Mode 1 candidates).
- Anniversary candidates (Mode 2 candidates).

Output is a 2-to-4-sentence markdown paragraph (≈40–80 words) in
the archive voice, with referenced issue(s) rendered as markdown
links (``[WT###](https://weekly.thingelstad.com/archive/N/)``).
Written to ``echoes.md`` in S3 (under ``atoms/``) + local
``data/issues/{N}/``.

Idempotent: re-running regenerates Echoes (output may differ). To
preserve a specific Echoes, edit via ``/eddy edit echoes`` after the
job runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..tools import content_store, db, thingy_retrieve
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_echoes")

NAME = "compose-echoes"

REPO = Path(__file__).resolve().parents[3]
ISSUES_ROOT = REPO / "data" / "issues"

# Used by _anniversary_candidates() to look up issue numbers + dates.
EMAILS_JSON = REPO / "apps" / "site" / "_data" / "emails.json"

# Echoes is a once-per-issue archive voice surface, with citations that
# have to be earned — Opus pays off
# at ~$5/yr more than Sonnet for the quality differential. Override down
# to Sonnet for cost-test or quick fallback via ``WORKSHOP_ECHOES_MODEL``.
_ECHOES_DEFAULT_MODEL = "opus"


def _echoes_model() -> str:
    override = (os.environ.get("WORKSHOP_ECHOES_MODEL") or "").strip()
    return override or _ECHOES_DEFAULT_MODEL

# Public archive URL — used to convert "Weekly Thing N" references in the
# echoes body into clickable markdown links.
_ARCHIVE_URL_TPL = "https://weekly.thingelstad.com/archive/{n}/"

# Max past echoes to pull for anti-repetition. Six covers a comfortable
# "recent history" window without bloating the prompt.
_PRIOR_ECHOES_COUNT = 6

# How many passages to retrieve from the Librarian API. 20 gives Sonnet a thick
# pool to pick from (≈ 6 distinct issues represented on average; the
# rerank biases hard toward the best matches at the top),
# while staying under the retrieval result ceiling and
# keeping the prompt at a manageable ~10–15 KB after preview-cap.
_ARCHIVE_SNIPPET_COUNT = 20
# Per-passage body cap. The Lambda already trims to ~1200 chars in
# compactSource; this is a defence-in-depth cap so a config drift on the
# Lambda side can't blow up the prompt.
_SNIPPET_PREVIEW_CHARS = 800

# Anniversary lookback offsets (years). Mirrors the "Mode 2" candidates
# in the compose-echoes prompt — one near year ago, five years back,
# eight years back. Eight is the deep cut for a nine-year archive.
_ANNIVERSARY_OFFSETS = (1, 5, 8)
# How many chars of body to include per anniversary candidate. Bigger
# than the semantic snippets because the model has only three of these
# and needs enough material to find one specific detail to surface.
_ANNIVERSARY_PREVIEW_CHARS = 1500

# Matches bare "Weekly Thing N" or "WT N" / "WTN" references in the
# echoes body. ``\b`` anchors prevent matching inside longer tokens.
# Used by _linkify_archive_refs after masking existing markdown links so
# we never double-wrap text that's already inside [..](..).
_ISSUE_REF_RE = re.compile(r"\b(Weekly Thing|WT)\s?(\d{1,4})\b")
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")


def _prior_echoes(issue_number: int) -> list[tuple[int, str]]:
    """Read up to ``_PRIOR_ECHOES_COUNT`` previous issues' echoes bodies
    from local ``data/issues/{N-k}/echoes.md``. Returns
    ``[(issue_number, echoes_text), …]`` newest-first. Issues without
    an echoes file (most of the back catalog — this is a new section)
    are silently skipped."""
    out: list[tuple[int, str]] = []
    n = int(issue_number)
    for offset in range(1, _PRIOR_ECHOES_COUNT + 1):
        prev = n - offset
        if prev < 1:
            break
        path = ISSUES_ROOT / str(prev) / "echoes.md"
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
    """Fetch the top archive passages for ``query`` via the Librarian
    ``/retrieve`` endpoint (Bedrock embed + Cohere rerank). Drops any
    passage from the current in-flight issue (the model shouldn't cite
    the issue it's closing). Raises ``thingy_retrieve.ThingyRetrieveError``
    on any failure — see module docstring for why this is fail-loud."""
    passages = thingy_retrieve.retrieve(query, k=_ARCHIVE_SNIPPET_COUNT)
    return [
        p for p in passages
        if not (isinstance(p, dict) and p.get("issue_number") == current_number)
    ]


def _format_prior_echoes(prior: list[tuple[int, str]]) -> str:
    if not prior:
        return "_(none — this is one of the first issues with echoes.)_"
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
        f"You're writing **Echoes** (the archive note) for **The Weekly "
        f"Thing #{issue_number}**, publishing {publish_date}.\n\n"
        f"---\n\n"
        f"## Current issue draft\n\n"
        f"```markdown\n{baseline_body.strip()}\n```\n\n"
        f"---\n\n"
        f"## Past {len(prior)} echoes note(s) (do not reuse themes or entries from these)\n\n"
        f"{_format_prior_echoes(prior)}\n\n"
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
        f"Now write the Echoes note: 2-5 sentences (≈60-110 words) in the "
        f"archive voice (third-person Jamie), OR the literal SKIP line. Every cited "
        f"issue must be a markdown link "
        f"`[WT###](https://weekly.thingelstad.com/archive/N/)`. Open with the "
        f"echoes note itself — no meta-commentary about which candidate set you "
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


def _clean_echoes(reply: str) -> str:
    """Strip surrounding whitespace + accidental code-fence wrappers; return
    the echoes paragraph as it should land in echoes.md."""
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
    """Write the Echoes archive note for the in-flight issue.

    Mandatory + auto-fired inside ``mark-built``. Reads the frozen
    content via ``_llm_job.draft_body`` unless an explicit
    ``baseline_body`` is provided (the test harness uses this to inject
    a known body). No SKIP path — Echoes ships in every issue. Fails
    loud on retrieval failure or persistent empty reply rather than
    degrading silently.
    """
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — start one in Studio first.",
        )
    n = int(window["issue_number"])
    publish_date = (window.get("pub_date") or "")[:10] or "(unknown date)"

    if baseline_body is None:
        baseline_body = await asyncio.to_thread(_llm_job.draft_body, n)
    if not baseline_body or not baseline_body.strip():
        return _base.JobResult(
            False, f"❌ no body available for WT{n} — sync sources in Studio first.",
        )

    bot, channel, reason = _llm_job.resolve_bot_and_channel(
        ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL",
    )
    if bot is None:
        return _base.JobResult(
            True, f"(compose-echoes skipped — {reason})",
            data={"echoes_written": False},
        )

    asset = f"{n}/echoes.md"
    try:
        with _base.job_lock([asset], NAME):
            try:
                base_prompt = anthropic_client.load_prompt("eddy-compose-echoes")
            except OSError as exc:
                logger.warning("compose-echoes: prompt missing: %s", exc)
                return _base.JobResult(
                    False, f"❌ compose-echoes prompt missing: `{exc}`",
                )

            prior = await asyncio.to_thread(_prior_echoes, n)
            try:
                passages = await asyncio.to_thread(
                    _retrieve_passages,
                    baseline_body[: _llm_job.ISSUE_BODY_CAP],
                    n,
                )
            except thingy_retrieve.ThingyRetrieveError as exc:
                # Fail loud — Echoes is mandatory and its quality bar
                # requires real semantic retrieval. Surface the failure
                # so mark-built can log it; the rest of the Publish
                # phase still proceeds (downstream prompts degrade
                # gracefully on missing echoes.md), but the operator
                # should know Echoes is missing for this issue.
                msg = (
                    f"❌ compose-echoes for WT{n}: Librarian retrieval unavailable "
                    f"(`{exc}`). Echoes section will be missing from this issue "
                    f"unless re-run via `/eddy issue echoes` once retrieval recovers."
                )
                logger.warning("compose-echoes thingy_retrieve failed: %s", exc)
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

            with db.AgentRun("eddy", trigger="compose-echoes") as agent_run:
                reply, meta = await bot.core(
                    latest=user_msg, history=[], model=_echoes_model(),
                )
                agent_run.record_meta(meta)
                agent_run.records_written = 1 if reply else 0

            if not reply or not reply.strip():
                msg = f"❌ compose-echoes for WT{n}: empty reply from Eddy."
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n})

            text = _clean_echoes(reply)
            if not text:
                msg = f"❌ compose-echoes for WT{n}: reply was empty after cleanup."
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n})

            # Linkify any bare "Weekly Thing N" / "WT N" references the
            # model didn't wrap in a markdown link itself.
            text = _linkify_archive_refs(text)

            # Write to S3 workspace (under atoms/) + mirror locally (the
            # ship paths read from local).
            content_store.write_issue(n, "echoes.md", text + "\n")
            local_dir = ISSUES_ROOT / str(n)
            local_dir.mkdir(parents=True, exist_ok=True)
            (local_dir / "echoes.md").write_text(text + "\n", encoding="utf-8")
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `compose-echoes` already running ({exc.holder_desc}).",
        )

    word_count = len(text.split())
    msg = (
        f"📚 compose-echoes for **WT{n}**: {word_count}-word Echoes note written.\n"
        f"> {text}"
    )
    await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
    return _base.JobResult(
        True,
        f"compose-echoes for WT{n}: written ({word_count} words).",
        data={
            "issue_number": n, "echoes_written": True,
            "echoes": text, "word_count": word_count,
        },
    )
