"""``eddy-review`` — Eddy's on-demand editorial review of the in-flight issue.

The single substantive editorial pass, extracted from the retired
``update-draft`` job and made **on-demand** (a button on the web production
page; no daily LLM spend). The draft body is rendered straight from current
DB state (``renderers.render_body_for_issue`` — the DB is the draft), Eddy
reviews it on Opus, and each target-anchored bullet persists as an
``editorial_comments`` row with a stable handle (``E349-N1``…). The comments
surface on the web production page and via the ``editorial__get_comment``
agent tool / ``@eddy tell me about E349-N1`` Discord lookup.

A ``PASS`` verdict closes the prior pass's open comments (the draft was
reviewed and found clean). Re-runs supersede prior comments wholesale.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date

from ..personas.base import is_pass_response
from ..tools import archive_context, db, issue_items, render, renderers
from ..tools.content import context
from ..tools.content import draft as draft_mod
from ..tools.llm import anthropic_client
from . import _base

logger = logging.getLogger("workshop.jobs.eddy_review")

NAME = "eddy-review"

# How many archive passages to surface in the review's "Recent archive
# echoes" block, and how much of the draft body seeds the semantic query.
_ECHO_K = 10
_ECHO_QUERY_CHARS = 3000

# The review is the highest-value thing Eddy does, so it runs on Opus by
# default. Tunable via ``WORKSHOP_EDDY_DRAFT_REVIEW_MODEL``.
_DEFAULT_MODEL = "opus"


def _review_model() -> str:
    override = (os.environ.get("WORKSHOP_EDDY_DRAFT_REVIEW_MODEL") or "").strip()
    return override or _DEFAULT_MODEL


# ---------- editorial_comments capture ----------
#
# After Eddy writes the review markdown, we parse the ``<!-- target:xxx -->``
# markers and store each anchored bullet/paragraph as a row in
# ``editorial_comments`` with a stable handle (``E349-N1``, ``E349-X3``).
# Re-runs supersede prior comments wholesale.

_TARGET_MARKER_RE = re.compile(r"<!--\s*target:([a-z0-9_-]+)\s*-->")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+", re.MULTILINE)


def _split_review_into_segments(review_md: str) -> list[str]:
    """Split the review markdown into top-level segments (contiguous
    paragraphs or bullet items)."""
    text = (review_md or "").strip()
    if not text:
        return []
    raw_blocks = re.split(r"\n\s*\n", text)
    segments: list[str] = []
    for block in raw_blocks:
        block = block.rstrip()
        if not block:
            continue
        positions: list[int] = [0]
        for m in _BULLET_RE.finditer(block):
            if m.start() > 0:
                positions.append(m.start())
        positions.append(len(block))
        for i in range(len(positions) - 1):
            piece = block[positions[i] : positions[i + 1]].strip()
            if piece:
                segments.append(piece)
    return segments


def _section_for_target(target: str) -> tuple[str, str]:
    """Resolve a target marker (``n1``, ``b2``, ``j3``, ``intro``,
    ``hygiene``, …) to ``(scope, section_or_letter)``."""
    if target in ("hygiene", "x"):
        return "hygiene", "hygiene"
    if target in ("whole", "issue", "w"):
        return "issue", "issue"
    if target in issue_items.SECTION_HANDLE_LETTER:
        return "section", target
    if len(target) >= 2 and target[0] in ("n", "b", "j"):
        return "item", {"n": "notable", "b": "brief", "j": "journal"}[target[0]]
    return "issue", "issue"


def _row_id_for_synth(issue_number: int, target: str) -> "int | None":
    """Map ``n1`` / ``b2`` / ``j3`` to the row id at that position in its
    section (``None`` when the position is out of range)."""
    if len(target) < 2 or target[0] not in ("n", "b", "j"):
        return None
    section = {"n": "notable", "b": "brief", "j": "journal"}[target[0]]
    try:
        idx = int(target[1:])
    except ValueError:
        return None
    rows = issue_items.list_items(issue_number, section=section, include_promoted=False)
    if idx < 1 or idx > len(rows):
        return None
    return int(rows[idx - 1]["id"])


def _store_review_comments(issue_number: int, review_md: str) -> int:
    """Parse the review markdown and write one ``editorial_comments`` row per
    target-marker-prefixed segment. Prior-pass open comments get superseded
    *after* the new pass writes. Returns the count written."""
    if not (review_md or "").strip():
        return 0
    segments = _split_review_into_segments(review_md)
    if not segments:
        return 0
    prior_open_ids = [int(c["id"]) for c in issue_items.list_open_comments(issue_number)]
    written = 0
    for seg in segments:
        markers = _TARGET_MARKER_RE.findall(seg)
        if not markers:
            continue  # ungrounded prose — skip
        target = markers[0]
        scope, section_or_letter = _section_for_target(target)
        body_md = _TARGET_MARKER_RE.sub("", seg).strip()
        body_md = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", body_md).strip()
        if not body_md:
            continue
        try:
            if scope == "item":
                rid = _row_id_for_synth(issue_number, target)
                if rid is None:
                    issue_items.write_comment(
                        issue_number=issue_number,
                        scope="section",
                        section=section_or_letter,
                        body_md=body_md,
                        verdict="suggestion",
                    )
                else:
                    issue_items.write_comment(
                        issue_number=issue_number,
                        scope="item",
                        item_id=rid,
                        body_md=body_md,
                        verdict="suggestion",
                    )
            elif scope in ("section",):
                issue_items.write_comment(
                    issue_number=issue_number,
                    scope="section",
                    section=section_or_letter,
                    body_md=body_md,
                    verdict="suggestion",
                )
            elif scope == "hygiene":
                issue_items.write_comment(
                    issue_number=issue_number,
                    scope="hygiene",
                    body_md=body_md,
                    verdict="suggestion",
                )
            else:
                issue_items.write_comment(
                    issue_number=issue_number,
                    scope="issue",
                    body_md=body_md,
                    verdict="suggestion",
                )
        except Exception:  # noqa: BLE001
            logger.exception("eddy-review: failed to store review comment")
            continue
        written += 1
    if written and prior_open_ids:
        new_open = issue_items.list_open_comments(issue_number)
        anchor = next((c["id"] for c in new_open if int(c["id"]) not in prior_open_ids), None)
        if anchor is not None:
            try:
                with db.connect() as conn:
                    placeholders = ",".join("?" for _ in prior_open_ids)
                    conn.execute(
                        f"UPDATE editorial_comments SET replaced_by_id = ? "
                        f"WHERE id IN ({placeholders})",
                        [int(anchor), *[int(i) for i in prior_open_ids]],
                    )
            except Exception:  # noqa: BLE001
                logger.exception("eddy-review: prior-pass supersede failed")
    return written


# ---------- the job ----------


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — start one in Studio first.")
    n = int(window["issue_number"])

    team = getattr(getattr(ctx, "deps", None), "team", None)
    eddy = team.bots.get("eddy") if team is not None else None
    if eddy is None or getattr(eddy, "user", None) is None:
        return _base.JobResult(False, "❌ Eddy isn't online — can't run the review.")
    try:
        prompt = anthropic_client.load_prompt("eddy-draft-review")
    except OSError as exc:
        return _base.JobResult(False, f"❌ draft-review prompt missing: {exc}")

    # The DB is the draft — render the body fresh for this review.
    draft_text = await asyncio.to_thread(renderers.render_body_for_issue, n, window=window)
    if not draft_text.strip():
        return _base.JobResult(False, f"❌ WT{n} renders empty — nothing to review.")

    st = await asyncio.to_thread(draft_mod.section_status, n)
    eddy_ctx = context.build_eddy_context(
        ref_date=date.today(), section_status=st, prev_digest=None
    )
    target_legend = render.review_target_legend(issue_number=n, section_status=st)
    # Pre-inject semantic echoes from the archive (fail-soft).
    echo_passages, echo_error = await asyncio.to_thread(
        archive_context.fetch_archive_context,
        draft_text[:_ECHO_QUERY_CHARS],
        k=_ECHO_K,
        exclude_issue=n,
    )
    echo_block = archive_context.format_archive_context_block(
        echo_passages,
        heading="Recent archive echoes",
        intro=(
            "These are the archive passages most semantically related to "
            "the current draft (top-K via Bedrock embed + Cohere rerank). "
            "Use them to flag when a Notable / Featured item in this draft "
            "echoes recent coverage — call out the overlap and ask whether "
            "the new piece adds something the prior one didn't. Don't "
            "treat echoes as automatic problems (Jamie threads themes "
            "deliberately) but DO surface them so the commentary can "
            "acknowledge the prior take instead of restating it."
        ),
        error=echo_error,
    )
    # Cache-friendly user message: the static prompt block carries a
    # cache_control marker; the dynamic block (date, counts, target IDs,
    # echoes, draft body) follows uncached.
    dynamic_block = (
        f"{context.render_block(eddy_ctx)}\n\n"
        f"---\n\n## Review target IDs\n\n"
        f"Use these IDs for anchored comments when a note points at a specific place:\n\n"
        f"{target_legend}\n\n"
        f"---\n\n{echo_block}\n\n"
        f"---\n\nThe current draft (WT{n}):\n\n```markdown\n{draft_text}\n```"
    )
    user_msg = [
        {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_block},
    ]
    with db.AgentRun("eddy", trigger="eddy-review") as agent_run:
        answer, _m = await eddy.core(latest=user_msg, history=[], model=_review_model())
        agent_run.record_meta(_m)
        agent_run.records_written = 0 if (not answer or is_pass_response(answer)) else 1

    if not answer or is_pass_response(answer):
        # A real verdict: the draft was reviewed and found clean. Prior
        # open comments are stale — close them.
        closed = 0
        try:
            closed = issue_items.close_all_open_comments(n)
        except Exception:  # noqa: BLE001
            logger.exception("eddy-review: failed to close prior comments on PASS")
        return _base.JobResult(
            True,
            f"✅ Eddy reviewed **WT{n}** — nothing to flag"
            + (f" (closed {closed} stale comment{'s' if closed != 1 else ''})" if closed else ""),
            data={"issue_number": n, "pass": True, "closed": closed},
        )

    written = 0
    try:
        written = _store_review_comments(n, answer.strip())
    except Exception:  # noqa: BLE001
        logger.exception("eddy-review: review-comments capture failed")
    return _base.JobResult(
        True,
        f"📝 Eddy reviewed **WT{n}** — {written} anchored comment"
        f"{'s' if written != 1 else ''} recorded.",
        data={"issue_number": n, "pass": False, "comments": written},
    )
