"""garden-checkin — Eddy's tending pass over the idea garden.

Not a nudge anymore: each pass Eddy does real clustering work. The job builds
the garden context in code — a batch of ungrouped open seeds plus the existing
open clusters — and runs Eddy's agent loop (persona-default Sonnet) with the
``seeds__*`` tools so he clusters, curates (tags/titles only — Jamie's seed
bodies are verbatim-sacred), and connects substantial clusters to the archive.
He ends with a verdict: ``PASS`` (garden tidy — any clustering he did still
sticks; nothing is posted) or a compact report to #editorial with at most one
ripe candidate. He proposes graduation; Jamie graduates from the /seeds page.

Fires Monday 09:00 CT (cron id ``garden-checkin``) and on demand from the
/seeds page's "Tend garden" button. With zero ungrouped seeds the pass is a
ripeness review over the existing clusters.
"""

from __future__ import annotations

import logging

from ..personas.base import is_pass_response
from ..tools import db
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.garden_checkin")

NAME = "garden-checkin"

# How many ungrouped seeds Eddy is shown per pass. The garden can hold a couple
# hundred loose seeds; the pass is incremental — the context block tells him
# how many remain beyond the batch so he knows the rest come around later.
BATCH_CAP = 60

# Per-seed body truncation in the context block (characters). Enough to grasp
# the idea for clustering; `seeds__get` has the full text when he needs it.
BODY_CAP = 280


def _seed_line(seed: dict) -> str:
    body = " ".join((seed.get("body") or "").split())
    if len(body) > BODY_CAP:
        body = body[:BODY_CAP].rstrip() + "…"
    title = f" — {seed['title']}" if seed.get("title") else ""
    tags = f" [tags: {seed['tags']}]" if seed.get("tags") else ""
    return f"- seed #{seed['id']}{title}{tags}\n  {body}"


def _garden_context(ungrouped: list[dict], clusters: list[dict]) -> str:
    """The garden state block appended to the tending prompt — built in code
    so Eddy spends his loop on clustering, not on paging through tools."""
    lines = ["## The garden right now", ""]

    if clusters:
        lines.append(f"### Open clusters ({len(clusters)})")
        lines.append("")
        for c in clusters:
            count = len(db.seed_list(cluster_id=c["id"]))
            note = f" — {c['note']}" if c.get("note") else ""
            lines.append(f"- cluster #{c['id']} \"{c['label']}\" ({count} seeds){note}")
    else:
        lines.append("### Open clusters")
        lines.append("")
        lines.append("(none yet — every cluster this pass creates is a new one)")
    lines.append("")

    batch = ungrouped[:BATCH_CAP]
    remaining = len(ungrouped) - len(batch)
    if batch:
        lines.append(f"### Ungrouped open seeds — this pass's batch ({len(batch)})")
        lines.append("")
        for s in batch:
            lines.append(_seed_line(s))
        lines.append("")
        if remaining > 0:
            lines.append(
                f"({remaining} more ungrouped seeds remain beyond this batch — the "
                "pass is incremental; they'll come around on later passes.)")
        else:
            lines.append("(That's every ungrouped seed — nothing waiting beyond this batch.)")
    else:
        lines.append("### Ungrouped open seeds")
        lines.append("")
        lines.append("(none — this pass is a ripeness review over the clusters above)")
    return "\n".join(lines)


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    # Oldest first, so the longest-waiting seeds get tended before new ones.
    ungrouped = [s for s in db.seed_list(status="open") if s.get("cluster_id") is None]
    ungrouped.reverse()
    clusters = db.seed_cluster_list(status="open")
    if not ungrouped and not clusters:
        return _base.JobResult(True, "(garden-checkin: empty garden — nothing to tend)")

    bot, channel, reason = _llm_job.resolve_bot_and_channel(
        ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(True, f"(garden-checkin: eddy unavailable — {reason})")

    try:
        prompt = anthropic_client.load_prompt("eddy-garden-tend")
    except OSError as exc:
        return _base.JobResult(False, f"garden-checkin: garden-tend prompt missing: {exc}")

    user_msg = f"{prompt}\n\n---\n\n{_garden_context(ungrouped, clusters)}"
    reply = ""
    try:
        with db.AgentRun("eddy", trigger="garden-tend") as agent_run:
            reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
            agent_run.record_meta(_meta)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
    except Exception:  # noqa: BLE001
        logger.exception("garden-checkin: tending pass failed")
        return _base.JobResult(False, "garden-checkin: tending pass failed")

    if reply and reply.strip() and not is_pass_response(reply):
        await ctx.post(channel, reply.strip(), persona="eddy")
        return _base.JobResult(
            True, "garden-checkin: posted the tending report", data={"posted": True})
    logger.info("garden-checkin: PASS (garden tidy — clustering work, if any, is saved)")
    return _base.JobResult(True, "garden-checkin: PASS (garden tidy)", data={"posted": False})
