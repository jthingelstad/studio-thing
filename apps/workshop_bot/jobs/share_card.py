"""Share card — the **promote** phase surface (`#promotion`, Marky).

Phase 3 of the publishing spine (`docs/publishing-process.md`): "is the
published issue out in the world?" It targets the **last-published** issue
(the concurrency: WT349 in Build ‖ WT348 in Share), and is the per-issue
syndication launchpad — LinkedIn, the r/WeeklyThing megathread + per-link
threads — with active-campaign + metrics shown as **read-only context** (the
Campaigns *program* intersecting here). Standing campaign management lives in
`/marky campaign …`, not on this card.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord

from ..tools import db
from . import _base, _cards

logger = logging.getLogger("workshop.jobs.share_card")

NAME = "share-card"
KIND = "share"

BTN_DRAFT = "share:draft"          # promotion-prep (LinkedIn + Reddit drafts)
BTN_METRICS = "share:metrics"      # daily-metrics refresh
BTN_REFRESH = "share:refresh"


def gather_state() -> dict:
    """State for the Share card — the last-published issue + campaign context.
    Synchronous (DB only); async callers wrap in `asyncio.to_thread`."""
    issue = db.get_latest_issue()
    if issue is None:
        return {"issue_number": None}
    try:
        campaigns = db.active_campaigns_with_age()
    except Exception:  # noqa: BLE001
        campaigns = []
    return {
        "issue_number": int(issue["number"]),
        "subject": (issue.get("subject") or "").strip(),
        "publish_date": (issue.get("publish_date") or "")[:10],
        "absolute_url": issue.get("absolute_url") or "",
        "has_audio": bool(issue.get("audio_url")),
        "link_count": issue.get("link_count") or 0,
        "campaigns": campaigns,
    }


def render_syndication_lines(state: dict) -> list[str]:
    # We don't track posted-state for syndication (promotion-prep drafts, never
    # auto-posts), so these read as available drafting actions, not checkboxes.
    url = state["absolute_url"]
    link = f" · [issue]({url})" if url else ""
    return [
        f"▶️ LinkedIn + r/WeeklyThing drafts — use **Draft promo**{link}",
        f"📰 {state['link_count']} links to thread"
        + ("  ·  🎧 audio published" if state["has_audio"] else ""),
    ]


def render_campaign_lines(state: dict) -> list[str]:
    camps = state["campaigns"]
    if not camps:
        return ["_(no live campaigns — manage with `/marky campaign add`)_"]
    lines: list[str] = []
    for c in camps[:6]:
        age = c.get("days_running")
        age_s = f" · {age}d" if isinstance(age, int) else ""
        lines.append(f"• **{c.get('name')}** (`ref={c.get('ref')}`){age_s}")
    return lines


def render_embed(state: dict) -> "discord.Embed":
    if state.get("issue_number") is None:
        return discord.Embed(
            title="📣 Share — nothing published yet",
            description="Once an issue is put to bed it lands here for syndication.",
            color=discord.Color.greyple(),
        )
    n = state["issue_number"]
    subj = state["subject"] or f"WT{n}"
    embed = discord.Embed(
        title=f"📣 Share · WT{n} — {subj}",
        description=f"published {state['publish_date']} · promote it (Marky drafts; never auto-posts)",
        color=discord.Color.blurple(),
        url=state["absolute_url"] or None,
    )
    embed.add_field(name="Syndication", value="\n".join(render_syndication_lines(state)), inline=False)
    embed.add_field(name="Campaigns (program context)", value="\n".join(render_campaign_lines(state)), inline=False)
    embed.set_footer(text=f"refreshed {datetime.now().strftime('%a %H:%M')} · campaigns: /marky campaign")
    return embed


def _build_view(state: dict):
    try:
        from ..personas.views.share_card_view import build_view
    except Exception:  # noqa: BLE001
        logger.exception("share-card: couldn't import share_card_view")
        return None
    return build_view(state)


async def post_or_update(ctx: "_base.JobContext") -> Optional[int]:
    """Render + upsert the Share card (pinned in #promotion) for the
    last-published issue."""
    state = await asyncio.to_thread(gather_state)
    if state.get("issue_number") is None:
        return None
    n = int(state["issue_number"])
    embed = render_embed(state)
    view = _build_view(state)
    return await _cards.upsert_card(
        ctx, kind=KIND, channel_env=_cards.PROMOTION_ENV, persona="marky", n=n, embed=embed, view=view,
    )


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    """`/marky share` — (re)post the Share card for the last-published issue."""
    mid = await post_or_update(ctx)
    if mid is None:
        return _base.JobResult(False, "No published issue yet (or #promotion unavailable).")
    return _base.JobResult(True, "📣 Share card is up in #promotion (pinned).", data={"message_id": mid})
