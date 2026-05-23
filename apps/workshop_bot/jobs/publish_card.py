"""Publish card — the **send** phase surface (`#editorial`, Eddy + pipeline).

Phase 2 of the publishing spine (`docs/publishing-process.md`): "is it out the
door, per channel?" Posted on `mark built`. Shows the shared envelope (subject,
description) + the membership CTA, then the per-channel matrix — Email
(Buttondown), Website (archive), Podcast (audio) — each with its gate and ship
state. Each 🚀 leg reports progress + outcome on this card.

The CTA is auto-requested from Patty on entry (see `build_card.mark_built`);
the card's CTA row is "pick a framing", never "go run Patty".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord

from ..tools import db, s3
from ..tools.content import draft as draft_mod
from . import _base, _cards, issue_status, publish

logger = logging.getLogger("workshop.jobs.publish_card")

NAME = "publish-card"
KIND = "publish"

BTN_META = "publish:meta"          # subject + description (compose-meta)
BTN_CTA = "publish:cta"            # membership CTA (compose-cta)
BTN_EMAIL = "publish:email"        # 🚀 Buttondown
BTN_WEBSITE = "publish:website"    # 🚀 Website
BTN_PODCAST = "publish:podcast"    # 🚀 Audio
BTN_ALL = "publish:all"            # 🚀 all in order
BTN_BED = "publish:bed"            # put to bed


def gather_state(n: int, *, window: Optional[dict] = None) -> dict:
    window = window or db.get_active_issue_window()
    if window is None:
        return {"issue_number": None}
    n = int(window["issue_number"])
    files = _cards.issue_files(n)
    st = draft_mod.section_status(n, list_objects=files)
    meta = _cards.read_metadata_raw(n)

    subject = (meta.get("subject") or "").strip()
    description = (meta.get("description") or "").strip()
    buttondown_id = (meta.get("buttondown_id") or "").strip()
    absolute_url = (meta.get("absolute_url") or "").strip()
    cta_files = sorted(f for f in files if (f.startswith("cta-") or f.startswith("thanks-")) and f.endswith(".md"))

    any_section = any(st["sections"][k]["present"] for k in ("notable", "brief", "journal"))
    # Email needs the *content* of subject + description (not just the file).
    email_ready = bool(subject and description and st["assets"].get("haiku.md")
                       and st["intro_present"] and st["cover_present"])
    email_missing = []
    if not subject:
        email_missing.append("subject")
    if not description:
        email_missing.append("description")
    for req, present in (("haiku", bool(st["assets"].get("haiku.md"))),
                         ("intro", st["intro_present"]), ("cover", st["cover_present"])):
        if not present:
            email_missing.append(req)

    return {
        "issue_number": n,
        "phase": window.get("phase", "publish"),
        "pub_date": window.get("pub_date", ""),
        "days_to_pub": issue_status._days_to(window.get("pub_date", "")),
        "subject": subject,
        "description": description,
        "cta_files": cta_files,
        "buttondown_id": buttondown_id,
        "buttondown_url": (publish._draft_url(buttondown_id) if buttondown_id else ""),
        "absolute_url": absolute_url,
        "email_missing": email_missing,
        "audio_shipped": f"weekly-thing-{n}.mp3" in files,
        "email_shipped": bool(buttondown_id),
        "review_url": s3.issue_file_url(n, "draft.html"),
        "gates": {
            BTN_EMAIL: email_ready,
            BTN_WEBSITE: bool(buttondown_id),     # website needs the stamped absolute_url
            BTN_PODCAST: any_section,
            BTN_ALL: email_ready,
        },
    }


# ---------- rendering ----------

def render_shared_lines(state: dict) -> list[str]:
    subj = state["subject"]
    desc = state["description"]
    cta = state["cta_files"]
    return [
        f"{_cards.mark(bool(subj))} Subject — " + (f"\"{subj}\"" if subj else "pick one → button"),
        f"{_cards.mark(bool(desc))} Description — " + (desc if desc else "generated with the subject"),
        (f"✅ CTA — {', '.join('`' + c + '`' for c in cta)}" if cta
         else "☐ CTA — pick a framing (auto-requested on entry)"),
    ]


def render_channel_lines(state: dict) -> list[str]:
    gates = state["gates"]
    lines: list[str] = []
    # Email
    if state["email_shipped"]:
        lines.append(f"✅ Email — [Buttondown draft]({state['buttondown_url']})")
    elif gates[BTN_EMAIL]:
        lines.append("🟢 Email — ready to send")
    else:
        miss = ", ".join(state["email_missing"]) or "requirements"
        lines.append(f"⛔ Email — blocked: needs {miss}")
    # Website
    if gates[BTN_WEBSITE]:
        lines.append("🟢 Website — ready to commit"
                     + (f" · [live]({state['absolute_url']})" if state["absolute_url"] else ""))
    else:
        lines.append("☐ Website — needs Email sent first (stamps the URL)")
    # Podcast
    if state["audio_shipped"]:
        lines.append("✅ Podcast — audio rendered")
    elif gates[BTN_PODCAST]:
        lines.append("🟢 Podcast — ready to render")
    else:
        lines.append("☐ Podcast — needs content")
    return lines


def render_embed(state: dict) -> "discord.Embed":
    if state.get("issue_number") is None:
        return discord.Embed(
            title="📨 Publish — no active issue",
            description="No issue is in Publish. Mark a Build issue built to open this.",
            color=discord.Color.greyple(),
        )
    n = state["issue_number"]
    subj = state["subject"] or "(subject pending)"
    all_shipped = state["email_shipped"] and state["audio_shipped"]
    color = discord.Color.green() if all_shipped else discord.Color.blurple()
    embed = discord.Embed(
        title=f"📨 Publish · WT{n} — {subj}",
        description=f"per-channel send · pub {state['pub_date']} ({state['days_to_pub']})",
        color=color,
        url=state["review_url"],
    )
    embed.add_field(name="Shared (envelope + CTA)", value="\n".join(render_shared_lines(state)), inline=False)
    embed.add_field(name="Channels", value="\n".join(render_channel_lines(state)), inline=False)
    embed.set_footer(text=f"refreshed {datetime.now().strftime('%a %H:%M')}")
    return embed


def _build_view(state: dict):
    try:
        from ..personas.views.publish_card_view import build_view
    except Exception:  # noqa: BLE001
        logger.exception("publish-card: couldn't import publish_card_view")
        return None
    return build_view(state)


async def post_or_update(ctx: "_base.JobContext", n: Optional[int] = None, *, window: Optional[dict] = None) -> Optional[int]:
    window = window or db.get_active_issue_window()
    if window is None:
        return None
    n = int(n if n is not None else window["issue_number"])
    state = await asyncio.to_thread(gather_state, n, window=window)
    embed = render_embed(state)
    view = _build_view(state)
    return await _cards.upsert_card(
        ctx, kind=KIND, channel_env=_cards.EDITORIAL_ENV, persona="eddy", n=n, embed=embed, view=view,
    )
