"""``update-draft`` — project upstream state into ``draft.md``.

A *pure projection*: re-run it and you get the same output (modulo
upstream changes). The draft is rebuilt from ``templates/draft_starter.md``
every run — so the layout / section order always tracks the template — and
each block is filled wholesale from its source. No additive merge; nothing
on the existing ``draft.md`` is preserved. Real authoring lives upstream
(Pinboard for the Notable / Briefly links, micro.blog for the Journal,
Drafts → Shortcut for ``intro.md`` / ``cover.json`` / ``currently.json``);
the haiku is a composed asset (``compose-haiku``). The cover caption and
the ``Currently`` section each come from a structured ``cover.json`` /
``currently.json`` (preferred) or a legacy verbatim ``cover.md`` /
``currently.md`` — see ``_cover.render`` / ``_currently.render``. The shape mirrors a
delivered issue: ``---``-fenced blocks, the Notable "discuss on Reddit"
line, ``### [Title](url)`` link headings, the ``→ **[Title](url)**``
Briefly form, elevated (titled) Journal posts, the ``A haiku to leave you
with…`` close.

After the fills the job writes ``draft.md`` back, records a ``draft_digests``
row (so Eddy's review can compute the delta), and — on Tue–Fri — runs
Eddy's post-update review and posts it to ``#editorial``. Sat/Sun/Mon it
stays silent. If ``final.md`` exists the issue is locked and the job
refuses (re-firing would silently produce a stale ``draft.md``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime
from html import escape as _html_escape
from typing import Optional
from zoneinfo import ZoneInfo

from ..personas.base import is_pass_response
from ..tools import alt_text, archive_context, db, issue_items, issue_items_render, issue_items_sync, render, renderers, s3
from ..tools.content import context, draft as draft_mod
from ..tools.llm import anthropic_client
from . import _base, _cover, _currently

logger = logging.getLogger("workshop.jobs.update_draft")

NAME = "update-draft"

# Block fill order is irrelevant (each replace_block is independent); the
# *layout* order lives in templates/draft_starter.md. Listed here in the
# published section order for readability (intro → Currently → cover →
# Featured → Notable → Journal → Brief → outro → haiku). Featured posts
# are micro.blog entries Jamie tagged with the ``Featured`` category;
# the sync layer marks the rows is_promoted=1 and the draft renders
# them as standalone ``## {title}`` sections above Notable. (Eddy used
# to choose promotions during create-final; that mechanism was retired
# in favor of the upstream-category flow.)
SECTION_BLOCKS = (
    "intro", "currently", "cover", "featured",
    "notable", "journal", "brief",
    "outro", "haiku",
)
# Blocks that are just a verbatim copy of an authored asset file. (``cover``
# and ``currently`` are handled separately — see ``_cover.render`` /
# ``_currently.render`` — since they prefer structured ``.json`` forms.)
# ``intro`` and ``outro`` are both Jamie-authored prose pushed via Shortcut;
# ``haiku`` is written by ``compose-haiku``. Same projection shape for all
# three: read verbatim from the asset file into the named block. Promoted
# (featured) items don't appear in the draft template — they only appear
# in ``final.md`` and downstream, spliced inline at their declared position
# by ``create-final``'s assembler.
_ASSET_FILE = {"intro": "intro.md", "outro": "outro.md", "haiku": "haiku.md"}
_COVER_IMAGE = "https://files.thingelstad.com/weekly-thing/{n}/cover.jpg"

# Local timezone for the draft.html "refreshed at" stamp. America/Chicago
# matches the cron's 17:00 CT firing — so the timestamp in the preview banner
# reads as the actual Central time the projection was generated.
_LOCAL_TZ = ZoneInfo("America/Chicago")


# ---------- fills ----------

def _read_asset(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"].strip()
    return ""


def _gather_fills(window: dict) -> tuple[dict[str, str], list[dict]]:
    """Pull every section's content once. Returns ``(fills, alts_filled)``
    where ``alts_filled`` is the per-image log surfaced by
    :func:`tools.content.microblog.fill_missing_alts` — one entry per
    image whose alt was generated and written back to micro.blog during
    this run. ``run()`` posts those to ``#chatter`` so the activity is
    visible.

    The three list sections (Notable / Briefly / Journal) come from
    ``issue_items`` rows: ``sync_all`` first refreshes rows from
    Pinboard + micro.blog (UPSERT on stable source ids, prune rows
    whose upstream item disappeared), then the renderers in
    :mod:`tools.issue_items_render` project rows back to the same
    shape the published email uses. Promoted (featured) rows are
    skipped at the parent-section level so a Journal post Eddy
    promoted into its own standalone section doesn't double up in
    Journal too.

    The atoms (intro / outro / cover / currently / haiku) are still
    file-backed: ``intro.md`` / ``outro.md`` / ``haiku.md`` (verbatim
    reads) and ``cover.json`` / ``currently.json`` (structured renders).
    Failed source pulls degrade to a placeholder line per affected
    section rather than failing the whole run.
    """
    n = int(window["issue_number"])
    # Reset the per-run vision-call cap so a single ``update-draft`` can't
    # fan out to dozens of vision calls (cover + every journal image).
    alt_text.begin_run()
    fills: dict[str, str] = {block: _read_asset(n, _ASSET_FILE[block]) for block in _ASSET_FILE}
    # Cover (caption/date/location) — structured cover.json (preferred) or
    # legacy cover.md; Currently — structured currently.json or legacy currently.md.
    fills["cover"] = _cover.render(n)
    fills["currently"] = _currently.render(n)
    # The haiku ships bold-wrapped with hard breaks; normalize whatever the
    # composed haiku.md holds.
    fills["haiku"] = _base.format_haiku(fills.get("haiku", ""))
    # The cover block leads with the issue's cover image (a derived URL),
    # then the caption / date / location below it. Use a native <img> tag
    # so the alt attribute has an explicit home (cover.json.alt overrides;
    # else vision-generated; else "").
    if fills.get("cover"):
        cover_alt = _cover.alt(n)
        cover_img = (
            f'<img src="{_COVER_IMAGE.format(n=n)}" '
            f'alt="{_html_escape(cover_alt, quote=True)}" />'
        )
        fills["cover"] = f"{cover_img}\n\n{fills['cover']}"

    # Refresh rows from upstream, then render from the row state.
    # sync_all wraps each source so a Pinboard outage doesn't kill the
    # micro.blog sync (or vice-versa); per-source errors surface as
    # placeholder lines via the per-section flags below.
    sync_result = issue_items_sync.sync_all(n, window)
    pin_failed = "error" in sync_result.get("pinboard", {})
    mb_failed = "error" in sync_result.get("microblog", {})

    if pin_failed:
        msg = sync_result["pinboard"].get("error", "unknown error")
        logger.warning("update-draft: Pinboard sync failed for #%d: %s", n, msg)
        fills["notable"] = f"_Notable — couldn't pull from Pinboard ({msg})._"
        fills["brief"] = f"_Briefly — couldn't pull from Pinboard ({msg})._"
    else:
        notable_rows = issue_items.list_items(n, section="notable", include_promoted=False)
        brief_rows = issue_items.list_items(n, section="brief", include_promoted=False)
        fills["notable"] = issue_items_render.render_notable(notable_rows, n)
        fills["brief"] = issue_items_render.render_brief(brief_rows)

    if mb_failed:
        msg = sync_result["microblog"].get("error", "unknown error")
        logger.warning("update-draft: micro.blog sync failed for #%d: %s", n, msg)
        fills["journal"] = f"_Journal — couldn't pull from micro.blog ({msg})._"
        fills["featured"] = ""
    else:
        journal_rows = issue_items.list_items(n, section="journal", include_promoted=False)
        fills["journal"] = issue_items_render.render_journal(journal_rows)
        # Featured posts are micro.blog journal entries Jamie tagged with the
        # ``Featured`` category. The sync layer flags them is_promoted=1 with
        # promoted_position="before_notable"; they render here as standalone
        # ``## {title}`` sections above Notable, in publish-date order.
        featured_rows = [
            r for r in issue_items.list_items(n, section="journal", include_promoted=True)
            if r.get("is_promoted")
        ]
        fills["featured"] = issue_items_render.render_featured_sections(featured_rows)

    alts_filled = list(sync_result.get("microblog", {}).get("alts_filled") or [])
    return fills, alts_filled


def _final_exists(issue_number: int) -> bool:
    res = s3.read_issue_file(issue_number, "final.md")
    return bool(res.get("found"))


# ---------- Eddy's post-update review ----------

# How many archive passages to surface in the draft-review's "Recent
# archive echoes" block. Ten is enough to span 3-5 distinct issues and
# 2-3 distinct themes typically; bigger numbers crowd the prompt.
_DRAFT_REVIEW_ECHO_K = 10
# Query is the first chunk of the draft body — long enough to carry the
# issue's center of gravity (intro + Notable section + start of Journal),
# short enough to keep latency tight.
_DRAFT_REVIEW_ECHO_QUERY_CHARS = 3000

# Model for the editorial review (`_draft_review`) — the single,
# substantive editorial pass. Its prose lands behind the `draft.html`
# "Show review" drawer; its anchored bullets persist as
# ``editorial_comments`` rows that the ship console surfaces as a count.
# This is the highest-value thing Eddy does, so it runs on Opus by
# default. Tunable via ``WORKSHOP_EDDY_DRAFT_REVIEW_MODEL``.
#
# (Until 2026-05 there was a *second*, separate review — a freeform
# `#editorial` card driven by a weekday-scaled model. It used a different
# prompt and wasn't stored, so it routinely contradicted this one and
# re-surfaced already-closed comments. It was retired in favour of this
# single stored pass; the console shows the open-comment count instead.)
_DRAFT_REVIEW_DEFAULT_MODEL = "opus"


def _draft_review_model() -> str:
    override = (os.environ.get("WORKSHOP_EDDY_DRAFT_REVIEW_MODEL") or "").strip()
    return override or _DRAFT_REVIEW_DEFAULT_MODEL


# ---------- editorial_comments capture ----------
#
# After Eddy writes the review markdown, we parse the ``<!-- target:xxx -->``
# markers and store each anchored bullet/paragraph as a row in
# ``editorial_comments`` with a stable handle (``E349-N1``, ``E349-X3``).
# The HTML drawer keeps using the existing in-page markers for connector
# lines; the DB rows are what the future ``@eddy tell me about E349-N1``
# Discord lookup queries. Re-runs supersede prior comments wholesale.

_TARGET_MARKER_RE = re.compile(r"<!--\s*target:([a-z0-9_-]+)\s*-->")
# Match the start of a markdown bullet or numbered item, optionally
# indented; we treat each top-level bullet as a candidate comment.
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+", re.MULTILINE)


def _split_review_into_segments(review_md: str) -> list[str]:
    """Split the review markdown into top-level segments. Each segment
    is either a contiguous paragraph or a bullet item; the segment
    boundary is a blank line OR the start of a new bullet line. We
    keep the bullet prefix on the segment so the body retains its
    shape when rendered later."""
    text = (review_md or "").strip()
    if not text:
        return []
    # Split on blank lines first.
    raw_blocks = re.split(r"\n\s*\n", text)
    segments: list[str] = []
    for block in raw_blocks:
        block = block.rstrip()
        if not block:
            continue
        # Within a block, split on the start of each new bullet line so
        # that "intro paragraph + bulleted suggestions" produces one
        # segment per bullet rather than one giant blob.
        positions: list[int] = [0]
        for m in _BULLET_RE.finditer(block):
            if m.start() > 0:
                positions.append(m.start())
        positions.append(len(block))
        for i in range(len(positions) - 1):
            piece = block[positions[i]:positions[i + 1]].strip()
            if piece:
                segments.append(piece)
    return segments


def _section_for_target(target: str) -> tuple[str, str]:
    """Resolve a target marker (``n1``, ``b2``, ``j3``, ``intro``,
    ``hygiene``, etc.) to ``(scope, section_or_letter)``. ``scope`` is
    ``'item'`` / ``'section'`` / ``'hygiene'`` / ``'issue'``."""
    if target in ("hygiene", "x"):
        return "hygiene", "hygiene"
    if target in ("whole", "issue", "w"):
        return "issue", "issue"
    if target in issue_items.SECTION_HANDLE_LETTER:
        return "section", target
    # Item-scoped: n1 / b2 / j3 — first letter is the section, rest is the index.
    if len(target) >= 2 and target[0] in ("n", "b", "j"):
        return "item", {"n": "notable", "b": "brief", "j": "journal"}[target[0]]
    return "issue", "issue"


def _row_id_for_synth(issue_number: int, target: str) -> "int | None":
    """Map ``n1`` / ``b2`` / ``j3`` to the row id at that position in
    its section. Returns ``None`` if the position is out of range
    (review references an item that no longer exists)."""
    if len(target) < 2 or target[0] not in ("n", "b", "j"):
        return None
    section = {"n": "notable", "b": "brief", "j": "journal"}[target[0]]
    try:
        idx = int(target[1:])
    except ValueError:
        return None
    rows = issue_items.list_items(issue_number, section=section, include_promoted=False)
    if idx < 1 or idx > len(rows):
        return None
    return int(rows[idx - 1]["id"])


def _store_review_comments(issue_number: int, review_md: str) -> tuple[int, list[str]]:
    """Parse the review markdown and write one ``editorial_comments``
    row per target-marker-prefixed segment. Returns
    ``(count, segment_handles)`` — ``segment_handles`` is a list of
    handles parallel to ``_split_review_into_segments(review_md)``,
    with ``""`` for segments that didn't get a row (ungrounded prose
    or store failure). This parallel list is what
    :func:`_inject_handle_markers` uses to embed handle badges in
    the drawer markdown without re-doing the parse.

    Prior-pass open comments get superseded *after* the new pass writes
    so the new pass's comments stay visible. A re-run that produces no
    anchored comments leaves the prior pass intact (better to keep
    stale guidance than to silently clear the drawer)."""
    if not (review_md or "").strip():
        return 0, []
    segments = _split_review_into_segments(review_md)
    if not segments:
        return 0, []
    prior_open_ids = [int(c["id"]) for c in issue_items.list_open_comments(issue_number)]
    written = 0
    segment_handles: list[str] = []
    for seg in segments:
        markers = _TARGET_MARKER_RE.findall(seg)
        if not markers:
            segment_handles.append("")
            continue  # ungrounded prose — skip
        target = markers[0]
        try:
            scope, section_or_letter = _section_for_target(target)
        except Exception:  # noqa: BLE001
            segment_handles.append("")
            continue
        body_md = _TARGET_MARKER_RE.sub("", seg).strip()
        # Strip the leading bullet prefix so stored bodies read cleanly
        # (the bullet shape is rendering-layer; storage is content).
        body_md = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", body_md).strip()
        if not body_md:
            segment_handles.append("")
            continue
        try:
            if scope == "item":
                rid = _row_id_for_synth(issue_number, target)
                if rid is None:
                    # Item is gone; record as section-scoped instead.
                    row = issue_items.write_comment(
                        issue_number=issue_number, scope="section",
                        section=section_or_letter, body_md=body_md,
                        verdict="suggestion",
                    )
                else:
                    row = issue_items.write_comment(
                        issue_number=issue_number, scope="item",
                        item_id=rid, body_md=body_md, verdict="suggestion",
                    )
            elif scope == "section":
                row = issue_items.write_comment(
                    issue_number=issue_number, scope="section",
                    section=section_or_letter, body_md=body_md,
                    verdict="suggestion",
                )
            elif scope == "hygiene":
                row = issue_items.write_comment(
                    issue_number=issue_number, scope="hygiene",
                    body_md=body_md, verdict="suggestion",
                )
            else:
                row = issue_items.write_comment(
                    issue_number=issue_number, scope="issue",
                    body_md=body_md, verdict="suggestion",
                )
        except Exception:  # noqa: BLE001
            logger.exception("update-draft: failed to store review comment")
            segment_handles.append("")
            continue
        written += 1
        segment_handles.append(str(row["handle"]))
    if written and prior_open_ids:
        # Mark each prior-pass comment superseded by *one* of the new
        # rows — we pick the first new row whose handle still resolves
        # via list_open_comments. The replaced_by pointer is a chain
        # anchor; clients walk forward by handle, so any new row works.
        new_open = issue_items.list_open_comments(issue_number)
        anchor = next((c["id"] for c in new_open if int(c["id"]) not in prior_open_ids), None)
        if anchor is not None:
            try:
                with db.connect() as conn:
                    placeholders = ",".join("?" for _ in prior_open_ids)
                    conn.execute(
                        f"UPDATE editorial_comments SET replaced_by_id = ? "
                        f"WHERE id IN ({placeholders})",
                        [int(anchor), *[int(i) for i in prior_open_ids]],
                    )
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: prior-pass supersede failed")
    return written, segment_handles


def _inject_handle_markers(review_md: str, segment_handles: list[str]) -> str:
    """Walk segments in the same order :func:`_store_review_comments`
    did, and inject a ``<!-- handle:H -->`` marker next to the first
    ``<!-- target:T -->`` marker of each segment that earned a
    handle. The renderer turns the marker into a visible badge + copy
    button.

    Idempotent on segments without a handle. Preserves the original
    text shape (we re-join with ``\\n\\n``-style separators the
    splitter consumed).
    """
    if not (review_md or "").strip() or not segment_handles:
        return review_md
    segments = _split_review_into_segments(review_md)
    if len(segments) != len(segment_handles):
        # Defensive — shapes should match since the same splitter
        # produced both. If they don't, return the original.
        return review_md
    # We need to insert handle markers without reordering or losing
    # the original blank-line structure. Simpler than re-joining: do
    # an in-place sub on the original text per (segment, handle).
    out = review_md
    for seg, handle in zip(segments, segment_handles):
        if not handle or not seg:
            continue
        target_match = _TARGET_MARKER_RE.search(seg)
        if not target_match:
            continue
        # Replace the segment's first target marker with itself + the
        # handle marker. Only the first occurrence inside the segment
        # gets the handle (handles are per-segment, not per-marker).
        old_target = target_match.group(0)
        replacement = f"{old_target}<!-- handle:{handle} -->"
        # Replace inside the segment first, then put the segment back
        # into the original review text. The segment substring is
        # unique enough (it's a full paragraph) that .replace works.
        new_seg = seg.replace(old_target, replacement, 1)
        out = out.replace(seg, new_seg, 1)
    return out


async def _draft_review(
    ctx: "_base.JobContext", window: dict, st: dict, prev_digest, today, draft_text: str,
) -> str:
    """A solid editorial pass for the shareable ``draft.html`` — suggestions
    only, embedded behind a "Show review" toggle (hidden by default). Runs
    on every ``update-draft`` (not weekday-gated like the ``#editorial``
    card — the shareable preview should always carry the latest pass).
    Returns the review markdown, or ``""`` when there's no Eddy / the
    prompt is missing / Eddy responds ``PASS`` (an empty draft)."""
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return ""
    eddy = team.bots.get("eddy")
    if eddy is None or getattr(eddy, "user", None) is None:
        return ""
    try:
        prompt = anthropic_client.load_prompt("eddy-draft-review")
    except OSError as exc:
        logger.warning("update-draft: draft-review prompt missing: %s", exc)
        return ""
    n = int(window["issue_number"])
    eddy_ctx = context.build_eddy_context(ref_date=today, section_status=st, prev_digest=prev_digest)
    target_legend = render.review_target_legend(draft_text, issue_number=n)
    # Pre-inject semantic echoes from the archive — gives Eddy "you've
    # been here before" awareness without him having to call the
    # archive tools mid-reasoning. Single query against the draft body;
    # ~$0.001/call, runs daily, fail-soft via archive_context.
    echo_passages, echo_error = await asyncio.to_thread(
        archive_context.fetch_archive_context,
        draft_text[:_DRAFT_REVIEW_ECHO_QUERY_CHARS],
        k=_DRAFT_REVIEW_ECHO_K,
        exclude_issue=n,
    )
    echo_block = archive_context.format_archive_context_block(
        echo_passages,
        heading="Recent archive echoes",
        intro=(
            "These are the archive passages most semantically related to "
            "the current draft (top-K via Bedrock embed + Cohere rerank). "
            "Use them to flag when a Notable / Featured item in this draft "
            "echoes recent coverage — call out the overlap and ask whether "
            "the new piece adds something the prior one didn't. Don't "
            "treat echoes as automatic problems (Jamie threads themes "
            "deliberately) but DO surface them so the commentary can "
            "acknowledge the prior take instead of restating it."
        ),
        error=echo_error,
    )
    user_msg = (
        f"{context.render_block(eddy_ctx)}\n\n{prompt}\n\n"
        f"---\n\n## Review target IDs\n\n"
        f"Use these IDs for hidden drawer connectors when a comment points at a specific place:\n\n"
        f"{target_legend}\n\n"
        f"---\n\n{echo_block}\n\n"
        f"---\n\nThe current draft (WT{n}):\n\n```markdown\n{draft_text}\n```"
    )
    with db.AgentRun("eddy", trigger="update-draft:html-review") as run:
        answer, _m = await eddy.core(latest=user_msg, history=[], model=_draft_review_model())
        run.record_meta(_m)
        run.records_written = 0 if (not answer or is_pass_response(answer)) else 1
    if not answer or is_pass_response(answer):
        # The LLM ran and explicitly said "nothing to flag" (or returned
        # an empty response, treated as the same). That's a real review
        # verdict — the prior pass's open comments are stale now and
        # shouldn't surface in the drawer. Close them so the next render
        # reads as the clean draft Eddy just verified.
        # (Errors from the LLM call would have raised before this line —
        # see the try/except in the caller — so this branch fires only
        # when Eddy successfully reviewed and found nothing.)
        try:
            closed = issue_items.close_all_open_comments(int(window["issue_number"]))
            if closed:
                logger.info(
                    "update-draft: PASS review closed %d open comment(s) for #%d",
                    closed, int(window["issue_number"]),
                )
        except Exception:  # noqa: BLE001
            logger.exception("update-draft: failed to close prior comments on PASS")
        return ""
    review_md = answer.strip()
    # Capture each target-anchored bullet as an editorial_comments row
    # AND embed the assigned handle next to its target marker so the
    # drawer can render a visible badge + copy button for each comment.
    # Best-effort — a parse failure shouldn't lose the review surface.
    try:
        _written, segment_handles = _store_review_comments(
            int(window["issue_number"]), review_md,
        )
        if any(segment_handles):
            review_md = _inject_handle_markers(review_md, segment_handles)
    except Exception:  # noqa: BLE001
        logger.exception("update-draft: review-comments capture failed")
    return review_md


# ---------- the job ----------

def _initial_progress(n: int) -> str:
    return (
        f"🔄 Refreshing **WT{n}** draft…\n"
        f"⏳ Pulling Pinboard + micro.blog + images _(slowest step)_\n"
        f"⏳ Editorial review (Opus)\n"
        f"⏳ HTML preview\n"
        f"⏳ Status card to #editorial"
    )


def _progress(
    n: int,
    *,
    header: Optional[str] = None,
    sources: str = "⏳",
    sources_detail: str = "_(slowest step)_",
    review: str = "⏳",
    review_detail: str = "",
    html: str = "⏳",
    html_detail: str = "",
    card: str = "⏳",
    card_detail: str = "",
) -> str:
    head = header or f"🔄 Refreshing **WT{n}** draft…"
    return (
        f"{head}\n"
        f"{sources} Pulling Pinboard + micro.blog + images{(' — ' + sources_detail) if sources_detail else ''}\n"
        f"{review} Editorial review (Opus){(' — ' + review_detail) if review_detail else ''}\n"
        f"{html} HTML preview{(' — ' + html_detail) if html_detail else ''}\n"
        f"{card} Status card to #editorial{(' — ' + card_detail) if card_detail else ''}"
    )


def _sources_summary(sync_result: dict, fills: dict) -> str:
    """One-line summary of what _gather_fills pulled, for the progress card."""
    bits: list[str] = []
    pinboard = sync_result.get("pinboard", {})
    if "error" in pinboard:
        bits.append(f"Pinboard error: {pinboard['error']}")
    else:
        observed = pinboard.get("observed", 0)
        if observed:
            bits.append(f"{observed} Pinboard items")
    microblog = sync_result.get("microblog", {})
    if "error" in microblog:
        bits.append(f"micro.blog error: {microblog['error']}")
    else:
        observed = microblog.get("observed", 0)
        if observed:
            bits.append(f"{observed} micro.blog entries")
    if not bits:
        return "no source updates"
    return ", ".join(bits)


async def _refresh_phase_card(ctx: "_base.JobContext", n: int, window: dict) -> None:
    """Refresh the phase-appropriate card in place — Build during `build`,
    Publish during `publish`. Best-effort; a Discord hiccup never fails the
    daily projection."""
    phase = (window or {}).get("phase", "build")
    try:
        if phase == "publish":
            from . import publish_card
            await publish_card.post_or_update(ctx, n, window=window)
        else:
            from . import build_card
            await build_card.post_or_update(ctx, n, window=window)
    except Exception:  # noqa: BLE001
        logger.exception("update-draft: phase card refresh failed for #%d", n)


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False,
            "❌ no active issue window — run `/eddy issue start <n> <pub-date> <days>` first.",
        )
    n = int(window["issue_number"])

    if _final_exists(n):
        return _base.JobResult(
            False,
            f"❌ issue #{n} is locked — `final.md` exists. Delete it to unlock `update-draft`.",
        )

    progress = await ctx.progress(
        "DISCORD_CHANNEL_EDITORIAL", _initial_progress(n), persona="eddy",
    )

    async def _refresh(**kwargs) -> None:
        if progress is not None:
            await progress.update(_progress(n, **kwargs))

    sources_detail = ""
    review_detail = ""
    html_detail = ""

    asset = f"{n}/draft.md"
    try:
        with _base.job_lock([asset], NAME):
            # ----- Step 1: pull from Pinboard + micro.blog + image rehost -----
            await _refresh(sources="🔄", sources_detail="_(running…)_")

            # Rebuild from the template every run so the section layout
            # always matches templates/draft_starter.md (the draft is a
            # pure projection — nothing on the old draft.md is preserved).
            text = _base.starter_template()
            # _gather_fills does blocking HTTP (Pinboard, micro.blog,
            # journal-image download/resize/upload) — off the event loop.
            # The actual sync result isn't returned by gather_fills today;
            # we re-derive a coarse summary from issue_items counts after
            # the fills are in.
            fills, alts_filled = await asyncio.to_thread(_gather_fills, window)
            for block in SECTION_BLOCKS:
                text = _base.replace_block(text, block, fills.get(block, ""))
            # Visibility: one line in #chatter per alt that was generated
            # and written back to micro.blog during the upstream sync.
            # Failures are best-effort — a missing channel id, lost Discord
            # connection, or a permission slip shouldn't fail the run.
            for filled in alts_filled:
                title = (filled.get("post_title") or "").strip() or "(untitled)"
                line = (
                    f"🔤 filled alt on [{title}]({filled['post_url']}): "
                    f'"{filled["alt"]}"'
                )
                try:
                    await ctx.post("DISCORD_CHANNEL_CHATTER", line)
                except Exception:  # noqa: BLE001
                    logger.exception("update-draft: failed to post alt-fill log to #chatter")
            try:
                s3.write_issue_file(n, "draft.md", text)
            except Exception as exc:  # noqa: BLE001
                logger.exception("update-draft: write failed for #%d", n)
                await _refresh(
                    header=f"❌ Refresh failed for **WT{n}** — couldn't write draft.md",
                    sources="❌", sources_detail=f"`{type(exc).__name__}: {exc}`",
                )
                return _base.JobResult(
                    False, f"❌ couldn't write `draft.md` for #{n}: `{type(exc).__name__}: {exc}`"
                )

            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

            # ----- Step 1b: daily render of buttondown.md + archive.md + transcript -----
            # The three pure renderers run alongside draft.md so the issue's
            # email / website / transcript artifacts always reflect current
            # state. Each renderer tolerates missing atoms (renders
            # placeholders); failures are logged but don't block the daily
            # projection — draft.md and the editorial review are what Jamie
            # is actually looking at this run. Step 4 of the refactor folds
            # send-to-buttondown / build-publish / compose-archive into
            # consumers of these artifacts.
            try:
                from ..tools import renderers
                render_result = await asyncio.to_thread(
                    renderers.render_all_for_issue, n, window=window,
                )
                if render_result.get("errors"):
                    logger.warning(
                        "update-draft: daily renders had errors for #%d: %s",
                        n, render_result["errors"],
                    )
            except Exception:  # noqa: BLE001 — daily renders are best-effort
                logger.exception("update-draft: daily renders failed for #%d", n)

            try:
                listing = s3.list_issue(n)
                files = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
            except Exception:  # noqa: BLE001
                files = set()
            st = draft_mod.section_status(n, draft_text=text, list_objects=files)
            prev_digest = db.latest_draft_digest(n)
            generated_at = datetime.now(_LOCAL_TZ)
            today = generated_at.date()
            stamp = generated_at.strftime("%Y-%m-%d %H:%M %Z")

            sources_detail = (
                f"{st['sections']['notable']['item_count']} Notable / "
                f"{st['sections']['brief']['item_count']} Briefly / "
                f"{st['sections']['journal']['item_count']} Journal · "
                f"~{st['word_count']}w"
            )

            # No-op short-circuit. If the projected draft is byte-identical to
            # the last run's (same source_hash), nothing material changed:
            # skip the Opus review, the HTML re-render, and the #editorial
            # re-post. The existing draft.html (with its review drawer) is
            # still valid, the prior open comments stay accurate, and a no-op
            # cron tick no longer floods the channel or burns an LLM call.
            # This is the common off-day case. (The ship console — wired
            # separately — still reads live DB + metadata each time, so a
            # metadata-only change surfaces there even when the body is flat.)
            prev_hash = (prev_digest or {}).get("source_hash")
            if prev_digest is not None and prev_hash == source_hash:
                html_url = s3.issue_file_url(n, "draft.html")
                # Still refresh the phase card — it reads live DB + metadata, so
                # a metadata-only change (subject set, CTA added, comment closed)
                # surfaces even when the draft body is byte-identical. No new
                # #editorial message; the pinned card is edited in place.
                await _refresh_phase_card(ctx, n, window)
                await _refresh(
                    header=f"✅ **WT{n}** — no changes since last refresh",
                    sources="✅", sources_detail=sources_detail,
                    review="✅", review_detail="skipped — draft unchanged",
                    html="✅", html_detail=f"[view]({html_url})",
                    card="✅", card_detail="console refreshed",
                )
                missing = ", ".join(st["required_missing"]) or "nothing"
                return _base.JobResult(
                    True,
                    f"no changes to `draft.md` for #{n} since last refresh "
                    f"(~{st['word_count']} words). Still missing for ship: {missing}.",
                    data={"issue_number": n, "section_status": st,
                          "preview_url": html_url, "unchanged": True},
                )

            # The editorial review is a *Build*-phase concern. During Publish
            # the content is frozen, so skip the Opus pass entirely (it would
            # only burn tokens and re-litigate a built issue).
            phase = window.get("phase", "build")
            review_md = ""
            if phase == "build":
                await _refresh(
                    sources="✅", sources_detail=sources_detail,
                    review="🧠", review_detail="_(Opus running…)_",
                )
                # ----- Step 2: editorial review (Opus) -----
                try:
                    review_md = await _draft_review(ctx, window, st, prev_digest, today, text)
                except Exception:  # noqa: BLE001
                    logger.exception("update-draft: HTML draft review failed for #%d", n)

            if review_md:
                # Rough comment count = number of "- " bullets in the review markdown.
                comment_count = sum(1 for line in review_md.splitlines() if line.lstrip().startswith("- "))
                review_detail = f"{comment_count} comment(s) captured"
            elif phase != "build":
                review_detail = "skipped (publish phase)"
            else:
                review_detail = "no comments (PASS or Eddy unavailable)"
            await _refresh(
                sources="✅", sources_detail=sources_detail,
                review="✅", review_detail=review_detail,
                html="🔄", html_detail="_(rendering + S3 upload + CDN invalidate)_",
            )

            # ----- Step 3: HTML preview render + S3 upload + CDN invalidate -----
            # Browser-viewable preview (no-cache + CDN invalidation); best-effort.
            # Subtitle carries the full local timestamp so anyone opening the
            # shareable link can tell at a glance whether they're looking at a
            # fresh projection or a stale one. Also surfaces the issue's
            # subject + description (metadata.json) and a row of convenience
            # links to the sibling artifacts the bot writes alongside the
            # draft (buttondown.md, archive.md, transcript-full.txt) so Jamie
            # can pull any of them from the same shareable page.
            try:
                # _load_metadata does an S3 read; keep it off the asyncio
                # loop the same way the render call below is.
                draft_meta = await asyncio.to_thread(renderers._load_metadata, n, window)
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: couldn't load metadata.json for #%d", n)
                draft_meta = None
            draft_links = [
                ("buttondown.md", s3.issue_file_url(n, "buttondown.md")),
                ("archive.md", s3.issue_file_url(n, "archive.md")),
                ("transcript-full.txt", s3.issue_file_url(n, "transcript-full.txt")),
            ]
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "draft", text,
                title=f"WT{n} — draft",
                subtitle=f"DRAFT · WT{n} · generated {stamp} · ~{st['word_count']} words · not the final issue",
                convenience_links=draft_links,
                meta=draft_meta,
                strip_block_markers=True, review_md=review_md,
            )
            html_detail = (f"[view]({html_url})" + (" (with review)" if review_md else "")) if html_url else "skipped"
            await _refresh(
                sources="✅", sources_detail=sources_detail,
                review="✅", review_detail=review_detail,
                html="✅", html_detail=html_detail,
                card="🔄", card_detail="_(refreshing console…)_",
            )

            # Refresh the phase card in place — this REPLACED the old per-tick
            # `📋` status + `✍️` review messages that flooded #editorial. The
            # Build card (during build) / Publish card (during publish) reads
            # live DB + S3 and carries the buttons. Best-effort.
            await _refresh_phase_card(ctx, n, window)

            await _refresh(
                header=f"✅ Refreshed **WT{n}** draft",
                sources="✅", sources_detail=sources_detail,
                review="✅", review_detail=review_detail,
                html="✅", html_detail=html_detail,
                card="✅", card_detail="posted",
            )

            try:
                db.insert_draft_digest(
                    issue=n,
                    word_count=st["word_count"],
                    notable_count=st["sections"]["notable"]["item_count"],
                    brief_count=st["sections"]["brief"]["item_count"],
                    journal_count=st["sections"]["journal"]["item_count"],
                    intro_present=st["intro_present"],
                    currently_present=st["currently_present"],
                    haiku_present=st["haiku_present"],
                    cover_present=st["cover_present"],
                    source_hash=source_hash,
                )
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: digest write failed for #%d", n)
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `update-draft` is already running ({exc.holder_desc}) — try again shortly."
        )

    missing = ", ".join(st["required_missing"]) or "nothing"
    view = (f" · 📄 {html_url}" + (" (with review — hit “Show review”)" if review_md else "")) if html_url else ""
    return _base.JobResult(
        True,
        f"refreshed `draft.md` for #{n} (~{st['word_count']} words; "
        f"{st['sections']['notable']['item_count']} Notable / "
        f"{st['sections']['brief']['item_count']} Briefly / "
        f"{st['sections']['journal']['item_count']} Journal){view}. "
        f"Still missing for ship: {missing}.".strip(),
        data={"issue_number": n, "section_status": st,
              "preview_url": html_url, "html_review": bool(review_md)},
    )
