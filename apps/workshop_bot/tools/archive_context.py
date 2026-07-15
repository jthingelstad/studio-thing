"""Shared helpers for jobs that want to pre-inject Librarian archive
context into their prompts.

The pattern is the same one ``compose-echoes`` uses: call the Librarian
``/retrieve`` endpoint for the top semantic matches against a query, then
format them as a labelled prompt block. Several jobs need this:

- ``compose-subject`` — same question, different output
- (and ``draft-review`` per-Notable echoes use a similar shape)

The helpers fail soft: a retrieval outage returns an explicit
"_(retrieval unavailable: …)_" block rather than raising. These jobs
have plenty to do without the archive context — losing it should
degrade the prompt, not block the job.

If a job's quality bar requires retrieval (like ``compose-echoes``),
it should call ``thingy_retrieve.retrieve`` directly and fail loud
instead of using these helpers.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from . import thingy_retrieve

logger = logging.getLogger("workshop.tools.archive_context")

# Per-passage body cap inside the rendered block. Bedrock's response
# trims to ~1200 chars; this is a tighter cap appropriate for prompt
# pre-injection (we want context, not transcription).
_PASSAGE_PREVIEW_CHARS = 500


def fetch_archive_context(
    query: str,
    *,
    k: int = 8,
    exclude_issue: Optional[int] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Fetch the top archive passages for ``query``. Returns
    ``(passages, error_message)``. On success ``error_message`` is
    ``None``; on retrieval failure ``passages`` is empty and
    ``error_message`` carries the reason for inclusion in the block.

    ``exclude_issue``, if given, drops passages from that issue
    number — useful when the caller is the in-flight issue itself and
    citing your own draft would be silly."""
    query = (query or "").strip()
    if not query:
        return [], None
    try:
        passages = thingy_retrieve.retrieve(query, k=k)
    except thingy_retrieve.ThingyRetrieveError as exc:
        logger.warning("archive_context: retrieval failed: %s", exc)
        return [], str(exc)
    if exclude_issue is not None:
        passages = [
            p for p in passages
            if not (isinstance(p, dict) and p.get("issue_number") == exclude_issue)
        ]
    return passages, None


def format_archive_context_block(
    passages: list[dict[str, Any]],
    *,
    heading: str,
    intro: str,
    error: Optional[str] = None,
) -> str:
    """Render passages as a markdown block: H2 ``heading`` line, then
    ``intro`` paragraph, then one block per passage (issue + subject +
    date + section header, then snippet as blockquote).

    ``error`` is set when retrieval failed — the block surfaces the
    failure rather than silently omitting itself, so the model can
    note "(no thread context available this turn)" in its output."""
    parts: list[str] = [f"## {heading}", "", intro, ""]
    if error:
        parts.append(f"_(retrieval unavailable: {error} — proceed without thread context.)_")
        return "\n".join(parts)
    if not passages:
        parts.append("_(no archive passages surfaced for this query — treat this as fresh territory.)_")
        return "\n".join(parts)
    blocks: list[str] = []
    for p in passages:
        num = p.get("issue_number")
        subject = (p.get("subject") or "").strip()
        date = (p.get("publish_date") or "")[:10]
        section = (p.get("section") or "").strip()
        text = (p.get("text") or "").strip()
        if len(text) > _PASSAGE_PREVIEW_CHARS:
            text = text[:_PASSAGE_PREVIEW_CHARS].rstrip() + "…"
        text = re.sub(r"\s+", " ", text)
        header_bits = [f"**WT{num}**"]
        if subject:
            header_bits.append(subject)
        if date:
            header_bits.append(date)
        if section:
            header_bits.append(section)
        blocks.append(f"### {' — '.join(header_bits)}\n\n> {text}")
    parts.append("\n\n".join(blocks))
    return "\n".join(parts)
