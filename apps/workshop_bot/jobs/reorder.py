"""``reorder`` — Eddy's Notable/Briefly reorder pass.

Reads the current ``issue_items`` rows for the in-flight issue (Notable
+ Briefly + Journal), presents them to Eddy with stable synthetic ids
(``n1`` / ``b2`` / ``j3``), and asks for an **ordering-only** JSON
response:

```json
{
  "notable_order": ["n3", "n1", "n2", "n4"],
  "brief_order":   ["b2", "b1", "b4", "b3"]
}
```

Apply step is row mutations:

1. Validate the proposal shape and per-section permutations against the
   parsed synthetic ids.
2. Map each synthetic id back to its ``issue_items.id``.
3. Call :func:`issue_items.reorder` for Notable + Brief in the LLM's
   order. Journal is never reordered.
4. Re-render the three daily artifacts (``archive.md`` / ``buttondown.md`` /
   ``transcript/*.txt``) so the new ordering surfaces immediately.

Eddy posts to ``#editorial``: per-section was/now reorder map + a link
to the side-by-side ``final-proposal.html`` preview. Jamie reacts
✅ / ❌ / 🔄. On ❌ the existing row order survives. On 🔄 we re-prompt
up to :data:`_llm_job.MAX_REFRESH_ROUNDS`.

**Thesis lives elsewhere now.** This job used to also ask Eddy for a
1-3 sentence thesis and write ``thesis.md``. That moved to the
``compose-thesis`` job, which fires at ``mark-built`` (the Build →
Publish phase transition) — running over the *frozen* authored content,
not the in-flight draft. The phase transition is the natural place for
a framing that anchors every downstream Publish job.

**Other legacy that's also gone.** The name is from a retired era when
this job assembled an explicit ``final.md`` artifact, chose
``promotions`` (Journal entries to elevate), and proposed
``membership_blocks`` placements:

- ``final.md`` is gone — the three sibling renderers (archive / email /
  transcript) compose directly from row state + atoms; there's no
  intermediate assembled body.
- Promotions moved upstream to Jamie's micro.blog ``Featured`` tag.
- Membership-block placement is hardcoded in ``render_email`` via
  ``CTA_SLOT_POSITIONS``.

The slash command at ``/eddy issue reorder`` matches today's scope;
the internal trigger is ``reorder``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..tools import db, issue_items, issue_items_render, render, renderers, s3
from ..tools.discord import discord_io, interaction
from ..tools.llm import anthropic_client
from . import _base, _llm_job, compose_cta

logger = logging.getLogger("workshop.jobs.reorder")

NAME = "reorder"

_NEXT_STEPS = (
    "Next, in any order: `/eddy issue haiku`, `/eddy issue subject`, "
    "`/patty cta` — then `/scout issue publish` (it'll list "
    "anything still missing if you run it early)."
)

# When reorder lands with declared membership-block slots, the
# next deterministic step is compose-cta (Patty filling each slot).
# WT348 surfaced this as a forgetting-Patty failure mode: Jamie
# skipped /patty cta entirely and the shipped issue went out without
# the supporter CTA / premium thanks. Auto-firing it as a background
# task removes the remember-to-run gap without taking the pick
# decision away from Jamie (each slot still prompts him in
# #supporters via the standard refresh-loop UX).
_NEXT_STEPS_WITH_CTA_AUTOFIRE = (
    "Next: `/eddy issue haiku`, `/eddy issue subject`, then `/scout issue publish`. "
    "Patty's `compose-cta` auto-fires now — react in `#supporters` per slot."
)

# Synthetic-id prefix per section (the LLM-facing ids).
_SYNTH_PREFIX = {"notable": "n", "brief": "b", "journal": "j"}


# ---------- synthetic id maps ----------

def _build_synth_maps(
    rows_by_section: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, int], dict[int, str]]:
    """Assign ``n1``/``n2``/…/``b1``/…/``j1``/… in current-position
    order. Returns ``(synth_id → row_id, row_id → synth_id)``."""
    synth_to_row: dict[str, int] = {}
    row_to_synth: dict[int, str] = {}
    for section in ("notable", "brief", "journal"):
        prefix = _SYNTH_PREFIX[section]
        for i, row in enumerate(rows_by_section.get(section, []), start=1):
            synth = f"{prefix}{i}"
            synth_to_row[synth] = int(row["id"])
            row_to_synth[int(row["id"])] = synth
    return synth_to_row, row_to_synth


# ---------- LLM input formatting ----------

def _format_section_chunks(
    section: str, rows: list[dict[str, Any]], row_to_synth: dict[int, str],
) -> str:
    if not rows:
        return f"_(no {section.capitalize()} items)_"
    parts: list[str] = []
    for row in rows:
        synth = row_to_synth[int(row["id"])]
        title = (row.get("title") or "").strip() or row.get("url") or "(untitled)"
        url = (row.get("url") or "").strip()
        # Render the item the way it'll appear in the issue so Eddy sees
        # exactly what's on the table.
        if section == "notable":
            body = issue_items_render._render_notable_item(row)
        elif section == "brief":
            body = issue_items_render._render_brief_item(row)
        else:
            body = issue_items_render._render_journal_entry(row)
        parts.append(f"### `{synth}` — {title}\n{url}\n\n{body}")
    return "\n\n---\n\n".join(parts)


def _id_inventory_block(
    rows_by_section: dict[str, list[dict[str, Any]]],
    row_to_synth: dict[int, str],
) -> str:
    """Concrete count + id list per section, prefixed to the user message
    so the model sees the exact set its ``*_order`` must permute (and the
    exact count to self-check against). Opus on the live --model preferred
    run was dropping the tail of a 16-item Journal list; this surfaces
    the constraint upstream of the prose constraint in the system prompt."""
    lines = ["## ID inventory — every id below must appear in your output", ""]
    for section in ("notable", "brief", "journal"):
        ids = [row_to_synth[int(r["id"])] for r in rows_by_section.get(section, [])]
        section_title = "Briefly" if section == "brief" else section.capitalize()
        lines.append(
            f"- **{section_title}** ({len(ids)} item(s)): "
            f"{', '.join('`' + i + '`' for i in ids) if ids else '_none_'}"
        )
    lines.extend([
        "",
        "Your `notable_order` must cover every Notable id above exactly once. "
        "Your `brief_order` must cover every Brief id above exactly once. "
        "Journal entries are not reordered — every non-promoted Journal id "
        "stays in its natural publish-date position, so do not include a "
        "`journal_order` in your output (it will be ignored if you do). "
        "Promotions remain Journal-only.",
        "",
        "---",
        "",
    ])
    return "\n".join(lines)


def _build_user_message(
    base_prompt: str,
    issue_number: int,
    rows_by_section: dict[str, list[dict[str, Any]]],
    row_to_synth: dict[int, str],
) -> str:
    return (
        f"{base_prompt}\n\n"
        f"---\n\n"
        f"{_id_inventory_block(rows_by_section, row_to_synth)}"
        f"## Parsed items for WT{issue_number}\n\n"
        f"### Notable items\n\n"
        f"{_format_section_chunks('notable', rows_by_section['notable'], row_to_synth)}\n\n"
        f"---\n\n"
        f"### Briefly items\n\n"
        f"{_format_section_chunks('brief', rows_by_section['brief'], row_to_synth)}\n\n"
        f"---\n\n"
        f"### Journal entries\n\n"
        f"{_format_section_chunks('journal', rows_by_section['journal'], row_to_synth)}\n"
    )


# ---------- proposal validation ----------

class _ProposalError(Exception):
    """Operator-readable validation failure; surfaces to #editorial."""


