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
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from ..tools import buttondown, db, pinboard, s3, tinylytics

# ---------- LLM output parsers (extracted so they're testable) ----------

# Strip ```json ... ``` markdown fences. Tolerant of stray whitespace
# and case variants (``` json, ```JSON). The LLM occasionally wraps a
# JSON-only response in fences despite being told not to.
_FENCE_RE = re.compile(
    r"\A\s*```(?:json|JSON)?\s*\n?(.*?)\n?\s*```\s*\Z",
    re.DOTALL,
)

# Markdown links Linky's research-pass digest emits: [title](url). Used
# as a fallback when the explicit RESEARCHED: line is malformed.
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")


def strip_json_fences(raw: str) -> str:
    """Strip outer ```...``` fences from an LLM response if present.
    Returns the inner payload (or the original string if there were no
    fences). Whitespace-tolerant on both ends."""
    if not raw:
        return ""
    text = raw.strip()
    match = _FENCE_RE.match(text)
    return (match.group(1) if match else text).strip()


def parse_researched_line(answer: str) -> tuple[Optional[list[str]], str]:
    """Pull the `RESEARCHED: [...]` line out of Linky's research digest.

    Returns ``(urls, body)`` where ``urls`` is a list of researched URLs
    (or None if the line is missing/malformed) and ``body`` is the
    digest with the RESEARCHED line removed. When the line is malformed,
    falls back to extracting URLs from markdown link syntax in the body
    so the runtime can still mark items researched and avoid an
    indefinite stall on the same batch.
    """
    body = answer
    explicit: Optional[list[str]] = None
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("RESEARCHED:"):
            payload = stripped.split(":", 1)[1].strip()
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, list):
                    explicit = [str(u) for u in parsed]
            except (json.JSONDecodeError, ValueError):
                explicit = None
            body = "\n".join(
                ln for ln in answer.splitlines()
                if ln.strip().upper() != stripped.upper()
            ).strip()
            break
    if explicit is not None:
        return explicit, body
    # Fallback: pull URLs from any `[text](url)` markdown links the LLM
    # included in the digest. Better to mark them researched than to
    # have the same batch resurface every run.
    fallback = _MD_LINK_RE.findall(body)
    if fallback:
        # Dedupe while preserving order.
        seen: set[str] = set()
        out: list[str] = []
        for u in fallback:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out, body
    return None, body

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
        unread = await asyncio.to_thread(pinboard.all_unread, limit=200)
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
    """Hybrid. Fetch Pinboard's popular feed every 6 hours, dedup against
    URLs we've already shown Jamie, then ask Linky (LLM) to filter what's
    left to items Jamie would actually be interested in. Post only the
    curated subset; if nothing passes the filter, post nothing.

    Mark every fetched item as seen regardless of LLM verdict — better to
    let one borderline item slip past than to spam Jamie with the same
    items every 6 hours.
    """
    channel = ctx.channel("DISCORD_CHANNEL_RESEARCH")
    if channel is None:
        return

    try:
        items = await asyncio.to_thread(pinboard.popular, limit=30)
    except Exception as exc:  # noqa: BLE001
        logger.warning("popular scan: fetch failed: %s", exc)
        return

    new_items = db.filter_unseen_popular(items)
    if not new_items:
        logger.info("popular scan: %d items, 0 new — nothing to post", len(items))
        return

    bot = ctx.bot("linky")
    if bot is None:
        # No Linky to judge; mark seen and move on.
        db.mark_popular_seen(new_items)
        return

    item_block = "\n".join(
        f"- {it.get('title', '(untitled)')!r}  {it.get('url', '')}"
        f"  (saved by {it.get('posted_by', '?')})"
        for it in new_items
    )
    prompt = (
        "6-hour check on Pinboard's popular feed. Here are NEW items since "
        "your last scan (you've never shown these to Jamie):\n\n"
        f"{item_block}\n\n"
        "For each, judge whether Jamie would actually want to see it. Use "
        "`search_archive` to check whether he's covered the topic — skip "
        "anything that just rehashes recent ground. Use `recall(kind=\"theme\")` "
        "to see what themes you've been tracking — items that connect to a "
        "live theme are extra interesting. **Default is to skip.** Better to "
        "post 0 items than to spam.\n\n"
        "If you find items worth surfacing, return a short markdown list, "
        "one bullet per item, formatted exactly like:\n"
        "  - [title](url) — one sentence on why it caught your eye\n\n"
        "If nothing rises above the bar, return exactly: NONE"
    )

    try:
        answer, meta = await bot.core(latest=prompt, history=[], model=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("popular scan: LLM filter failed: %s", exc)
        db.mark_popular_seen(new_items)
        return

    answer = (answer or "").strip()
    db.mark_popular_seen(new_items)  # always mark, regardless of judgment

    if not answer or answer.upper().startswith("NONE"):
        logger.info("popular scan: %d new items, all PASSed by Linky", len(new_items))
        return

    body = (
        f"Popular on Pinboard right now (filtered to what looks relevant):\n\n{answer}"
    )
    await ctx.post(channel, body)


async def linky_research_unread(ctx: "JobContext") -> None:
    """LLM job. Pick a few unresearched items from Jamie's `to read` queue,
    fetch each URL, write a short research note, post the digest. Marks
    each item researched so the next run picks up where this left off.
    """
    channel = ctx.channel("DISCORD_CHANNEL_RESEARCH")
    bot = ctx.bot("linky")
    if channel is None or bot is None:
        return

    try:
        unread = await asyncio.to_thread(pinboard.all_unread, limit=200)
    except Exception as exc:  # noqa: BLE001
        logger.warning("to-read research: Pinboard fetch failed: %s", exc)
        return

    if not unread:
        return

    candidate_urls = [
        (p.get("url"), p.get("title"), p.get("tags"))
        for p in unread
        if p.get("url")
    ]
    unresearched = db.filter_unresearched_urls([u for u, _, _ in candidate_urls])
    if not unresearched:
        logger.info("to-read research: nothing left unresearched (%d in queue)", len(unread))
        return

    # Hand Linky a manageable batch and let her judgment pick which to actually
    # read. Limit batch size so a single run doesn't burn a huge token budget.
    batch_urls = unresearched[:8]
    by_url = {u: (t, tg) for u, t, tg in candidate_urls if u in set(batch_urls)}

    catalog_block = "\n".join(
        f"- {by_url[u][0] or '(untitled)'}  {u}  [tags: {by_url[u][1] or '(none)'}]"
        for u in batch_urls
    )

    prompt = (
        "Time to do some research on Jamie's `to read` pile. Here are items "
        "you haven't yet researched:\n\n"
        f"{catalog_block}\n\n"
        "Pick the 2-3 most promising. For each one you pick:\n"
        "  1. `fetch_url` to actually read it.\n"
        "  2. Write a 2-3 sentence research note: what the piece actually "
        "says, what's the angle a Weekly Thing reader would care about, and "
        "a confidence flag (✦ Notable / · Briefly / ⊘ skip).\n\n"
        "Return your output as a markdown list, one block per item, formatted "
        "exactly like:\n"
        "  ### [title](url) ✦\n"
        "  Two-or-three-sentence research note.\n\n"
        "Then on a separate final line, return a JSON array of just the URLs "
        "you actually researched (so the runtime can mark them done), prefixed "
        "with the literal token `RESEARCHED:` — for example:\n"
        "  RESEARCHED: [\"https://...\", \"https://...\"]\n\n"
        "If nothing in the batch is worth a research pass, return exactly: NONE"
    )

    try:
        answer, meta = await bot.core(latest=prompt, history=[], model=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("to-read research: LLM call failed: %s", exc)
        return

    answer = (answer or "").strip()
    if not answer or answer.upper().startswith("NONE"):
        # Nothing worth posting; don't mark anything researched so they
        # come back next run.
        logger.info("to-read research: Linky found nothing worth surfacing in batch")
        return

    # Pull the RESEARCHED line out of the answer and use it to mark
    # items. If the line is missing or malformed, parse_researched_line
    # falls back to URLs found in the digest's markdown links so a bad
    # batch doesn't stall the job indefinitely.
    researched_urls, body_text = parse_researched_line(answer)
    if researched_urls is None:
        logger.warning("to-read research: no usable RESEARCHED list; not marking any URLs done")
        researched_urls = []

    for url in researched_urls:
        title = by_url.get(url, (None, None))[0]
        db.mark_url_researched(url=url, title=title, summary=body_text[:2000])

    if body_text:
        await ctx.post(channel, f"Research notes from the to-read pile:\n\n{body_text}")


# ============================================================
# Marky
# ============================================================

async def marky_daily_engagement(ctx: "JobContext") -> None:
    """Pure code: trailing-7-day Tinylytics + subscriber counts → #chatter."""
    channel = ctx.channel("DISCORD_CHANNEL_CHATTER")
    if channel is None:
        return

    summary = await asyncio.to_thread(tinylytics.safe_summary, days=7)
    counts = {}
    try:
        counts = await asyncio.to_thread(buttondown.counts)
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
    channel = ctx.channel("DISCORD_CHANNEL_SUPPORTERS")
    if bot is None or channel is None:
        return

    issue = _resolve_working_issue(ctx)
    if issue is None:
        await ctx.post(channel, "Couldn't resolve the working issue number; skipping member.json write.")
        return

    prompt = (
        f"Time to write member.json for issue #{issue} (the in-flight issue, "
        "not in your archive corpus yet). Steps:\n"
        "1. `get_support_state` for the current nonprofit, supporter count, "
        "dollars raised.\n"
        "2. Search the archive for the last 3-4 supporter CTAs Jamie shipped — "
        "voice match them, do not echo last week's framing.\n"
        "3. Compose two pieces, both in **Thingy's** voice (the only agent "
        "readers know — Patty is invisible). Warm, personal, on Jamie's "
        "behalf; never Jamie's first person, never sales-y.\n"
        "   - **CTA** (60-120 words, plain markdown, no headings). Names the "
        "current nonprofit and what they do; warm acknowledgment of existing "
        "supporters. Don't include a sign-off — Jamie's pipeline attributes "
        "it to Thingy.\n"
        "   - **Progress update** (~80 words, addressed to current supporters). "
        "What their support has funded this year, in concrete terms.\n"
        "4. Return ONLY a JSON object with shape "
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
