"""``promotion-prep`` (Marky) — syndication drafts for the latest issue.

Triggered when an issue enters the **Share** phase: ``put-to-bed``
fires this automatically after closing the active window. Re-runnable
on demand from the Share card's "Draft promo" button or via
``/marky prep``. Operates on the most recently *published* issue's
``draft.md`` in the S3 workspace — the channel-neutral body. (We
deliberately don't read buttondown.md / archive.md / transcript here:
buttondown.md carries email-only Liquid blocks + the tracking pixel,
archive.md has website front matter, and transcripts are audio-
shaped — none of those are the right input for cross-channel promo
drafting. draft.md is the canonical body.)

Marky drafts, in Jamie's voice, **2–3 alternative framings per
platform** (LinkedIn ~100–200 words; an r/WeeklyThing megathread; one
per-link Reddit thread per Notable item), posts them all to
``#promotion``, and **never auto-posts** anywhere — Jamie copies /
edits / publishes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..tools import archive_context, db, s3
from ..tools.content import context
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.promotion_prep")

NAME = "promotion-prep"

# How many archive passages to surface as "this issue's thread context".
# Eight gives Marky enough material to recognize a multi-issue thread
# (3+ hits on the same theme over time) without dominating the prompt.
_THREAD_CONTEXT_K = 8

# Cap the query passed to /retrieve. The full draft body would work
# but adds latency for no quality lift — the first ~2000 chars
# (intro + first Notable section) carry the issue's center of gravity.
_THREAD_QUERY_CHARS = 2000


def _resolve_latest_issue(explicit: Optional[int]) -> tuple[Optional[int], Optional[str]]:
    """The Share target = the last-published issue (the most recent row in the
    `issues` table, filed by put-to-bed). The phase, not an RSS poll, is what
    says an issue is ready to share."""
    if explicit is not None:
        return int(explicit), None
    li = db.get_latest_issue()
    if not li:
        return None, None
    return int(li["number"]), (li.get("publish_date") or "")[:10] or None


async def run(ctx: "_base.JobContext", *, issue_number: Optional[int] = None) -> "_base.JobResult":
    # Resolve the last-published issue from the DB (filled by put-to-bed);
    # the channel-neutral body lives at draft.md in S3.
    n, ship_date = await asyncio.to_thread(_resolve_latest_issue, issue_number)
    if n is None:
        return _base.JobResult(False, "❌ no published issue yet — put an issue to bed first.")
    res = await asyncio.to_thread(s3.read_issue_file, n, "draft.md")
    if not (res.get("found") and isinstance(res.get("text"), str) and res["text"].strip()):
        return _base.JobResult(
            False,
            f"❌ no `draft.md` for WT{n} in the workspace — can't draft promotion until it's built.",
        )
    publish_body = res["text"]

    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "marky", "DISCORD_CHANNEL_PROMOTION")
    if bot is None:
        return _base.JobResult(True, f"(promotion-prep skipped — {reason})", data={"posted": False})

    # Whole-job lock — promotion-prep doesn't write a workspace file (only
    # posts to #promotion), so the lock is the job name itself, mirroring
    # the `follow-up-sweep` pattern.
    try:
        with _base.job_lock([f"job:{NAME}"], NAME):
            marky_ctx = await asyncio.to_thread(
                context.build_marky_context, latest_issue=n, ship_date=ship_date
            )
            try:
                base_prompt = anthropic_client.load_prompt("marky-promotion-prep")
            except OSError as exc:
                logger.warning("promotion-prep: prompt missing: %s", exc)
                return _base.JobResult(False, f"promotion-prep prompt missing: {exc}")
            # Pre-fetch archive thread context — gives Marky multi-issue
            # arc awareness so she can write "Jamie's been pulling on
            # this since WT309" framings instead of treating every issue
            # as a one-off. Fail-soft via archive_context: a retrieval
            # outage degrades the prompt but doesn't block the job.
            thread_passages, thread_error = await asyncio.to_thread(
                archive_context.fetch_archive_context,
                publish_body[:_THREAD_QUERY_CHARS],
                k=_THREAD_CONTEXT_K,
                exclude_issue=n,
            )
            thread_block = archive_context.format_archive_context_block(
                thread_passages,
                heading="Recurring thread context",
                intro=(
                    "These are the past archive passages most semantically "
                    "related to this issue's themes (top-K via Bedrock embed "
                    "+ Cohere rerank). Use them to recognize when this issue "
                    "continues a multi-issue thread — that recognition can "
                    "anchor a sharper LinkedIn or Reddit framing (\"Jamie's "
                    "been pulling on this since WTxxx\", \"this is the third "
                    "issue this year on Apple privacy\"). If the hits look "
                    "tangential, treat this as a one-off issue and don't "
                    "force a thread framing."
                ),
                error=thread_error,
            )
            user_msg = (
                f"{context.render_block(marky_ctx)}\n\n{base_prompt}\n\n"
                f"---\n\nThe published issue (WT{n}):\n\n"
                f"```markdown\n{publish_body[: _llm_job.PROMOTION_BODY_CAP]}\n```\n\n"
                f"---\n\n{thread_block}"
            )
            with db.AgentRun("marky", trigger="promotion-prep") as agent_run:
                answer, _meta = await bot.core(latest=user_msg, history=[], model=None)
                agent_run.record_meta(_meta)
                agent_run.records_written = 1 if answer else 0
            if not answer or not answer.strip():
                return _base.JobResult(False, f"promotion-prep for WT{n}: model returned nothing.", data={"posted": False})
            posted = await ctx.post("DISCORD_CHANNEL_PROMOTION", answer, persona="marky")
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `promotion-prep` already running ({exc.holder_desc}).")
    return _base.JobResult(
        True,
        f"Marky drafted promotion content for WT{n} → #promotion." if posted else "(couldn't post Marky's drafts)",
        data={"issue_number": n, "posted": bool(posted)},
    )