def _validate_proposal_shape(data: dict) -> None:
    # Journal entries are no longer reordered — Eddy is told not to send a
    # journal_order. Promotions moved upstream (micro.blog Featured tag).
    # membership_blocks was retired — placement is hardcoded in
    # render_email via CTA_SLOT_POSITIONS. Any of those three fields are
    # tolerated-and-ignored if they show up in the LLM output anyway.
    required = ("notable_order", "brief_order")
    missing = [k for k in required if k not in data]
    if missing:
        raise _ProposalError(f"missing field(s) in JSON: {', '.join(missing)}")
    for k in ("notable_order", "brief_order"):
        if not isinstance(data[k], list) or not all(isinstance(x, str) for x in data[k]):
            raise _ProposalError(f"`{k}` must be a list of id strings")


def _patch_missing_ids_into_orders(
    data: dict,
    synth_section: dict[str, str],
) -> list[str]:
    """If the LLM dropped ids from any ``*_order`` array, append the
    omitted ids to the end of that section in original (synth-id sort)
    order. Returns the list of patched ids for surfacing in ``#editorial``.

    Auto-fix safety net: even with the strengthened prompt and ID-inventory
    header, the LLM occasionally drops a tail item. Rather than fall through
    to passthrough (which loses the entire editorial pass), keep the
    reorder and silently include the missing items. The note in
    ``#editorial`` lets Jamie spot the patch and override if needed.
    """
    patched: list[str] = []
    for section in ("notable", "brief"):
        order = list(data.get(f"{section}_order") or [])
        want = sorted(
            (sid for sid, sect in synth_section.items() if sect == section),
            key=lambda s: int("".join(ch for ch in s if ch.isdigit()) or "0"),
        )
        missing = [sid for sid in want if sid not in set(order)]
        if missing:
            data[f"{section}_order"] = order + missing
            patched.extend(missing)
    return patched


