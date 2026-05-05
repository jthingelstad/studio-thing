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

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from ..tools import buttondown, db, pinboard, s3, tinylytics

if TYPE_CHECKING:
    from .runner import JobContext

logger = logging.getLogger("workshop.scheduler.handlers")


# ---------- helpers ----------

def _resolve_working_issue(ctx: "JobContext") -> Optional[int]:
    """The current in-flight issue number. Tries S3 first, falls back to
    ``corpus.latest_issue_number + 1``.
    """
    try:
        ws = s3.list_workspaces()
        s3_max = ws.get("current_issue_number")
    except Exception as exc:  # noqa: BLE001
        logger.warning("scheduler: S3 list_workspaces failed: %s", exc)
        s3_max = None

    published = None
    bot = next(iter(ctx.team.bots.values()), None)
    if bot is not None and bot.deps.corpus is not None:
        published = bot.deps.corpus.latest_issue_number

    if s3_max is not None and (published is None or s3_max > published):
        return s3_max
    if published is not None:
        return published + 1
    return None


# ============================================================
# Linky
# ============================================================

async def linky_wednesday_check(ctx: "JobContext") -> None:
    """Pure code. Count items added since Sunday; ping if light."""
    channel = ctx.channel("DISCORD_CHANNEL_RESEARCH")
    if channel is None:
        return

    try:
        unread = pinboard.all_unread(limit=200)
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"Wednesday check skipped — Pinboard fetch failed: `{exc}`")
        return

    week_count = len(unread)
    if week_count == 0:
        msg = "Wednesday check-in: nothing in the unread queue. Want to send anything my way?"
    elif week_count < 8:
        msg = (
            f"Wednesday check-in: only **{week_count}** items in the unread queue. "
            "Want to send anything my way? Or want me to scan the popular feed for ideas?"
        )
    else:
        # Group by tag to give a quick theme preview.
        tag_counts: dict[str, int] = {}
        for p in unread:
            for t in (p.get("tags") or "").split():
                tag_counts[t] = tag_counts.get(t, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda kv: -kv[1])[:5]
        tag_line = ", ".join(f"`{t}` ({n})" for t, n in top_tags) or "(no tags yet)"
        msg = (
            f"Wednesday check-in: **{week_count}** items in the unread queue.\n"
            f"Top tags: {tag_line}\n"
            "Looking healthy. Friday curation pass will go deeper."
        )

    await ctx.post(channel, msg)
    db.insert_agent_note(
        agent_name="linky",
        kind="observation",
        key="linky:wednesday-check",
        content=msg,
        metadata={"week_count": week_count, "fired_at": datetime.now(timezone.utc).isoformat()},
    )


async def linky_friday_curation(ctx: "JobContext") -> None:
    """LLM job — full curation pass. Reuses the agent loop with Linky's tools."""
    bot = ctx.bot("linky")
    channel = ctx.channel("DISCORD_CHANNEL_RESEARCH")
    if bot is None or channel is None:
        return

    prompt = (
        "Friday afternoon — Jamie writes Sunday morning. Do a full curation pass "
        "on the unread Pinboard queue: fetch_pinboard_unread (limit 200), group "
        "into 2-5 themes, tag each item ✦/·/⊘, and flag anything paywalled or "
        "context-dependent. Search the archive when a bookmark feels familiar — "
        "has Jamie covered this territory recently? After you write the pass, "
        "save it with `remember(kind='context', key='linky:friday-curation')` so "
        "Jamie can pull it up by name. Plain markdown."
    )
    answer, meta = await bot.core(latest=prompt, history=[], model=None)
    await ctx.post(channel, answer or "(curation pass produced nothing)")


async def linky_popular_scan(ctx: "JobContext") -> None:
    """Pure code. Fetch Pinboard's popular feed; post anything that doesn't
    already match recent archive coverage."""
    channel = ctx.channel("DISCORD_CHANNEL_RESEARCH")
    if channel is None:
        return

    try:
        items = pinboard.popular(limit=20)
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"Popular feed scan skipped — fetch failed: `{exc}`")
        return

    if not items:
        await ctx.post(channel, "Pinboard popular feed was empty just now.")
        return

    lines = [f"Popular on Pinboard ({len(items)} items):"]
    for item in items:
        title = item.get("title", "").strip() or "(untitled)"
        url = item.get("url", "")
        lines.append(f"- [{title}]({url})")
    body = "\n".join(lines)
    body += "\n\n_(Anything catch your eye? Send to me with `@Linky` and I'll dig in.)_"
    await ctx.post(channel, body)
    db.insert_agent_note(
        agent_name="linky",
        kind="observation",
        key="linky:popular-scan",
        content=body,
        metadata={"item_count": len(items), "fired_at": datetime.now(timezone.utc).isoformat()},
    )


# ============================================================
# Marky
# ============================================================

