"""``continuity-check`` — the archive as a collaborator *while Jamie writes*.

When Jamie writes a newsletter intro, Studio surfaces what he's **already
published** on that topic, so he doesn't
unknowingly repeat himself and can build on (or deliberately contradict)
his prior takes. This is continuity-while-you-write, not a review.

The mechanism is the same semantic-retrieval engine ``eddy-review`` and
``compose-echoes`` lean on: ``tools/archive_context.fetch_archive_context``
pulls the top archive passages for the text (Bedrock embed + Cohere rerank
through the Librarian ``/retrieve``). Eddy then writes ONE short nudge — "you've
circled this three times: WT303, WT341… this leans the same way, is there a
new angle?" — referencing issues as ``WT###`` and being honest when there's
genuinely no prior coverage. **He never rewrites Jamie's words** (the one rule,
pinned in ``prompts/eddy/continuity-check.md``).

Fail-soft: a retrieval outage posts a brief "couldn't reach the archive" note
and returns rather than crashing — losing the nudge shouldn't wedge the write
surface that triggered it.

Triggered on demand from the newsletter issue page's intro action. Posts to
``#editorial`` as Eddy.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..tools import archive_context, db
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.continuity_check")

NAME = "continuity-check"

# How many archive passages to surface. ~8 gives Eddy enough spread to spot a
# repeated thread without drowning the nudge in citations.
_RETRIEVE_K = 8

# How much of the new text seeds the semantic query. An intro or a seed is
# short; this cap is defence-in-depth against a pasted wall of text.
_QUERY_CHARS = 3000

# Soft cap on Eddy's posted note. This is a margin nudge, not a report — if he
# overruns, trim rather than flood #editorial.
_NOTE_CHAR_CAP = 1200


async def run_for_text(
    ctx: "_base.JobContext",
    *,
    text: str,
    label: str,
    exclude_issue: Optional[int] = None,
) -> "_base.JobResult":
    """Surface Jamie's prior published coverage of ``text`` as a short Eddy
    note in ``#editorial``.

    ``label`` names what's being checked (e.g. ``"seed: Own your words"`` or
    ``"WT359 intro"``) — it frames the note so Jamie knows which piece it's
    about. ``exclude_issue`` drops passages from that issue number, so the
    newsletter intro doesn't match itself.
    """
    text = (text or "").strip()
    if not text:
        return _base.JobResult(True, "(continuity-check: nothing to check — empty text)")

    r = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if r.bot is None:
        return _base.JobResult(True, f"(continuity-check skipped — {r.error_reason})")

    passages, error = await asyncio.to_thread(
        archive_context.fetch_archive_context,
        text[:_QUERY_CHARS],
        k=_RETRIEVE_K,
        exclude_issue=exclude_issue,
    )
    if error:
        # Fail-soft: the archive is unreachable this turn. Say so briefly and
        # bail — don't crash the write surface that triggered the check.
        msg = (
            f"🔁 Continuity check — **{label}**: couldn't reach the archive "
            f"just now (`{error}`). Nothing lost — try again in a bit."
        )
        await ctx.post(r.channel, msg, persona="eddy")
        logger.info("continuity-check: retrieval unavailable for %s (%s)", label, error)
        return _base.JobResult(
            True,
            f"continuity-check: retrieval unavailable — {error}",
            data={"posted": True, "retrieval_failed": True},
        )

    try:
        prompt = anthropic_client.load_prompt("eddy-continuity-check")
    except OSError as exc:
        return _base.JobResult(False, f"continuity-check: prompt missing: {exc}")

    context_block = archive_context.format_archive_context_block(
        passages,
        heading="Already in the archive",
        intro=(
            "These are the passages Jamie has **already published** most "
            "closely related to what he's writing now (top-K via Bedrock "
            "embed + Cohere rerank). Reference them as WT### — never cite an "
            "issue that isn't shown here."
        ),
        error=error,
    )
    user_msg = (
        f"{prompt}\n\n---\n\n"
        f"## What Jamie is writing now — {label}\n\n"
        f"```\n{text}\n```\n\n"
        f"---\n\n{context_block}"
    )

    reply = ""
    try:
        with db.AgentRun("eddy", trigger=NAME) as agent_run:
            # One turn on Eddy's persona-default model (Sonnet) — the nudge is
            # short and picker-shaped, no need for the review-tier Opus.
            reply, meta = await r.bot.core(latest=user_msg, history=[], model=None)
            agent_run.record_meta(meta)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
    except Exception:  # noqa: BLE001
        logger.exception("continuity-check: Eddy call failed for %s", label)
        return _base.JobResult(False, "continuity-check: Eddy call failed")

    note = (reply or "").strip()
    if not note:
        return _base.JobResult(
            True,
            "continuity-check: Eddy had nothing to add",
            data={"posted": False},
        )
    if len(note) > _NOTE_CHAR_CAP:
        note = note[:_NOTE_CHAR_CAP].rstrip() + "…"

    body = f"🔁 Continuity check — **{label}**\n{note}"
    await ctx.post(r.channel, body, persona="eddy")
    # One place logs "Eddy shared a continuity note" regardless of which
    # surface triggered the check.
    logger.info(
        "continuity-check: Eddy posted a continuity note for %s (%d chars)", label, len(note)
    )
    return _base.JobResult(
        True,
        f"continuity-check: posted a continuity note for {label}",
        data={"posted": True, "passages": len(passages)},
    )