def _validate_per_section_orders(
    data: dict,
    synth_section: dict[str, str],
) -> None:
    """Each *_order must be a strict permutation of the synth ids in that
    section. Journal is never in the loop — entries always preserve their
    natural publish-date order."""
    for section in ("notable", "brief"):
        order = data[f"{section}_order"]
        want = [sid for sid, sect in synth_section.items() if sect == section]
        want_set = set(want)
        order_set: set[str] = set()
        dupes: list[str] = []
        for sid in order:
            if sid in order_set:
                dupes.append(sid)
            order_set.add(sid)
        if dupes:
            raise _ProposalError(
                f"{section}_order: duplicate id(s): {', '.join(sorted(set(dupes)))}"
            )
        extra = sorted(order_set - want_set)
        if extra:
            raise _ProposalError(
                f"{section}_order: id(s) not in this section: {', '.join(extra)}"
            )
        missing = sorted(want_set - order_set)
        if missing:
            raise _ProposalError(
                f"{section}_order: missing id(s): {', '.join(missing)}"
            )


# ---------- editorial-surface rendering ----------

def _row_label(row: dict[str, Any]) -> str:
    title = (row.get("title") or "").strip()
    if title:
        return title
    meta = row.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("label"):
        return str(meta["label"]).strip()
    return (row.get("url") or "").strip() or f"row#{row.get('id')}"


def _render_was_now(
    rows: list[dict[str, Any]],
    order_synth: list[str],
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
    *,
    kind_label: str,
) -> str:
    if not rows:
        return f"**{kind_label}** — _(empty)_"
    original_synth = [row_to_synth[int(r["id"])] for r in rows]
    if original_synth == list(order_synth):
        return f"**{kind_label}** — no change"
    by_synth = {row_to_synth[int(r["id"])]: r for r in rows}
    def titles_for(ids):
        return " · ".join(f"{i+1}. {_row_label(by_synth[sid])}" for i, sid in enumerate(ids))
    return (
        f"**{kind_label}** — reordered\n"
        f"  was: {titles_for(original_synth)}\n"
        f"  now: {titles_for(order_synth)}"
    )


