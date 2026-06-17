"""Publish card — the **send** phase surface (`#production`, Scout + pipeline).

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
BTN_HAIKU = "publish:haiku"        # haiku (compose-haiku)
BTN_CTA = "publish:cta"            # membership CTA (compose-cta)
BTN_RECOMPOSE = "publish:recompose"  # retry thesis + echoes if either failed at mark-built
BTN_EMAIL = "publish:email"        # 🚀 Buttondown
BTN_WEBSITE = "publish:website"    # 🚀 Website
BTN_PODCAST = "publish:podcast"    # 🚀 Audio
BTN_ALL = "publish:all"            # 🚀 all in order
BTN_BED = "publish:bed"            # put to bed


def gather_state(n: Optional[int] = None, *, window: Optional[dict] = None) -> dict:
    """Same issue-number resolution as build_card.gather_state — prefer
    the DB-shaped window's ``issue_number`` column; fall back to the
    explicit ``n`` arg when the caller passed a ``compute_window``-shaped
    dict (no issue_number)."""
    window = window or db.get_active_issue_window()
    if window is None:
        return {"issue_number": None}
    derived = window.get("issue_number")
    if derived is not None:
        n = int(derived)
    elif n is not None:
        n = int(n)
    else:
        return {"issue_number": None}
    files = _cards.issue_files(n)
    st = draft_mod.section_status(n, list_objects=files)
    meta = _cards.read_metadata_raw(n)

    subject = (meta.get("subject") or "").strip()
    description = (meta.get("description") or "").strip()
    buttondown_id = (meta.get("buttondown_id") or "").strip()
    absolute_url = (meta.get("absolute_url") or "").strip()
    cta_files = sorted(f for f in files if (f.startswith("cta-") or f.startswith("thanks-")) and f.endswith(".md"))
    haiku_present = bool(st["assets"].get("haiku.md"))
    # Echoes — written as echoes.md by compose-echoes.
    echoes_present = "echoes.md" in files
    # Thesis written by compose-thesis at mark-built; show the prose on
    # the card so Jamie sees the editorial framing alongside subject /
    # description / CTA. Missing thesis isn't an error — degrades to a
    # placeholder line (subject / description / haiku / CTA prompts also
    # degrade gracefully).
    thesis_res = s3.read_issue_file(n, "thesis.md")
    thesis_text = (thesis_res.get("text") or "").strip() if thesis_res.get("found") else ""

    any_section = any(st["sections"][k]["present"] for k in ("notable", "brief", "journal"))
    # Email needs subject + description + haiku + intro + cover. (Haiku
    # is now a Publish concern — Eddy writes it via compose-haiku;
    # button lives on this card.)
    email_ready = bool(subject and description and haiku_present
                       and st["intro_present"] and st["cover_present"])
    email_missing = []
    if not subject:
        email_missing.append("subject")
    if not description:
        email_missing.append("description")
    for req, present in (("haiku", haiku_present),
                         ("intro", st["intro_present"]), ("cover", st["cover_present"])):
        if not present:
            email_missing.append(req)

    phase = window.get("phase", "publish")
    # In Publish phase, thesis + echoes should already exist (compose-thesis
    # and compose-echoes auto-fire at mark-built, best-effort). If they're
    # missing past the phase boundary, the auto-fire failed silently and
    # the operator needs a way to retry.
    thesis_failed = phase == "publish" and not thesis_text
    echoes_failed = phase == "publish" and not echoes_present
    recompose_needed = thesis_failed or echoes_failed

    return {
        "issue_number": n,
        "phase": phase,
        "pub_date": window.get("pub_date", ""),
        "days_to_pub": issue_status._days_to(window.get("pub_date", "")),
        "thesis": thesis_text,
        "thesis_failed": thesis_failed,
        "subject": subject,
        "description": description,
        "haiku_present": haiku_present,
        "echoes_present": echoes_present,
        "echoes_failed": echoes_failed,
        "recompose_needed": recompose_needed,
        "cta_files": cta_files,
        "buttondown_id": buttondown_id,
        "buttondown_url": (publish._draft_url(buttondown_id) if buttondown_id else ""),
        "absolute_url": absolute_url,
        "email_missing": email_missing,
        "audio_shipped": f"weekly-thing-{n}.mp3" in files,
        "email_shipped": bool(buttondown_id),
        "review_url": s3.issue_file_url(n, "draft.html"),
        "gates": {
            BTN_RECOMPOSE: recompose_needed,
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
    haiku = state["haiku_present"]
    echoes = state["echoes_present"]
    echoes_failed = state.get("echoes_failed", False)
    if echoes:
        echoes_line = "✅ Echoes — Thingy's archive note written"
    elif echoes_failed:
        echoes_line = "❌ Echoes — compose-echoes failed at mark-built → Retry button"
    else:
        echoes_line = "☐ Echoes — auto-fired at mark-built (Opus)"
    return [
        f"{_cards.mark(bool(subj))} Subject — " + (f"\"{subj}\"" if subj else "pick one → button"),
        f"{_cards.mark(bool(desc))} Description — " + (desc if desc else "generated with the subject"),
        f"{_cards.mark(haiku)} Haiku — " + ("written" if haiku else "Eddy writes it → button"),
        echoes_line,
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
    # Thesis at the top — Eddy's editorial framing, written at mark-built.
    # Shown verbatim so Jamie sees the read that anchors every Publish job.
    thesis = state.get("thesis") or ""
    if thesis:
        thesis_value = thesis
    elif state.get("thesis_failed"):
        thesis_value = "_❌ compose-thesis failed at mark-built — hit the Retry composes button._"
    else:
        thesis_value = "_(pending — compose-thesis runs at mark-built)_"
    embed.add_field(name="📐 Thesis", value=thesis_value, inline=False)
    embed.add_field(name="Shared (envelope + haiku + CTA)", value="\n".join(render_shared_lines(state)), inline=False)
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
        ctx, kind=KIND, channel_env=_cards.PRODUCTION_ENV, persona="scout", n=n, embed=embed, view=view,
    )


# ---------- recompose (retry thesis + echoes after a mark-built failure) ----------


async def recompose(ctx: "_base.JobContext") -> "_base.JobResult":
    """Re-fire compose-thesis and/or compose-echoes for the active issue,
    for whichever atom is missing in Publish phase. Used by the Publish
    card's Retry button when the auto-fires at mark-built fail silently.
    Idempotent: re-running with both atoms present is a no-op."""
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    state = await asyncio.to_thread(gather_state, window=window)
    if not state.get("recompose_needed"):
        return _base.JobResult(
            True,
            "✅ Nothing to recompose — thesis + echoes are both present.",
            data={"thesis_failed": False, "echoes_failed": False},
        )

    from . import compose_thesis, compose_echoes
    fired: list[str] = []
    errors: list[str] = []

    if state.get("thesis_failed"):
        try:
            res = await compose_thesis.run(_base.JobContext(deps=ctx.deps, trigger="recompose"))
            fired.append("thesis")
            if not res.ok:
                errors.append(f"thesis: {res.message}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("recompose: compose-thesis raised")
            errors.append(f"thesis: {exc!r}")

    if state.get("echoes_failed"):
        try:
            res = await compose_echoes.run(_base.JobContext(deps=ctx.deps, trigger="recompose"))
            fired.append("echoes")
            if not res.ok:
                errors.append(f"echoes: {res.message}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("recompose: compose-echoes raised")
            errors.append(f"echoes: {exc!r}")

    if errors:
        return _base.JobResult(
            False,
            "⚠️ Recompose hit errors: " + " · ".join(errors),
            data={"fired": fired, "errors": errors},
        )
    return _base.JobResult(
        True,
        f"✅ Recompose ran — refreshed {', '.join(fired)}.",
        data={"fired": fired, "errors": []},
    )
