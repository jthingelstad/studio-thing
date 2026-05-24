"""``create-final`` — Eddy's editorial pass on the row-backed model.

Reads ``issue_items`` rows for the in-flight issue (Notable / Briefly,
plus the non-promoted Journal rows), presents them to Eddy with stable
synthetic ids (``n1``, ``b2``, ``j3``), and asks for an **ordering-only**
JSON response:

```json
{
  "thesis": "…",
  "notable_order": ["n3", "n1", "n2", "n4"],
  "brief_order":   ["b2", "b1", "b4", "b3"],
  "membership_blocks": [
    {"kind": "cta",    "after": "n1", "rationale": "…"},
    {"kind": "cta",    "before_haiku": true, "rationale": "…"},
    {"kind": "thanks", "after": "n2", "rationale": "…"}
  ]
}
```

**Apply step is row mutations, not byte-chunk reassembly.** Code:

1. Validates the proposal shape, membership_blocks, and per-section
   permutations against the parsed synthetic ids.
2. Maps each synthetic id back to its ``issue_items.id``.
3. Calls :func:`issue_items.reorder` for Notable + Brief in the LLM's
   order. Journal is never reordered.
4. Renders ``final.md`` from rows using :mod:`tools.issue_assembly`:
   atoms (intro / currently / cover / outro / haiku) come verbatim
   from their files; parent sections render in current position order
   with cta/thanks markers spliced inline; Featured-category posts
   appear as ``## Heading`` sections at the fixed ``before_notable``
   slot — what Jamie sees in ``final.md`` IS where things will land in
   the published email.
5. Writes ``final.md`` and ``thesis.md``.

Featured posts come from Jamie's upstream micro.blog ``Featured``
category (set by the sync layer in :mod:`tools.issue_items_sync`).
Eddy used to choose promotions; that role moved upstream. Eddy still
sees Featured posts surfaced separately in the editorial card so he
knows which entries were elevated, but they don't appear in the
parsed Journal list and Eddy doesn't propose them.

The LLM never touches bytes — identity comes from row id. The old
chunk parser + multiset lossless check are retired (the row model
guarantees losslessness by construction; an UPDATE on a position
column can't drop, duplicate, or mutate a row).

Eddy posts to ``#editorial``: thesis, per-section was/now reorder
map, Featured posts (from upstream), membership-block plan. Jamie
reacts ✅ / ❌ / 🔄. On ❌ the existing row order survives and the
section bodies render in their pre-create-final order (no thesis,
no markers). On 🔄 we re-prompt up to
:data:`_llm_job.MAX_REFRESH_ROUNDS`.

Refuses if ``final.md`` already exists — delete it explicitly to
re-run (or use ``/eddy issue reset final``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..tools import db, issue_items, issue_items_render, render, renderers, s3
from ..tools.discord import discord_io, interaction
from ..tools.llm import anthropic_client
from . import _base, _cover, _currently, _llm_job, compose_closer, compose_cta

logger = logging.getLogger("workshop.jobs.create_final")

NAME = "create-final"

_NEXT_STEPS = (
    "Next, in any order: `/eddy issue haiku`, `/eddy issue subject`, "
    "`/patty cta` — then `/eddy issue publish` (it'll list "
    "anything still missing if you run it early)."
)

# When create-final lands with declared membership-block slots, the
# next deterministic step is compose-cta (Patty filling each slot).
# WT348 surfaced this as a forgetting-Patty failure mode: Jamie
# skipped /patty cta entirely and the shipped issue went out without
# the supporter CTA / premium thanks. Auto-firing it as a background
# task removes the remember-to-run gap without taking the pick
# decision away from Jamie (each slot still prompts him in
# #supporters via the standard refresh-loop UX).
_NEXT_STEPS_WITH_CTA_AUTOFIRE = (
    "Next: `/eddy issue haiku`, `/eddy issue subject`, then `/eddy issue publish`. "
    "Patty's `compose-cta` auto-fires now — react in `#supporters` per slot."
)

# Hard caps on Eddy's declarations (enforced after parse).
_MAX_CTA = 2
_MAX_THANKS = 1
# Promotions used to be Eddy's call (he picked up to 2 Journal entries to
# elevate to standalone featured sections). That moved to the upstream
# micro.blog ``Featured`` category — see ``tools/issue_items_sync.py``.
# Eddy doesn't propose promotions any more.

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
    # journal_order. Promotions also moved out of Eddy's hands (the
    # micro.blog Featured category drives them at sync time now). Both
    # fields are tolerated-and-ignored if they show up in the LLM output
    # anyway (LLM habit). Only thesis + Notable + Brief + membership are
    # required.
    required = ("thesis", "notable_order", "brief_order", "membership_blocks")
    missing = [k for k in required if k not in data]
    if missing:
        raise _ProposalError(f"missing field(s) in JSON: {', '.join(missing)}")
    if not isinstance(data.get("thesis"), str) or not data["thesis"].strip():
        raise _ProposalError("`thesis` must be a non-empty string")
    for k in ("notable_order", "brief_order"):
        if not isinstance(data[k], list) or not all(isinstance(x, str) for x in data[k]):
            raise _ProposalError(f"`{k}` must be a list of id strings")
    if not isinstance(data["membership_blocks"], list):
        raise _ProposalError("`membership_blocks` must be a list")


def _patch_missing_ids_into_orders(
    data: dict,
    synth_section: dict[str, str],
    promoted_synth: set[str],
) -> list[str]:
    """If the LLM dropped ids from any ``*_order`` array, append the
    omitted ids to the end of that section in original (synth-id sort)
    order. Returns the list of patched ids for surfacing in ``#editorial``.

    This is the auto-fix safety net: even with the strengthened prompt
    and ID-inventory header, Opus on long Journal lists still
    occasionally drops the tail. Rather than fall through to passthrough
    (which loses the entire editorial pass — thesis, promotions,
    membership-block placement, every other section's reorder), keep
    the reorder and silently include the missing items. The note in
    ``#editorial`` lets Jamie spot the patch and override if needed.
    """
    patched: list[str] = []
    for section in ("notable", "brief"):
        order = list(data.get(f"{section}_order") or [])
        want = sorted(
            (sid for sid, sect in synth_section.items()
             if sect == section and sid not in promoted_synth),
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
    promoted_synth: set[str],
) -> None:
    """Each *_order must be a permutation of (synth ids in that section
    minus promoted ids). Journal is no longer in the loop — entries always
    preserve their natural publish-date order."""
    for section in ("notable", "brief"):
        order = data[f"{section}_order"]
        want = [sid for sid, sect in synth_section.items() if sect == section and sid not in promoted_synth]
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
                f"{section}_order: id(s) not in this section (or promoted): {', '.join(extra)}"
            )
        missing = sorted(want_set - order_set)
        if missing:
            raise _ProposalError(
                f"{section}_order: missing id(s): {', '.join(missing)}"
            )


def _validate_membership_blocks(
    blocks: list, synth_section: dict[str, str], promoted_synth: set[str],
) -> None:
    cta_count = 0
    thanks_count = 0
    for i, b in enumerate(blocks):
        if not isinstance(b, dict):
            raise _ProposalError(f"membership_blocks[{i}] is not an object")
        kind = b.get("kind")
        if kind not in ("cta", "thanks"):
            raise _ProposalError(
                f"membership_blocks[{i}].kind must be 'cta' or 'thanks' (got {kind!r})"
            )
        has_after = "after" in b
        has_before = bool(b.get("before_haiku"))
        if has_after == has_before:
            raise _ProposalError(
                f"membership_blocks[{i}] must have exactly one of `after` (an item id) "
                f"or `before_haiku: true`"
            )
        if has_after:
            aid = b["after"]
            if not isinstance(aid, str) or aid not in synth_section:
                raise _ProposalError(
                    f"membership_blocks[{i}].after={aid!r} doesn't match any parsed id"
                )
            if aid in promoted_synth:
                raise _ProposalError(
                    f"membership_blocks[{i}].after={aid!r} is a promoted id; "
                    f"membership-block `after` cannot point at a promoted item"
                )
        if kind == "cta":
            cta_count += 1
        else:
            thanks_count += 1
    if cta_count > _MAX_CTA:
        raise _ProposalError(f"too many cta blocks ({cta_count}); max {_MAX_CTA}")
    if thanks_count > _MAX_THANKS:
        raise _ProposalError(f"too many thanks blocks ({thanks_count}); max {_MAX_THANKS}")


# ---------- marker assignment ----------

def _assign_markers(
    blocks: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], list[str], list[tuple[str, dict]]]:
    """Walk membership_blocks in declaration order, assigning each one a
    1-indexed marker. Returns ``(markers_after_synth, before_haiku,
    plan)``:

    - ``markers_after_synth`` — synth_id → list of marker strings
    - ``before_haiku`` — markers slated for the last non-empty section
    - ``plan`` — ordered ``[(marker, block_meta), …]`` for the
      editorial-card rendering (so it can show "cta:1 after n2 — …")
    """
    markers_after: dict[str, list[str]] = {}
    before_haiku: list[str] = []
    kind_counts: dict[str, int] = {}
    plan: list[tuple[str, dict]] = []
    for b in blocks:
        kind = b["kind"]
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        marker = f"<!-- {kind}:{kind_counts[kind]} -->"
        plan.append((marker, b))
        if b.get("before_haiku"):
            before_haiku.append(marker)
        else:
            markers_after.setdefault(b["after"], []).append(marker)
    return markers_after, before_haiku, plan


def _trailing_markers_target(
    notable_rows: list[dict[str, Any]],
    journal_rows: list[dict[str, Any]],
    brief_rows: list[dict[str, Any]],
) -> str:
    """Pick which section's trailing-markers slot the ``before_haiku``
    markers land in. Order of preference matches the publish flow: end
    of Briefly, else Journal, else Notable."""
    if brief_rows:
        return "brief"
    if journal_rows:
        return "journal"
    if notable_rows:
        return "notable"
    return "brief"  # degenerate — empty issue


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
    promoted_synth: set[str] = frozenset(),
) -> str:
    if not rows:
        return f"**{kind_label}** — _(empty)_"
    rows_in_section = [r for r in rows if row_to_synth[int(r["id"])] not in promoted_synth]
    original_synth = [row_to_synth[int(r["id"])] for r in rows_in_section]
    promoted_in_section = [r for r in rows if row_to_synth[int(r["id"])] in promoted_synth]
    promoted_note = f" ({len(promoted_in_section)} promoted out)" if promoted_in_section else ""
    if original_synth == list(order_synth):
        if not original_synth:
            return f"**{kind_label}** — _(empty after promotion)_"
        return f"**{kind_label}** — no change{promoted_note}"
    by_synth = {row_to_synth[int(r["id"])]: r for r in rows}
    titles_for = lambda ids: " · ".join(
        f"{i+1}. {_row_label(by_synth[sid])}" for i, sid in enumerate(ids)
    )
    return (
        f"**{kind_label}** — reordered{promoted_note}\n"
        f"  was: {titles_for(original_synth)}\n"
        f"  now: {titles_for(order_synth)}"
    )


def _render_journal_preserved(
    rows: list[dict[str, Any]],
    row_to_synth: dict[int, str],
    *,
    promoted_synth: set[str] = frozenset(),
) -> str:
    """Journal-section card for the editorial proposal. Journal is never
    reordered (see _apply_proposal); this just shows the items as they'll
    appear in the issue, in their natural publish-date order, with a count
    of any promoted-out items so Jamie can confirm the section's intact."""
    if not rows:
        return "**Journal** — _(empty)_"
    rows_in_section = [r for r in rows if row_to_synth[int(r["id"])] not in promoted_synth]
    promoted_in_section = [r for r in rows if row_to_synth[int(r["id"])] in promoted_synth]
    promoted_note = f" ({len(promoted_in_section)} promoted out)" if promoted_in_section else ""
    if not rows_in_section:
        return f"**Journal** — _(empty after promotion){promoted_note}_"
    titles = " · ".join(
        f"{i+1}. {_row_label(r)}" for i, r in enumerate(rows_in_section)
    )
    return f"**Journal** — preserved in publish order{promoted_note}\n  {titles}"


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


def _render_membership_plan(
    blocks: list[dict[str, Any]],
    synth_to_row: dict[str, int],
    rows_by_id: dict[int, dict[str, Any]],
) -> str:
    if not blocks:
        return "**Membership blocks:** _(none — this issue runs clean)_"
    lines = [f"**Membership blocks:** {len(blocks)} slot(s)"]
    kind_counts: dict[str, int] = {}
    for b in blocks:
        kind = b["kind"]
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        n = kind_counts[kind]
        marker = f"`{kind}:{n}`"
        if b.get("before_haiku"):
            position = "before haiku"
        else:
            aid = b["after"]
            row = rows_by_id.get(synth_to_row[aid], {})
            position = f"after \"{_row_label(row)}\" (`{aid}`)"
        rationale = (b.get("rationale") or "").strip()
        line = f"  · {marker} {position}"
        if rationale:
            line += f" — {rationale}"
        lines.append(line)
    return "\n".join(lines)


def _render_editorial_card(
    issue_number: int,
    thesis: str,
    rows_by_section: dict[str, list[dict[str, Any]]],
    data: dict,
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
    rows_by_id: dict[int, dict[str, Any]],
    featured_rows: Optional[list[dict[str, Any]]] = None,
) -> str:
    parts = [
        f"📝 **create-final** for WT{issue_number}",
        "",
        f"**Thesis:** {thesis.strip()}",
        "",
        _render_was_now(rows_by_section["notable"], data["notable_order"], synth_to_row, row_to_synth, kind_label="Notable"),
        _render_was_now(rows_by_section["brief"], data["brief_order"], synth_to_row, row_to_synth, kind_label="Briefly"),
        _render_journal_preserved(rows_by_section["journal"], row_to_synth),
    ]
    featured_card = _render_featured_plan(featured_rows or [])
    if featured_card:
        parts.extend(["", featured_card])
    parts.extend(["", _render_membership_plan(data["membership_blocks"], synth_to_row, rows_by_id)])
    return "\n".join(parts)


# ---------- atoms (file-backed) ----------

def _read_atom(n: int, filename: str) -> str:
    res = s3.read_issue_file(n, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"].strip()
    return ""


def _build_atoms(n: int) -> dict[str, str]:
    """Read intro / outro / haiku verbatim; render cover + currently via
    their structured-JSON helpers. The cover block also leads with a
    native ``<img>`` tag carrying the issue's cover URL + alt.

    Identical to what ``update-draft._gather_fills`` does for these
    blocks; centralized here so ``create-final`` reads from the same
    source of truth.
    """
    from html import escape as _esc

    atoms: dict[str, str] = {
        "intro": _read_atom(n, "intro.md"),
        "outro": _read_atom(n, "outro.md"),
        "haiku": _base.format_haiku(_read_atom(n, "haiku.md")),
        "cover": _cover.render(n),
        "currently": _currently.render(n),
    }
    if atoms["cover"]:
        cover_alt = _cover.alt(n)
        cover_img = (
            f'<img src="https://files.thingelstad.com/weekly-thing/{n}/cover.jpg" '
            f'alt="{_esc(cover_alt, quote=True)}" />'
        )
        atoms["cover"] = f"{cover_img}\n\n{atoms['cover']}"
    return atoms


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


# ---------- final.md render ----------

def _render_final(
    issue_number: int,
    atoms: dict[str, str],
    data: dict,
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
    *,
    closer: str = "",
) -> str:
    """Build a baseline body for compose-closer to read.

    No marker plumbing — the closer just needs prose to ground its
    archive-retrieval call. Composes via ``renderers.render_archive_body``
    (the same path the archive renderer uses), then closer adds its
    own paragraph downstream. Output is never written to disk; it's
    only handed to compose_closer.
    """
    notable_rows = issue_items.list_items(issue_number, section="notable", include_promoted=False)
    journal_rows = issue_items.list_items(issue_number, section="journal", include_promoted=False)
    brief_rows = issue_items.list_items(issue_number, section="brief", include_promoted=False)
    promoted_rows = issue_items.promoted_items(issue_number)

    section_bodies = {
        "notable": issue_items_render.render_notable(notable_rows, issue_number),
        "journal": issue_items_render.render_journal(journal_rows),
        "brief": issue_items_render.render_brief(brief_rows),
    }
    features = [
        (r["promoted_position"], issue_items_render.render_featured_section(r))
        for r in promoted_rows if r.get("promoted_position")
    ]

    return renderers.render_archive_body(
        atoms=atoms, sections=section_bodies, features=features, closer=closer,
    )


# ---------- I/O ----------

_ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"


def _schedule_compose_cta(
    ctx: "_base.JobContext", *, issue_number: int, slots_declared: int,
) -> None:
    """Fire ``compose-cta`` as a background asyncio task so create-final
    can return immediately. Any error inside compose-cta is logged
    rather than re-raised — the JobResult for create-final has already
    been built and the user's slash ack is in flight; an exception
    here would land nowhere useful.
    """
    async def _run() -> None:
        try:
            result = await compose_cta.run(ctx)
            logger.info(
                "create-final → compose-cta autofire for WT%d (%d slot(s)): %s",
                issue_number, slots_declared, getattr(result, "message", ""),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "create-final → compose-cta autofire failed for WT%d",
                issue_number,
            )

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running loop (test contexts without an event loop). Skip
        # silently — the test harness drives compose-cta directly.
        logger.debug("create-final: no event loop for compose-cta autofire")


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
            False, f"❌ no `issue_items` rows for WT{n} — run `/eddy issue update` first.",
        )

    synth_to_row, row_to_synth = _build_synth_maps(rows_by_section)
    synth_section: dict[str, str] = {}
    for section, rows in rows_by_section.items():
        for row in rows:
            synth_section[row_to_synth[int(row["id"])]] = section
    rows_by_id = {int(r["id"]): r for rs in rows_by_section.values() for r in rs}

    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(False, f"(create-final skipped — {reason})")

    # Lock on issue_items so a concurrent /eddy issue reorder doesn't
    # race row mutations — the asset key is symbolic now that final.md
    # is no longer written.
    asset = f"{n}/issue_items"
    html_url: Optional[str] = None
    try:
        with _base.job_lock([asset], NAME):
            atoms = _build_atoms(n)
            base_prompt = anthropic_client.load_prompt("eddy-create-final")
            base_user_msg = _build_user_message(base_prompt, n, rows_by_section, row_to_synth)
            user_msg = base_user_msg[: _llm_job.CREATE_FINAL_BODY_CAP]

            for _round in range(_llm_job.MAX_REFRESH_ROUNDS):
                with db.AgentRun("eddy", trigger="create-final") as agent_run:
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
                    # promoted_synth is empty: Featured-category rows are excluded
                    # from the LLM's view of rows_by_section (include_promoted=False
                    # in the run() snapshot), so Eddy can't reference them in any
                    # ``*_order`` or ``membership_blocks.after``.
                    promoted_synth: set[str] = set()
                    _validate_per_section_orders(data, synth_section, promoted_synth)
                    _validate_membership_blocks(
                        data["membership_blocks"], synth_section, promoted_synth,
                    )
                except _ProposalError as exc:
                    # Auto-fix path: if the only failure is "missing id(s)"
                    # in one of the *_order arrays, append the omitted ids
                    # in original order and re-validate. Preserves the
                    # editorial reorder, thesis, promotions, and membership
                    # blocks rather than dropping the whole proposal to
                    # passthrough. Other shape/permutation/membership
                    # errors fall through to the normal LLM retry.
                    auto_fixed = False
                    if data is not None and ": missing id(s):" in str(exc):
                        patched = _patch_missing_ids_into_orders(
                            data, synth_section, promoted_synth,
                        )
                        if patched:
                            try:
                                _validate_per_section_orders(
                                    data, synth_section, promoted_synth,
                                )
                                _validate_membership_blocks(
                                    data["membership_blocks"], synth_section,
                                    promoted_synth,
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
                                    f"`/eddy issue reset final` if the auto-fix is "
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
                            f"⚠️ Eddy's `create-final` proposal for WT{n} didn't validate: "
                            f"`{exc}` — retrying with a tighter hint.",
                            suppress_embeds=True,
                        )
                        user_msg = (base_user_msg + (
                            f"\n\n(That response was rejected: `{exc}`. Follow the JSON schema "
                            f"exactly — every parsed id must appear exactly once across its "
                            f"section's order + the promotions list.)"
                        ))[: _llm_job.CREATE_FINAL_BODY_CAP]
                        continue

                thesis = data["thesis"].strip()

                # Editorial card → #editorial; Jamie ✅/❌/🔄.
                # Render the side-by-side proposal page so Jamie can
                # see current vs proposed with connector lines in the
                # browser. Best-effort: a render hiccup just omits the
                # URL from the Discord prompt — the card text alone
                # has always been the canonical decision surface.
                proposal_url = await asyncio.to_thread(
                    render.render_and_upload_proposal,
                    issue_number=n, thesis=thesis,
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
                    n, thesis, rows_by_section, data,
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
                        f"Accept Eddy's editorial pass for WT{n}? "
                        f"(❌ writes final.md in the current row order, no thesis/promotions/markers.)"
                    ),
                )
                if approved == "refresh":
                    user_msg = base_user_msg + "\n\n(Jamie wants a different cut — try again.)"
                    continue

                if approved is True:
                    # Apply: mutate rows. No final.md write — the daily
                    # renderers below pull from the mutated DB state.
                    await asyncio.to_thread(_apply_proposal, n, data, synth_to_row)
                    # Closer still composed from the just-reordered body so
                    # the archive note is grounded in the actual content
                    # ordering. compose_closer.run wants a baseline body;
                    # build one in memory without writing.
                    baseline_body = _render_final(
                        n, atoms, data, synth_to_row, row_to_synth,
                    )
                    closer_result = await compose_closer.run(
                        ctx, baseline_body=baseline_body,
                    )
                    if closer_result.ok and closer_result.data and not closer_result.data.get("skipped"):
                        # Closer.md persisted by compose_closer; the daily
                        # renderers below will splice it into the body.
                        pass
                    s3.write_issue_file(n, "thesis.md", thesis + "\n")
                    # Render the three artifacts now so they reflect the
                    # new ordering immediately (the next update-draft tick
                    # would catch up, but Jamie's about to publish — give
                    # him a current preview right away).
                    try:
                        await asyncio.to_thread(
                            renderers.render_all_for_issue, n, window=window,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("create-final: post-apply render failed for #%d", n)
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
                        "thesis_written": approved is True,
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
        return _base.JobResult(False, f"⏳ `create-final` already running ({exc.holder_desc}).")