def _render_journal_preserved(
    rows: list[dict[str, Any]],
    row_to_synth: dict[int, str],
) -> str:
    """Journal-section card for the editorial proposal. Journal is never
    reordered — this just shows the items as they'll appear in the issue,
    in their natural publish-date order, so Jamie can confirm the section."""
    if not rows:
        return "**Journal** — _(empty)_"
    titles = " · ".join(
        f"{i+1}. {_row_label(r)}" for i, r in enumerate(rows)
    )
    return f"**Journal** — preserved in publish order\n  {titles}"


def _render_featured_plan(featured_rows: list[dict[str, Any]]) -> str:
    """Surface Featured-from-micro.blog posts in the editorial card —
    these came from Jamie's upstream ``Featured`` category tag (not
    Eddy's call) and render as standalone H2 sections above Notable."""
    if not featured_rows:
        return ""
    lines = [
        f"**Featured (from micro.blog \"Featured\" category):** "
        f"{len(featured_rows)} post(s) elevated to standalone section(s) above Notable"
    ]
    for r in featured_rows:
        heading = (r.get("promoted_heading") or "").strip() or _row_label(r)
        url = (r.get("url") or "").strip()
        lines.append(f"  · \"{heading}\" — {url}")
    return "\n".join(lines)


def _render_editorial_card(
    issue_number: int,
    rows_by_section: dict[str, list[dict[str, Any]]],
    data: dict,
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
    rows_by_id: dict[int, dict[str, Any]],
    featured_rows: Optional[list[dict[str, Any]]] = None,
) -> str:
    parts = [
        f"📝 **reorder** for WT{issue_number}",
        "",
        _render_was_now(rows_by_section["notable"], data["notable_order"], synth_to_row, row_to_synth, kind_label="Notable"),
        _render_was_now(rows_by_section["brief"], data["brief_order"], synth_to_row, row_to_synth, kind_label="Briefly"),
        _render_journal_preserved(rows_by_section["journal"], row_to_synth),
    ]
    featured_card = _render_featured_plan(featured_rows or [])
    if featured_card:
        parts.extend(["", featured_card])
    return "\n".join(parts)


# ---------- apply ----------

def _apply_proposal(
    issue_number: int,
    data: dict,
    synth_to_row: dict[str, int],
) -> None:
    """Mutate ``issue_items`` to match Eddy's plan: reorder Notable and
    Brief. Journal is never reordered — entries always keep the position
    update-draft set from their micro.blog publish_date. Featured
    posts (is_promoted=1 from sync) are untouched here — they were set
    upstream by Jamie's ``Featured`` micro.blog category, not by Eddy."""
    for section in ("notable", "brief"):
        order_synth = data[f"{section}_order"]
        ordered_row_ids = [synth_to_row[sid] for sid in order_synth]
        if ordered_row_ids:
            issue_items.reorder(issue_number, section, ordered_row_ids)


# ---------- I/O ----------

_ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"


def _schedule_compose_cta(
    ctx: "_base.JobContext", *, issue_number: int, slots_declared: int,
) -> None:
    """Fire ``compose-cta`` as a background asyncio task so reorder
    can return immediately. Any error inside compose-cta is logged
    rather than re-raised — the JobResult for reorder has already
    been built and the user's slash ack is in flight; an exception
    here would land nowhere useful.
    """
    async def _run() -> None:
        try:
            result = await compose_cta.run(ctx)
            logger.info(
                "reorder → compose-cta autofire for WT%d (%d slot(s)): %s",
                issue_number, slots_declared, getattr(result, "message", ""),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "reorder → compose-cta autofire failed for WT%d",
                issue_number,
            )

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running loop (test contexts without an event loop). Skip
        # silently — the test harness drives compose-cta directly.
        logger.debug("reorder: no event loop for compose-cta autofire")


def _md_html_links(issue_number: int, name: str, html_url: Optional[str]) -> str:
    md_url = f"{_ASSETS_BASE}/{issue_number}/{name}.md"
    if html_url:
        return f"\n\n📄 [HTML]({html_url}) · 📝 [markdown]({md_url})"
    return f"\n\n📝 [markdown]({md_url})"