async def marky_daily_engagement(ctx: "JobContext") -> None:
    """Pure code: trailing-7-day Tinylytics + subscriber counts → #chatter."""
    channel = ctx.channel("DISCORD_CHANNEL_CHATTER")
    if channel is None:
        return

    summary = tinylytics.safe_summary(days=7)
    counts = {}
    try:
        counts = buttondown.counts()
    except Exception as exc:  # noqa: BLE001
        logger.warning("buttondown.counts failed: %s", exc)

    lines = ["**Daily engagement** (trailing 7 days)"]
    stats = summary.get("stats")
    if isinstance(stats, dict) and "error" not in stats:
        # Tinylytics shape varies; render whatever's there compactly.
        for k, v in list(stats.items())[:6]:
            lines.append(f"- {k}: {v}")
    elif isinstance(stats, dict):
        lines.append(f"- stats: ⚠️ {stats.get('error')}")

    pages = summary.get("top_pages") or []
    if isinstance(pages, list) and pages:
        lines.append("")
        lines.append("Top pages:")
        for p in pages[:3]:
            url = p.get("path") or p.get("url") or "?"
            views = p.get("views") or p.get("count") or "?"
            lines.append(f"- {url} — {views}")

    if counts:
        lines.append("")
        lines.append(
            f"Subscribers: **{counts.get('total', '?')}** total, "
            f"**{counts.get('premium', '?')}** premium, "
            f"**{counts.get('unsubscribed', '?')}** lifetime unsubscribed"
        )

    await ctx.post(channel, "\n".join(lines))


async def marky_weekly_subscriber_report(ctx: "JobContext") -> None:
    """Pure code: subscriber recent + churn → #promotion."""
    channel = ctx.channel("DISCORD_CHANNEL_PROMOTION")
    if channel is None:
        return

    try:
        recent = buttondown.recent_subscribers(limit=25)
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"Weekly subscriber report skipped — Buttondown fetch failed: `{exc}`")
        return
    try:
        churn = buttondown.recent_unsubscribes(limit=15)
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


async def marky_thursday_member_json(ctx: "JobContext") -> None:
    """LLM job. Compose CTA + progress update, write to S3 member.json."""
    bot = ctx.bot("marky")
    channel = ctx.channel("DISCORD_CHANNEL_PROMOTION")
    if bot is None or channel is None:
        return

    issue = _resolve_working_issue(ctx)
    if issue is None:
        await ctx.post(channel, "Couldn't resolve the working issue number; skipping member.json write.")
        return

    prompt = (
        f"Time to write member.json for issue #{issue} (the in-flight issue, not "
        "in your archive corpus yet). Steps:\n"
        "1. `get_support_state` for the current nonprofit, supporter count, "
        "dollars raised.\n"
        "2. `recall(agent_name='patty')` to pick up tonal calls Patty has noted.\n"
        "3. Search the archive for the last 3-4 supporter CTAs Jamie shipped — "
        "do not echo last week's framing.\n"
        "4. Compose two pieces:\n"
        "   - **CTA** (60-120 words, plain markdown, no headings, invisible "
        "narrator). Names the current nonprofit and what they do; warm "
        "acknowledgment of existing supporters.\n"
        "   - **Progress update** (~80 words, addressed to current supporters). "
        "What their support has funded this year, in concrete terms.\n"
        "5. Return ONLY a JSON object with shape "
        "`{\"cta\": \"...\", \"progress\": \"...\", \"nonprofit\": \"...\"}` — "
        "no markdown fences, no commentary."
    )

    answer, meta = await bot.core(latest=prompt, history=[], model=None)
    raw = (answer or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[len("json"):].strip()
    try:
        parsed = json.loads(raw)
        cta = parsed.get("cta", "").strip()
        progress = parsed.get("progress", "").strip()
        nonprofit = parsed.get("nonprofit", "").strip()
    except Exception as exc:  # noqa: BLE001
        await ctx.post(channel, f"member.json compose returned non-JSON: `{exc}`. Raw output saved to memory.")
        db.insert_agent_note(
            agent_name="marky",
            kind="todo",
            key="marky:member-json-fallback",
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
            agent_name="marky",
            kind="todo",
            key="marky:member-json-pending",
            content=payload,
            related_issue=issue,
        )
        return

    db.insert_agent_note(
        agent_name="marky",
        kind="todo",
        key="marky:member-json-this-week",
        content=payload,
        related_issue=issue,
        metadata={"job_id": "marky-thursday-member-json"},
    )

    summary = (
        f"📬 Wrote `member.json` for issue **#{issue}**.\n"
        f"- Nonprofit: {nonprofit or '(unspecified)'}\n"
        f"- CTA length: {len(cta)} chars\n"
        f"- Progress length: {len(progress)} chars\n"
        f"_Shortcuts will pick this up Sunday._"
    )
    await ctx.post(channel, summary)


# ============================================================
# Eddy
# ============================================================

async def eddy_saturday_prep(ctx: "JobContext") -> None:
    """Mostly pure code: recall recent preferences/themes, post to #editorial.

    The LLM is only used if there's enough material that a synthesis is
    actually useful; otherwise we just list what we found.
    """
    channel = ctx.channel("DISCORD_CHANNEL_EDITORIAL")
    if channel is None:
        return

    prefs = db.query_agent_notes(agent_name="eddy", kind="preference", limit=8)
    themes = db.query_agent_notes(agent_name="eddy", kind="theme", limit=8)
    if not prefs and not themes:
        await ctx.post(channel, "Saturday prep: nothing in memory to surface this week.")
        return

    lines = ["**Saturday prep** — what I'm carrying into tomorrow's writing:"]
    if prefs:
        lines.append("")
        lines.append("_Preferences:_")
        for n in prefs:
            label = f" `{n['key']}`" if n.get("key") else ""
            lines.append(f"- {n['content']}{label}")
    if themes:
        lines.append("")
        lines.append("_Themes I'm tracking:_")
        for n in themes:
            label = f" `{n['key']}`" if n.get("key") else ""
            lines.append(f"- {n['content']}{label}")
    await ctx.post(channel, "\n".join(lines))
