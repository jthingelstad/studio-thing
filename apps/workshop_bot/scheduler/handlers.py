"""Concrete scheduled-job handlers.

Each function takes a ``JobContext`` and does the work for one job. The
context exposes the team registry, channel resolution, and the agent
loop (when LLM judgment is genuinely needed). Most handlers are pure
data assembly: pull → format → post.

Conventions:

  - Handlers don't raise. The runner catches exceptions and posts a
    failure notice; handlers focus on the happy path.
  - Anything posted to Discord goes through ``ctx.post(text, ...)``
    so the runner can chunk it consistently.
  - Anything written to memory or S3 uses the same modules every
    other agent path uses (``db.insert_agent_note``, ``s3.write_issue_file``)
    so the resulting state is indistinguishable from a human-triggered
    run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from ..personas.base import is_pass_response
from ..systems.buttondown import client as buttondown
from ..tools import anthropic_client, db, issue, s3

# ---------- LLM output parsers (extracted so they're testable) ----------

# Strip ```json ... ``` markdown fences. Tolerant of stray whitespace
# and case variants (``` json, ```JSON). The LLM occasionally wraps a
# JSON-only response in fences despite being told not to.
_FENCE_RE = re.compile(
    r"\A\s*```(?:json|JSON)?\s*\n?(.*?)\n?\s*```\s*\Z",
    re.DOTALL,
)

def strip_json_fences(raw: str) -> str:
    """Strip outer ```...``` fences from an LLM response if present.
    Returns the inner payload (or the original string if there were no
    fences). Whitespace-tolerant on both ends."""
    if not raw:
        return ""
    text = raw.strip()
    match = _FENCE_RE.match(text)
    return (match.group(1) if match else text).strip()


if TYPE_CHECKING:
    from .runner import JobContext

logger = logging.getLogger("workshop.scheduler.handlers")


# ---------- helpers ----------

def _resolve_working_issue(ctx: "JobContext") -> Optional[int]:
    """The current in-flight issue number. Delegates to the shared
    ``issue.current_number`` resolver.
    """
    bot = next(iter(ctx.team.bots.values()), None)
    if bot is None:
        return None
    return issue.t_current_issue_number(bot.deps).get("working_issue_number")


# ============================================================
# Heartbeat — shared LLM-driven scheduled check-in
# ============================================================

def _heartbeats_enabled() -> bool:
    """Honor ``WORKSHOP_HEARTBEATS_ENABLED`` (default 1)."""
    raw = (os.environ.get("WORKSHOP_HEARTBEATS_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


async def heartbeat(persona: str, ctx: "JobContext") -> None:
    """A persona's scheduled wake-up turn.

    Loads ``prompts/<persona>/heartbeat.md`` as the user message, runs
    the persona's full agent loop, and posts the answer to its home
    channel — unless the answer is ``PASS`` (the default), in which case
    the heartbeat exits silently. Heartbeats are wrapped in their own
    ``db.AgentRun`` so the persona's scheduled token spend is visible
    alongside its mention-driven turns.

    Wired into ``scheduler/jobs.py`` as
    ``functools.partial(handlers.heartbeat, persona='<name>')`` per
    each persona's heartbeat JobSpec.
    """
    if not _heartbeats_enabled():
        logger.info("heartbeat: disabled via WORKSHOP_HEARTBEATS_ENABLED=0; skipping %s", persona)
        return

    bot = ctx.bot(persona)
    if bot is None:
        logger.warning("heartbeat: persona %r not registered; skipping", persona)
        return

    try:
        prompt_text = anthropic_client.load_prompt(f"{persona}-heartbeat")
    except OSError as exc:
        logger.warning("heartbeat: prompt for %r unreadable: %s", persona, exc)
        return

    model = (os.environ.get("WORKSHOP_HEARTBEAT_MODEL") or "haiku").strip() or None

    answer = ""
    with db.AgentRun(persona, trigger="heartbeat") as run:
        try:
            answer, _meta = await bot.core(
                latest=prompt_text, history=[], model=model
            )
        except Exception as exc:  # noqa: BLE001
            run.error = f"{type(exc).__name__}: {exc}"
            logger.exception("heartbeat %s: agent loop failed", persona)
            return
        run.records_written = 0 if (not answer or is_pass_response(answer)) else 1

    if not answer or is_pass_response(answer):
        logger.info("heartbeat %s: PASS", persona)
        return

    home_env = bot.home_channel_env
    if not home_env:
        logger.warning("heartbeat %s: no home_channel_env; dropping reply", persona)
        return
    channel = ctx.channel(home_env, persona=persona)
    if channel is None:
        return
    await ctx.post(channel, answer, suppress_embeds=True)


# ============================================================
# Linky
# ============================================================

async def linky_friday_curation(ctx: "JobContext") -> None:
    """LLM job — full curation pass. Reuses the agent loop with Linky's tools."""
    bot = ctx.bot("linky")
    channel = ctx.channel("DISCORD_CHANNEL_RESEARCH", persona="linky")
    if bot is None or channel is None:
        return

    prompt = (
        "Friday afternoon — Jamie writes Sunday morning. Do a full curation pass "
        "on the unread Pinboard queue: pinboard.unread (limit 200), group "
        "into 2-5 themes, tag each item ✦/·/⊘, and flag anything paywalled or "
        "context-dependent. Search the archive when a bookmark feels familiar — "
        "has Jamie covered this territory recently? After you write the pass, "
        "save it with `memory.remember(kind='context', key='linky:friday-curation')` "
        "so Jamie can pull it up by name. Plain markdown."
    )
    answer, meta = await bot.core(latest=prompt, history=[], model=None)
    await ctx.post(channel, answer or "(curation pass produced nothing)", suppress_embeds=True)


