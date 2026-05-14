"""``/eddy review <text>`` — ad-hoc editorial review of pasted text.

Different from Eddy's daily ``update-draft`` review (which runs against
``draft.md`` after the projection): this is a one-shot review of
arbitrary pasted text. The result lands in ``#editorial`` under Eddy's
name, with the source text quoted at the top so Jamie can scroll back
and see what was reviewed.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..tools import db
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.review_text")

NAME = "review-text"

# Cap on pasted text length. Above this we truncate before sending to
# the LLM. 24k chars is a generous floor — beyond that the request
# isn't a "review", it's a different shape of work.
_TEXT_CAP = 24_000


async def run(
    ctx: "_base.JobContext",
    *,
    text: str,
    invoker: Optional[str] = None,
) -> "_base.JobResult":
    text = (text or "").strip()
    if not text:
        return _base.JobResult(False, "❌ no text to review — pass the draft as the `text` arg.")

    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(True, f"(review-text skipped — {reason})", data={"posted": False})

    body = text[:_TEXT_CAP]
    truncated = len(text) > _TEXT_CAP

    user_msg = (
        "You're reviewing a piece of text Jamie pasted via `/eddy review`. "
        "This is not the in-flight issue draft — treat it as a standalone "
        "piece. Apply your editorial lens: concrete suggestions, no rewrite, "
        "voice + structure + factual flags. Be specific. 1–3 short paragraphs "
        "or bullets. If it's already solid, say so plainly.\n\n"
        f"```\n{body}\n```"
    )
    if truncated:
        user_msg += f"\n\n_(Note: text was truncated at {_TEXT_CAP} chars.)_"

    with db.AgentRun("eddy", trigger="review-text") as agent_run:
        answer, _meta = await bot.core(latest=user_msg, history=[], model=None)
        agent_run.record_meta(_meta)
        agent_run.records_written = 1 if (answer and answer.strip()) else 0

    if not answer or not answer.strip():
        return _base.JobResult(False, "review-text: Eddy returned an empty response.", data={"posted": False})

    header = f"📝 **Ad-hoc review** — requested by {invoker or 'an operator'}"
    if truncated:
        header += f" _(text truncated at {_TEXT_CAP} chars)_"
    posted = await ctx.post(
        "DISCORD_CHANNEL_EDITORIAL",
        f"{header}\n\n{answer}",
        persona="eddy",
    )
    return _base.JobResult(
        True,
        f"Eddy posted a review to #editorial." if posted else "(couldn't post Eddy's review)",
        data={"posted": bool(posted), "truncated": truncated},
    )
