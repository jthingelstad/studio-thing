"""``promotion-prep`` (Marky) — syndication drafts for the latest issue.

Triggered when the ``rss-check`` job sees a new issue number in
``weekly.thingelstad.com/feed.xml`` (or manually). Operates on the most
recently *published* issue's ``publish.md`` in the S3 workspace —
independent of the in-flight issue. Marky drafts, in Jamie's voice,
**2–3 alternative framings per platform** (LinkedIn ~100–200 words; an
r/WeeklyThing megathread; one per-link Reddit thread per Notable item),
posts them all to ``#promotion``, and **never auto-posts** anywhere —
Jamie copies / edits / publishes.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..tools import anthropic_client, context, db, rss, s3
from . import _base, _compose

logger = logging.getLogger("workshop.jobs.promotion_prep")

NAME = "promotion-prep"


def _resolve_latest_issue(explicit: Optional[int]) -> tuple[Optional[int], Optional[str]]:
    if explicit is not None:
        return int(explicit), None
    try:
        li = rss.latest_published_issue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("promotion-prep: RSS lookup failed: %s", exc)
        return None, None
    if not li:
        return None, None
    return li.get("number"), li.get("ship_date")


async def run(ctx: "_base.JobContext", *, issue_number: Optional[int] = None) -> "_base.JobResult":
    n, ship_date = _resolve_latest_issue(issue_number)
    if n is None:
        return _base.JobResult(False, "❌ couldn't determine the latest published issue from the RSS feed.")
    res = s3.read_issue_file(n, "publish.md")
    if not (res.get("found") and isinstance(res.get("text"), str) and res["text"].strip()):
        return _base.JobResult(
            False,
            f"❌ no `publish.md` for WT{n} in the workspace — can't draft promotion until it's built.",
        )
    publish_body = res["text"]

    bot, channel, reason = _compose.resolve_bot_and_channel(ctx, "marky", "DISCORD_CHANNEL_PROMOTION")
    if bot is None:
        return _base.JobResult(True, f"(promotion-prep skipped — {reason})", data={"posted": False})

    asset = f"{n}/promotion-drafts"  # not a real file — just a lock key so a re-fire bounces
    try:
        with _base.job_lock([asset], NAME):
            marky_ctx = context.build_marky_context(latest_issue=n, ship_date=ship_date)
            try:
                base_prompt = anthropic_client.load_prompt("marky-promotion-prep")
            except OSError as exc:
                logger.warning("promotion-prep: prompt missing: %s", exc)
                return _base.JobResult(False, f"promotion-prep prompt missing: {exc}")
            user_msg = (
                f"{context.render_block(marky_ctx)}\n\n{base_prompt}\n\n"
                f"---\n\nThe published issue (WT{n}):\n\n"
                f"```markdown\n{publish_body[: _compose.ISSUE_BODY_CAP + 8000]}\n```"
            )
            with db.AgentRun("marky", trigger="promotion-prep") as agent_run:
                answer, _meta = await bot.core(latest=user_msg, history=[], model=None)
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
