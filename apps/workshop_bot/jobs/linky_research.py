"""``/linky research <url>`` — ad-hoc per-URL research.

Like ``pinboard-scan`` but for a single URL Jamie pastes (rather than
a feed item Linky surfaced). Skips the cross-source / sightings /
popular-seen machinery (none of which applies to a one-off query) and
just runs Linky's agent loop against the URL with the per-link card
prompt. Result lands in ``#research``.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..tools import db
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.linky_research")

NAME = "linky-research"


async def run(
    ctx: "_base.JobContext",
    *,
    url: str,
    invoker: Optional[str] = None,
) -> "_base.JobResult":
    url = (url or "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return _base.JobResult(False, "❌ pass a full http(s) URL.")

    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "linky", "DISCORD_CHANNEL_RESEARCH")
    if bot is None:
        return _base.JobResult(True, f"(linky-research skipped — {reason})", data={"posted": False})

    user_msg = (
        f"Jamie pasted this URL via `/linky research` and wants your read:\n\n"
        f"<{url}>\n\n"
        f"Apply your usual per-link lens — fetch it, decide whether it's "
        f"interesting to Jamie (you know his archive), check archive resonance "
        f"if relevant, and post the card to #research. If it's not interesting, "
        f"say so plainly and why. Don't bookmark it — that's Jamie's call."
    )
    with db.AgentRun("linky", trigger="linky-research") as agent_run:
        answer, _meta = await bot.core(latest=user_msg, history=[], model=None)
        agent_run.record_meta(_meta)
        agent_run.records_written = 1 if (answer and answer.strip()) else 0

    if not answer or not answer.strip():
        return _base.JobResult(False, "linky-research: Linky returned an empty response.", data={"posted": False})

    header = f"🔎 **Ad-hoc research** — requested by {invoker or 'an operator'}"
    posted = await ctx.post(
        "DISCORD_CHANNEL_RESEARCH",
        f"{header}\n\n{answer}",
        persona="linky",
    )
    return _base.JobResult(
        True,
        f"Linky researched {url} → #research." if posted else "(couldn't post Linky's research)",
        data={"url": url, "posted": bool(posted)},
    )