# ============================================================
# Marky
# ============================================================

async def marky_weekly_subscriber_report(ctx: "JobContext") -> None:
    """Pure code: subscriber recent + churn → #promotion."""
    channel = ctx.channel("DISCORD_CHANNEL_PROMOTION", persona="marky")
    if channel is None:
        return

    try:
        recent = await asyncio.to_thread(buttondown.recent_subscribers, limit=25)
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"Weekly subscriber report skipped — Buttondown fetch failed: `{exc}`")
        return
    try:
        churn = await asyncio.to_thread(buttondown.recent_unsubscribes, limit=15)
    except Exception as exc:  # noqa: BLE001
        churn = []
        logger.warning("buttondown.recent_unsubscribes failed: %s", exc)

    new_seen = 0
    new_persisted = 0
    for sub in recent:
        sid = str(sub.get("id") or "")
        if not sid:
            continue
        new_seen += 1
        if db.upsert_subscriber_event(
            external_id=sid,
            email_hash=sub.get("email_hash", ""),
            event_type="created",
            event_date=sub.get("created_at") or "",
            metadata={"source": sub.get("source"), "domain": sub.get("email_domain")},
        ):
            new_persisted += 1
    for sub in churn:
        sid = str(sub.get("id") or "")
        if not sid:
            continue
        db.upsert_subscriber_event(
            external_id=sid,
            email_hash=sub.get("email_hash", ""),
            event_type="unsubscribed",
            event_date=sub.get("created_at") or "",
            metadata={"source": sub.get("source"), "domain": sub.get("email_domain")},
        )

    sources: dict[str, int] = {}
    for sub in recent:
        src = sub.get("source") or "unknown"
        sources[src] = sources.get(src, 0) + 1
    src_line = ", ".join(f"{s}: {n}" for s, n in sorted(sources.items(), key=lambda kv: -kv[1]))

    lines = [
        "**Weekly subscriber report**",
        f"- New (last 25): {len(recent)} ({new_persisted} new this week)",
        f"- Sources: {src_line or '(none)'}",
        f"- Recent churn: {len(churn)}",
    ]
    await ctx.post(channel, "\n".join(lines))


async def patty_thursday_member_json(ctx: "JobContext") -> None:
    """LLM job. Patty composes the supporter CTA + progress update and writes
    them to the in-flight issue's member.json on S3."""
    bot = ctx.bot("patty")
    channel = ctx.channel("DISCORD_CHANNEL_SUPPORTERS", persona="patty")
    if bot is None or channel is None:
        return

    issue = _resolve_working_issue(ctx)
    if issue is None:
        await ctx.post(channel, "Couldn't resolve the working issue number; skipping member.json write.")
        return

    prompt = (
        f"Time to write member.json for issue #{issue} (the in-flight issue, "
        "not in your archive corpus yet). Steps:\n"
        "1. `site.support_state` for the current nonprofit, supporter count.\n"
        "2. `stripe.year_to_date` for the live dollars-raised figure (and the "
        "configured nonprofit short name for cross-check).\n"
        "3. Search the archive for the last 3-4 supporter CTAs Jamie shipped — "
        "voice match them, do not echo last week's framing.\n"
        "4. Compose two pieces, both in **Thingy's** voice (the only agent "
        "readers know — Patty is invisible). Warm, personal, on Jamie's "
        "behalf; never Jamie's first person, never sales-y.\n"
        "   - **CTA** (60-120 words, plain markdown, no headings). Names the "
        "current nonprofit and what they do; warm acknowledgment of existing "
        "supporters. Don't include a sign-off — Jamie's pipeline attributes "
        "it to Thingy.\n"
        "   - **Progress update** (~80 words, addressed to current supporters). "
        "What their support has funded this year, in concrete terms — use the "
        "live total from stripe.year_to_date.\n"
        "5. Return ONLY a JSON object with shape "
        "`{\"cta\": \"...\", \"progress\": \"...\", \"nonprofit\": \"...\"}` — "
        "no markdown fences, no commentary."
    )

    answer, meta = await bot.core(latest=prompt, history=[], model=None)
    raw = strip_json_fences(answer or "")
    try:
        parsed = json.loads(raw)
        cta = parsed.get("cta", "").strip()
        progress = parsed.get("progress", "").strip()
        nonprofit = parsed.get("nonprofit", "").strip()
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"member.json compose returned non-JSON: `{exc}`. Raw output saved to memory.")
        db.insert_agent_note(
            agent_name="patty",
            kind="todo",
            key="patty:member-json-fallback",
            content=raw,
            related_issue=issue,
        )
        return

    payload = json.dumps(
        {
            "cta": cta,
            "progress": progress,
            "nonprofit": nonprofit,
            "issue_number": issue,
            "composed_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
        ensure_ascii=False,
    )
    try:
        s3.write_issue_file(issue, "member.json", payload)
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"member.json compose ok, but S3 write failed: `{exc}`")
        db.insert_agent_note(
            agent_name="patty",
            kind="todo",
            key="patty:member-json-pending",
            content=payload,
            related_issue=issue,
        )
        return

    db.insert_agent_note(
        agent_name="patty",
        kind="todo",
        key="patty:member-json-this-week",
        content=payload,
        related_issue=issue,
        metadata={"job_id": "patty-thursday-member-json"},
    )

    summary = (
        f"📬 Wrote `member.json` for issue **#{issue}**.\n"
        f"- Nonprofit: {nonprofit or '(unspecified)'}\n"
        f"- CTA length: {len(cta)} chars\n"
        f"- Progress length: {len(progress)} chars\n"
        f"_Shortcuts will pick this up Sunday._"
    )
    await ctx.post(channel, summary)


