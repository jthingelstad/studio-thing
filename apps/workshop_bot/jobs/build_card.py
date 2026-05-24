"""Build card — the **content** phase surface (`#editorial`, Eddy).

Phase 1 of the publishing spine (`docs/publishing-process.md`): "is the issue
written and good?" One pinned card showing the issue's anatomy in **reading
order** (Intro · Currently · Cover · Notable · Journal · Briefly · Outro ·
Outro) plus the editorial review + reorder status. It carries the
content-author buttons and the **Mark built** transition that opens Publish.

State is a pure function of DB + S3 (no wizard-state table). The persistent
button View lives in `personas/views/build_card_view.py`; the button
`custom_id`s are defined here so the renderer and the view agree.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord

from ..tools import db, issue_items, s3
from ..tools.content import draft as draft_mod
from . import _base, _cards, issue_status

logger = logging.getLogger("workshop.jobs.build_card")

NAME = "build-card"
KIND = "build"

# Button custom_ids — static so the persistent View routes across restarts.
BTN_REFRESH = "build:refresh"
BTN_REORDER = "build:reorder"
BTN_EDIT = "build:edit"
BTN_MARK_BUILT = "build:mark-built"


def gather_state(n: Optional[int] = None, *, window: Optional[dict] = None) -> dict:
    """Content state for the Build card. Synchronous (blocking S3); async
    callers wrap in `asyncio.to_thread`.

    Issue-number resolution: prefer ``window["issue_number"]`` when the
    caller passed a DB-shaped window (carries the column), else fall back
    to the explicit ``n`` arg — start-issue passes the ``compute_window``
    dict which has the dates but not ``issue_number``, so the explicit
    ``n`` is what we have. Both-missing is the "no active issue" case.
    """
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

    currently = db.currently_get_entries(n)
    try:
        open_comments = len(issue_items.list_open_comments(n))
    except Exception as exc:  # noqa: BLE001
        logger.warning("build-card: list_open_comments(%d) failed: %s", n, exc)
        open_comments = 0

    sec = st["sections"]
    sections_ready = all(sec[k]["present"] for k in ("notable", "brief", "journal"))
    # Build phase is content-only: the three sections + intro + cover.
    # Haiku is a Publish concern (Eddy writes it, not Jamie) — moved off
    # the Build card alongside subject/description/CTA. Thesis is also
    # Publish (auto-generated at mark-built from the frozen content).
    build_ready = bool(
        sections_ready and st["intro_present"] and st["cover_present"]
    )

    return {
        "issue_number": n,
        "phase": window.get("phase", "build"),
        "pub_date": window.get("pub_date", ""),
        "days_to_pub": issue_status._days_to(window.get("pub_date", "")),
        "word_count": st["word_count"],
        "sections": sec,
        "intro_present": st["intro_present"],
        "outro_present": "outro.md" in files,
        "cover_present": st["cover_present"],
        "currently_entries": [c.get("type_label") for c in currently],
        "reorder_applied": "thesis.md" in files,
        "open_comments": open_comments,
        "review_url": s3.issue_file_url(n, "draft.html"),
        "build_ready": build_ready,
    }


# ---------- rendering ----------

def render_anatomy_lines(state: dict) -> list[str]:
    """The issue's content rows in reading order."""
    sec = state["sections"]
    lines: list[str] = []
    lines.append(f"{_cards.mark(state['intro_present'])} Intro"
                 + ("" if state["intro_present"] else " — write it, push via Shortcut"))
    entries = state["currently_entries"]
    lines.append(
        f"{_cards.mark(bool(entries))} Currently"
        + (f" — {len(entries)} ({', '.join(entries)})" if entries else " — none yet")
    )
    lines.append(f"{_cards.mark(state['cover_present'])} Cover")
    for name, label in (("notable", "Notable"), ("journal", "Journal"), ("brief", "Briefly")):
        icon, tag = _cards.section_tag(sec[name])
        lines.append(f"{icon} {label} — {tag}")
    lines.append(f"{_cards.mark(state['outro_present'])} Outro" + ("" if state["outro_present"] else " — optional"))
    return lines


def render_editorial_lines(state: dict) -> list[str]:
    oc = state["open_comments"]
    return [
        f"↑ Reorder — " + ("applied (thesis set)" if state["reorder_applied"] else "not run"),
        f"🔎 Review — {oc} open note{'' if oc == 1 else 's'} · [view drawer]({state['review_url']})",
    ]


def render_embed(state: dict) -> "discord.Embed":
    if state.get("issue_number") is None:
        return discord.Embed(
            title="📄 Build — no active issue",
            description="Run `/eddy issue start <n> <pub-date> <days>` to begin a cycle.",
            color=discord.Color.greyple(),
        )
    n = state["issue_number"]
    sec = state["sections"]
    ready = "✅ ready to build" if state["build_ready"] else "⚠️ in progress"
    color = discord.Color.green() if state["build_ready"] else discord.Color.gold()
    embed = discord.Embed(
        title=f"📄 Build · WT{n}",
        description=(
            f"{ready} · ~{state['word_count']} words · "
            f"{sec['notable']['item_count']}N / {sec['brief']['item_count']}B / "
            f"{sec['journal']['item_count']}J · pub {state['pub_date']} ({state['days_to_pub']})"
        ),
        color=color,
        url=state["review_url"],
    )
    embed.add_field(name="The issue (reading order)", value="\n".join(render_anatomy_lines(state)), inline=False)
    embed.add_field(name="Editorial", value="\n".join(render_editorial_lines(state)), inline=False)
    when = "ready" if state["build_ready"] else "fill the required sections + intro/cover/haiku first"
    embed.set_footer(text=f"Mark built when done → opens Publish ({when}) · refreshed {datetime.now().strftime('%a %H:%M')}")
    return embed