# ---------- main ----------

async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])

    # Row snapshot for the LLM. include_promoted=True so an item Eddy
    # already promoted (rare — we clear promotions on apply, but a manual
    # mid-run change could leave one) is still visible; the prompt's
    # `*_order` is over non-promoted ids only, but Eddy needs to see what
    # exists in the section to recompute.
    rows_by_section = {
        "notable": issue_items.list_items(n, section="notable", include_promoted=False),
        "brief": issue_items.list_items(n, section="brief", include_promoted=False),
        "journal": issue_items.list_items(n, section="journal", include_promoted=False),
    }
    if not any(rows_by_section.values()):
        return _base.JobResult(
            False, f"❌ no `issue_items` rows for WT{n} — run `/scout issue update` first.",
        )

    synth_to_row, row_to_synth = _build_synth_maps(rows_by_section)
    synth_section: dict[str, str] = {}
    for section, rows in rows_by_section.items():
        for row in rows:
            synth_section[row_to_synth[int(row["id"])]] = section
    rows_by_id = {int(r["id"]): r for rs in rows_by_section.values() for r in rs}

    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(False, f"(reorder skipped — {reason})")

    # Lock on issue_items so a concurrent /eddy issue reorder doesn't
    # race row mutations — the asset key is symbolic now that final.md
    # is no longer written.
    asset = f"{n}/issue_items"
    _html_url: Optional[str] = None
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-reorder")
            base_user_msg = _build_user_message(base_prompt, n, rows_by_section, row_to_synth)
            user_msg = base_user_msg[: _llm_job.CREATE_FINAL_BODY_CAP]

            for _round in range(_llm_job.MAX_REFRESH_ROUNDS):
                with db.AgentRun("eddy", trigger="reorder") as agent_run:
                    # Sonnet default — reorder is a constrained editorial
                    # decision (ordering N items), well within Sonnet's
                    # range. The substantive editorial pass is
                    # update-draft:html-review (Opus).
                    reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                    agent_run.record_meta(_meta)
                    agent_run.records_written = 1
                data = _llm_job.parse_json_payload(reply or "")
                try:
                    if data is None:
                        raise _ProposalError("response wasn't a parseable JSON object")
                    _validate_proposal_shape(data)
                    _validate_per_section_orders(data, synth_section)
                except _ProposalError as exc:
                    # Auto-fix path: if the only failure is "missing id(s)"
                    # in one of the *_order arrays, append the omitted ids
                    # in original order and re-validate. Preserves the
                    # editorial reorder + thesis rather than dropping the
                    # whole proposal to passthrough. Other shape /
                    # permutation errors fall through to the LLM retry.
                    auto_fixed = False
                    if data is not None and ": missing id(s):" in str(exc):
                        patched = _patch_missing_ids_into_orders(
                            data, synth_section,
                        )
                        if patched:
                            try:
                                _validate_per_section_orders(
                                    data, synth_section,
                                )
                            except _ProposalError:
                                # Auto-patch didn't fully resolve; fall
                                # through to the normal retry path.
                                pass
                            else:
                                await channel.send(
                                    f"🛠️ Eddy's proposal for WT{n} omitted "
                                    f"{', '.join('`' + p + '`' for p in patched)} "
                                    f"— appended in original order to keep the rest "
                                    f"of the proposal intact. Override with "
                                    f"`/scout issue reset final` if the auto-fix is "
                                    f"the wrong call.",
                                    suppress_embeds=True,
                                )
                                auto_fixed = True

                    if auto_fixed:
                        # data is now valid; fall through to the approval
                        # card below.
                        pass
                    else:
                        await channel.send(
                            f"⚠️ Eddy's `reorder` proposal for WT{n} didn't validate: "
                            f"`{exc}` — retrying with a tighter hint.",
                            suppress_embeds=True,
                        )
                        user_msg = (base_user_msg + (
                            f"\n\n(That response was rejected: `{exc}`. Follow the JSON schema "
                            f"exactly — every parsed id must appear exactly once in its "
                            f"section's order.)"
                        ))[: _llm_job.CREATE_FINAL_BODY_CAP]
                        continue

                # Editorial card → #editorial; Jamie ✅/❌/🔄. Render the
                # side-by-side proposal page so Jamie can see current vs
                # proposed with connector lines in the browser.
                # Best-effort: a render hiccup just omits the URL from
                # the Discord prompt — the card text is the canonical
                # decision surface.
                proposal_url = await asyncio.to_thread(
                    render.render_and_upload_proposal,
                    issue_number=n, thesis="",
                    rows_by_section=rows_by_section, proposal=data,
                    synth_to_row=synth_to_row, row_to_synth=row_to_synth,
                )
                # Featured-category posts come from upstream micro.blog tags
                # (not Eddy). Surface them on the editorial card so Jamie sees
                # what got elevated above Notable.
                featured_rows = [
                    r for r in issue_items.list_items(n, section="journal", include_promoted=True)
                    if r.get("is_promoted")
                ]
                card = _render_editorial_card(
                    n, rows_by_section, data,
                    synth_to_row, row_to_synth, rows_by_id,
                    featured_rows=featured_rows,
                )
                if proposal_url:
                    card = card + f"\n\n📄 [side-by-side view]({proposal_url})"
                for part in discord_io.split_for_discord(card):
                    await channel.send(part, suppress_embeds=True)
                approved = await interaction.await_approval(
                    bot, channel,
                    prompt=(
                        f"Accept Eddy's reorder for WT{n}? "
                        f"(❌ leaves the existing row order alone.)"
                    ),
                )
                if approved == "refresh":
                    user_msg = base_user_msg + "\n\n(Jamie wants a different cut — try again.)"
                    continue

                if approved is True:
                    # Apply: mutate rows. The daily renderers pull from
                    # the mutated DB state. Thesis + Echoes are no longer
                    # written here — compose-thesis and compose-echoes
                    # both fire at mark-built over the frozen content.
                    await asyncio.to_thread(_apply_proposal, n, data, synth_to_row)
                    # Render the three artifacts now so they reflect the
                    # new ordering immediately (the next update-draft tick
                    # would catch up, but give Jamie a current preview).
                    try:
                        await asyncio.to_thread(
                            renderers.render_all_for_issue, n, window=window,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("reorder: post-apply render failed for #%d", n)
                else:
                    # ❌ — leave rows as-is. Daily renderers next tick.
                    pass

                draft_url = s3.issue_file_url(n, "draft.html")
                next_steps = _NEXT_STEPS
                await channel.send(
                    f"✅ Reorder applied for WT{n}.\n"
                    f"📄 [draft]({draft_url}) · 📄 [side-by-side]({proposal_url})\n\n{next_steps}"
                    if approved is True
                    else f"↩️ Reorder rejected for WT{n} — rows left as-is. {next_steps}",
                    suppress_embeds=True,
                )
                return _base.JobResult(
                    True,
                    f"Reorder applied for WT{n}"
                    if approved is True
                    else f"Reorder rejected for WT{n} — rows unchanged",
                    data={
                        "issue_number": n,
                        "preview_url": draft_url,
                    },
                )

            # Refresh rounds exhausted — leave rows as-is.
            await channel.send(
                f"⚠️ `/eddy issue reorder` for WT{n} couldn't get a valid proposal after "
                f"{_llm_job.MAX_REFRESH_ROUNDS} attempts. Rows left as-is; "
                "re-run `/eddy issue reorder` if you want another pass.",
                suppress_embeds=True,
            )
            return _base.JobResult(
                True,
                f"`reorder` for WT{n} exhausted retries; rows unchanged. {_NEXT_STEPS}",
                data={"issue_number": n, "thesis_written": False},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `reorder` already running ({exc.holder_desc}).")