def _build_view(state: dict):
    try:
        from ..personas.views.build_card_view import build_view
    except Exception:  # noqa: BLE001
        logger.exception("build-card: couldn't import build_card_view")
        return None
    return build_view(state)


async def post_or_update(ctx: "_base.JobContext", n: Optional[int] = None, *, window: Optional[dict] = None) -> Optional[int]:
    """Render + upsert the Build card (pinned in #editorial)."""
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


# ---------- the build→publish transition ----------

async def mark_built(ctx: "_base.JobContext") -> "_base.JobResult":
    """Exit gate of Build. Flips ``phase`` to ``publish``, finalizes the
    Build card (compact summary, unpinned), runs ``compose-thesis`` to
    write the editorial framing from the now-frozen content, posts +
    pins the Publish card, and auto-fires ``compose-cta`` so a CTA
    framing is waiting in Publish. Refuses if content isn't complete.

    Order matters: compose-thesis lands BEFORE compose-cta so the
    CTA prompt picks up the freshly-written thesis as its anchor."""
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "No active issue window. Run `/eddy issue start`.")
    n = int(window["issue_number"])
    if window.get("phase") == "publish":
        return _base.JobResult(True, f"WT{n} is already in **Publish**.", data={"issue_number": n, "phase": "publish"})

    state = await asyncio.to_thread(gather_state, n, window=window)
    if not state.get("build_ready"):
        return _base.JobResult(
            False,
            f"⚠️ WT{n} isn't built yet — needs the three sections + intro + cover. "
            f"Fill those, then mark it built.",
            data={"issue_number": n},
        )

    db.set_issue_phase(n, "publish")
    window = db.get_active_issue_window()  # refresh phase

    # Finalize the Build card to a compact record + unpin.
    summary = discord.Embed(
        title=f"📄 Build · WT{n} — ✅ Built",
        description="Moved to **Publish**. Reopen with `/eddy issue reopen` if you need to edit content.",
        color=discord.Color.green(),
    )
    await _cards.finalize_card(ctx, kind=KIND, channel_env=_cards.EDITORIAL_ENV, persona="eddy", n=n, embed=summary)

    # Compose the thesis from the just-frozen content first — it's the
    # editorial framing every subsequent Publish job anchors on.
    # Best-effort: downstream prompts degrade gracefully on missing
    # thesis.md so a failure here doesn't wedge the transition.
    from . import publish_card, compose_cta, compose_echoes, compose_thesis
    try:
        await compose_thesis.run(_base.JobContext(deps=ctx.deps, trigger="mark-built"))
    except Exception:  # noqa: BLE001
        logger.exception("mark-built: compose-thesis failed for #%d", n)

    # Compose Echoes (Thingy's archive note) — mandatory, runs over the
    # frozen content with the just-written thesis as anchor. On failure
    # we log and continue; mark-built doesn't unwind on a single job.
    try:
        await compose_echoes.run(_base.JobContext(deps=ctx.deps, trigger="mark-built"))
    except Exception:  # noqa: BLE001
        logger.exception("mark-built: compose-echoes failed for #%d", n)

    # Post the Publish card (reads thesis + echoes + cta state) and
    # auto-request the CTA from Patty (its prompt also reads the thesis).
    await publish_card.post_or_update(ctx, n, window=window)
    try:
        await compose_cta.run(_base.JobContext(deps=ctx.deps, trigger="mark-built"))
    except Exception:  # noqa: BLE001
        logger.exception("mark-built: compose-cta auto-request failed for #%d", n)
    await publish_card.post_or_update(ctx, n, window=window)  # reflect any CTA result

    return _base.JobResult(
        True,
        f"✅ **WT{n}** marked built — now in **Publish**. Thesis written; CTA requested from Patty; pick a framing on the Publish card.",
        data={"issue_number": n, "phase": "publish"},
    )


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    """`/eddy issue build` — (re)post + pin the Build card."""
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "No active issue window. Run `/eddy issue start <n> <pub-date> <days>`.")
    n = int(window["issue_number"])
    mid = await post_or_update(ctx, n, window=window)
    if mid is None:
        return _base.JobResult(False, f"❌ couldn't post the Build card for #{n} (channel unavailable?).")
    return _base.JobResult(True, f"📄 Build card for **WT{n}** is up in #editorial (pinned).", data={"issue_number": n, "message_id": mid})


async def reopen(ctx: "_base.JobContext") -> "_base.JobResult":
    """Flip back to Build to fix content. Re-posts the Build card."""
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    n = int(window["issue_number"])
    db.set_issue_phase(n, "build")
    window = db.get_active_issue_window()
    await post_or_update(ctx, n, window=window)
    return _base.JobResult(True, f"↩️ WT{n} reopened for edits — back in **Build**.", data={"issue_number": n, "phase": "build"})
