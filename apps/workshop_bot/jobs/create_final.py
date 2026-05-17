"""``create-final`` — Eddy's editorial pass on the row-backed model.

Reads ``issue_items`` rows for the in-flight issue (Notable / Briefly /
Journal), presents them to Eddy with stable synthetic ids (``n1``,
``b2``, ``j3``) — the LLM-facing shape is unchanged — and asks for an
**ordering-only** JSON response:

```json
{
  "thesis": "…",
  "notable_order": ["n3", "n1", "n2", "n4"],
  "brief_order":   ["b2", "b1", "b4", "b3"],
  "journal_order": ["j2", "j1", "j3", "j4"],
  "promotions": [
    {"id": "j5", "heading": "The Quiet Colossus on Ada",
     "position": "after_notable", "rationale": "…"}
  ],
  "membership_blocks": [
    {"kind": "cta",    "after": "n1", "rationale": "…"},
    {"kind": "cta",    "before_haiku": true, "rationale": "…"},
    {"kind": "thanks", "after": "n2", "rationale": "…"}
  ]
}
```

**Apply step is row mutations, not byte-chunk reassembly.** Code:

1. Validates the proposal shape, promotions, membership_blocks, and
   per-section permutations against the parsed synthetic ids.
2. Maps each synthetic id back to its ``issue_items.id``.
3. Clears any prior promotions for the issue.
4. Calls :func:`issue_items.promote` for each new promotion.
5. Calls :func:`issue_items.reorder` per section with the
   non-promoted row ids in the LLM's order.
6. Renders ``final.md`` from rows using :mod:`tools.issue_assembly`:
   atoms (intro / currently / cover / outro / haiku) come verbatim
   from their files; parent sections render in current position
   order with cta/thanks markers spliced inline; promoted items
   appear as ``## Heading`` sections at their declared
   ``promoted_position`` — **inline in the file**, not gathered at
   the bottom. What Jamie sees in ``final.md`` IS where things will
   land in the published email.
7. Writes ``final.md`` and ``thesis.md``.

The LLM never touches bytes — identity comes from row id. The old
chunk parser + multiset lossless check are retired (the row model
guarantees losslessness by construction; an UPDATE on a position
column can't drop, duplicate, or mutate a row).

Eddy posts to ``#editorial``: thesis, per-section was/now reorder
map, promotions plan, membership-block plan. Jamie reacts ✅ / ❌ /
🔄. On ❌ the existing row order survives and the section bodies
render in their pre-create-final order (no thesis, no markers, no
promotions). On 🔄 we re-prompt up to :data:`_llm_job.MAX_REFRESH_ROUNDS`.

Refuses if ``final.md`` already exists — delete it explicitly to
re-run (or use ``/eddy issue reset final`` once that lands).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..tools import db, issue_assembly, issue_items, issue_items_render, render, s3
from ..tools.discord import discord_io, interaction
from ..tools.llm import anthropic_client
from . import _base, _cover, _currently, _llm_job, compose_cta

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
_MAX_PROMOTIONS = 2
_PROMOTION_POSITIONS = issue_items.PROMOTION_POSITIONS

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


def _build_user_message(
    base_prompt: str,
    issue_number: int,
    rows_by_section: dict[str, list[dict[str, Any]]],
    row_to_synth: dict[int, str],
) -> str:
    return (
        f"{base_prompt}\n\n"
        f"---\n\n"
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
    required = ("thesis", "notable_order", "brief_order", "journal_order", "membership_blocks")
    missing = [k for k in required if k not in data]
    if missing:
        raise _ProposalError(f"missing field(s) in JSON: {', '.join(missing)}")
    if not isinstance(data.get("thesis"), str) or not data["thesis"].strip():
        raise _ProposalError("`thesis` must be a non-empty string")
    for k in ("notable_order", "brief_order", "journal_order"):
        if not isinstance(data[k], list) or not all(isinstance(x, str) for x in data[k]):
            raise _ProposalError(f"`{k}` must be a list of id strings")
    if not isinstance(data["membership_blocks"], list):
        raise _ProposalError("`membership_blocks` must be a list")
    promos = data.get("promotions", [])
    if not isinstance(promos, list):
        raise _ProposalError("`promotions` must be a list (or omitted)")


def _validate_promotions(
    promotions: list,
    synth_section: dict[str, str],
) -> None:
    if len(promotions) > _MAX_PROMOTIONS:
        raise _ProposalError(
            f"too many promotions ({len(promotions)}); max {_MAX_PROMOTIONS}"
        )
    seen: set[str] = set()
    for i, p in enumerate(promotions):
        if not isinstance(p, dict):
            raise _ProposalError(f"promotions[{i}] is not an object")
        pid = p.get("id")
        if not isinstance(pid, str):
            raise _ProposalError(f"promotions[{i}].id must be a string")
        sect = synth_section.get(pid)
        if sect is None:
            raise _ProposalError(
                f"promotions[{i}].id={pid!r} doesn't match any parsed item"
            )
        if sect != "journal":
            raise _ProposalError(
                f"promotions[{i}].id={pid!r} is a {sect.capitalize()} item — "
                f"only Journal items can be promoted"
            )
        if pid in seen:
            raise _ProposalError(f"promotions[{i}].id={pid!r} appears more than once")
        seen.add(pid)
        heading = p.get("heading")
        if not isinstance(heading, str) or not heading.strip():
            raise _ProposalError(f"promotions[{i}].heading must be a non-empty string")
        position = p.get("position")
        if position not in _PROMOTION_POSITIONS:
            raise _ProposalError(
                f"promotions[{i}].position={position!r} must be one of "
                f"{', '.join(_PROMOTION_POSITIONS)}"
            )


def _validate_per_section_orders(
    data: dict,
    synth_section: dict[str, str],
    promoted_synth: set[str],
) -> None:
    """Each *_order must be a permutation of (synth ids in that section
    minus promoted ids)."""
    for section in ("notable", "brief", "journal"):
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


def _render_promotions_plan(
    promotions: list[dict[str, Any]],
    synth_to_row: dict[str, int],
    rows_by_id: dict[int, dict[str, Any]],
) -> str:
    if not promotions:
        return ""
    lines = [f"**Promotions:** {len(promotions)} item(s) elevated to standalone section(s)"]
    for p in promotions:
        pid = p["id"]
        heading = p["heading"].strip()
        position = p["position"].replace("_", " ")
        row = rows_by_id.get(synth_to_row[pid], {})
        source_label = (row.get("section") or "?").capitalize()
        source_title = _row_label(row)
        rationale = (p.get("rationale") or "").strip()
        line = (
            f"  · \"{heading}\" — was {source_label} `{pid}` "
            f"({source_title!r}) → standalone section {position}"
        )
        if rationale:
            line += f" — {rationale}"
        lines.append(line)
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
) -> str:
    promoted_synth = {p["id"] for p in (data.get("promotions") or [])}
    parts = [
        f"📝 **create-final** for WT{issue_number}",
        "",
        f"**Thesis:** {thesis.strip()}",
        "",
        _render_was_now(rows_by_section["notable"], data["notable_order"], synth_to_row, row_to_synth, kind_label="Notable", promoted_synth=promoted_synth),
        _render_was_now(rows_by_section["brief"], data["brief_order"], synth_to_row, row_to_synth, kind_label="Briefly"),
        _render_was_now(rows_by_section["journal"], data["journal_order"], synth_to_row, row_to_synth, kind_label="Journal", promoted_synth=promoted_synth),
    ]
    promos_card = _render_promotions_plan(data.get("promotions") or [], synth_to_row, rows_by_id)
    if promos_card:
        parts.extend(["", promos_card])
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
    """Mutate ``issue_items`` to match the LLM's plan: clear stale
    promotions, apply new promotions, reorder each section."""
    promotions = data.get("promotions") or []
    issue_items.clear_promotions(issue_number)
    promoted_row_ids: set[int] = set()
    for p in promotions:
        rid = synth_to_row[p["id"]]
        promoted_row_ids.add(rid)
        issue_items.promote(
            rid,
            promoted_position=p["position"],
            promoted_heading=p["heading"].strip(),
        )
    for section in ("notable", "brief", "journal"):
        order_synth = data[f"{section}_order"]
        ordered_row_ids = [synth_to_row[sid] for sid in order_synth]
        # Sanity: per-section orders should never include promoted rows
        # (the validator catches it), but skip defensively.
        ordered_row_ids = [rid for rid in ordered_row_ids if rid not in promoted_row_ids]
        if ordered_row_ids:
            issue_items.reorder(issue_number, section, ordered_row_ids)


# ---------- final.md render ----------

def _render_final(
    issue_number: int,
    atoms: dict[str, str],
    data: dict,
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
) -> str:
    """Read the post-mutation row state and assemble final.md."""
    notable_rows = issue_items.list_items(issue_number, section="notable", include_promoted=False)
    journal_rows = issue_items.list_items(issue_number, section="journal", include_promoted=False)
    brief_rows = issue_items.list_items(issue_number, section="brief", include_promoted=False)
    promoted_rows = issue_items.promoted_items(issue_number)

    # Membership-block markers → per-section trailing lists.
    markers_after_synth, before_haiku, _plan = _assign_markers(data["membership_blocks"])
    # Convert the synth-keyed markers map to row-id-keyed for the renderer.
    markers_after_rid: dict[int, list[str]] = {
        synth_to_row[sid]: ms for sid, ms in markers_after_synth.items()
    }
    trailing_target = _trailing_markers_target(notable_rows, journal_rows, brief_rows)

    section_bodies: dict[str, str] = {}
    section_bodies["notable"] = issue_items_render.render_notable_with_markers(
        notable_rows, issue_number, markers_after_rid,
        trailing_markers=before_haiku if trailing_target == "notable" else None,
    )
    section_bodies["journal"] = issue_items_render.render_journal_with_markers(
        journal_rows, markers_after_rid,
        trailing_markers=before_haiku if trailing_target == "journal" else None,
    )
    section_bodies["brief"] = issue_items_render.render_brief_with_markers(
        brief_rows, markers_after_rid,
        trailing_markers=before_haiku if trailing_target == "brief" else None,
    )

    # Promoted (featured) sections: render each row, group by position.
    features: list[tuple[str, str]] = []
    for row in promoted_rows:
        body = issue_items_render.render_featured_section(row)
        features.append((row["promoted_position"], body))

    return issue_assembly.assemble_final(
        atoms=atoms, section_bodies=section_bodies, features=features,
    )


def _render_final_passthrough(issue_number: int, atoms: dict[str, str]) -> str:
    """❌ path — render final.md from the existing row order (no thesis,
    no promotions, no markers). Same shape; just the current state."""
    notable_rows = issue_items.list_items(issue_number, section="notable", include_promoted=False)
    journal_rows = issue_items.list_items(issue_number, section="journal", include_promoted=False)
    brief_rows = issue_items.list_items(issue_number, section="brief", include_promoted=False)
    promoted_rows = issue_items.promoted_items(issue_number)
    section_bodies = {
        "notable": issue_items_render.render_notable(notable_rows, issue_number),
        "journal": issue_items_render.render_journal(journal_rows),
        "brief": issue_items_render.render_brief(brief_rows),
    }
    features = [(r["promoted_position"], issue_items_render.render_featured_section(r))
                for r in promoted_rows if r.get("promoted_position")]
    return issue_assembly.assemble_final(
        atoms=atoms, section_bodies=section_bodies, features=features,
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

    final_exists = (await asyncio.to_thread(s3.read_issue_file, n, "final.md")).get("found")
    if final_exists:
        return _base.JobResult(
            False, f"❌ WT{n} already has `final.md` — delete it to re-run `create-final`.",
        )

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

    asset = f"{n}/final.md"
    html_url: Optional[str] = None
    try:
        with _base.job_lock([asset], NAME):
            atoms = _build_atoms(n)
            base_prompt = anthropic_client.load_prompt("eddy-create-final")
            base_user_msg = _build_user_message(base_prompt, n, rows_by_section, row_to_synth)
            user_msg = base_user_msg[: _llm_job.CREATE_FINAL_BODY_CAP]

            for _round in range(_llm_job.MAX_REFRESH_ROUNDS):
                with db.AgentRun("eddy", trigger="create-final") as agent_run:
                    reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                    agent_run.record_meta(_meta)
                    agent_run.records_written = 1
                data = _llm_job.parse_json_payload(reply or "")
                try:
                    if data is None:
                        raise _ProposalError("response wasn't a parseable JSON object")
                    _validate_proposal_shape(data)
                    promotions = data.get("promotions") or []
                    _validate_promotions(promotions, synth_section)
                    promoted_synth = {p["id"] for p in promotions}
                    _validate_per_section_orders(data, synth_section, promoted_synth)
                    _validate_membership_blocks(
                        data["membership_blocks"], synth_section, promoted_synth,
                    )
                except _ProposalError as exc:
                    await channel.send(
                        f"⚠️ Eddy's `create-final` proposal for WT{n} didn't validate: "
                        f"`{exc}` — retrying with a tighter hint.",
                        suppress_embeds=True,
                    )
                    # If the validator flagged a missing-id error, list the
                    # omitted ids explicitly so Eddy patches them in rather
                    # than recomputing from scratch — the most common
                    # failure (especially on Opus) is dropping the tail of
                    # a long Journal list, and a generic "follow the schema"
                    # hint isn't enough to recover.
                    extra_hint = ""
                    msg = str(exc)
                    if ": missing id(s):" in msg:
                        omitted = msg.split(": missing id(s):", 1)[1].strip()
                        section = msg.split("_order", 1)[0].strip()
                        extra_hint = (
                            f"\n\nSpecifically: append {omitted} to "
                            f"`{section}_order` (anywhere in the array — at "
                            f"the end is fine if you have no opinion). Do "
                            f"not change the rest of your proposal. Every "
                            f"parsed id must appear exactly once."
                        )
                    user_msg = (base_user_msg + (
                        f"\n\n(That response was rejected: `{exc}`. Follow the JSON schema "
                        f"exactly — every parsed id must appear exactly once across its "
                        f"section's order + the promotions list.{extra_hint})"
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
                card = _render_editorial_card(
                    n, thesis, rows_by_section, data,
                    synth_to_row, row_to_synth, rows_by_id,
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
                    # Apply: mutate rows then render.
                    await asyncio.to_thread(_apply_proposal, n, data, synth_to_row)
                    final_body = _render_final(
                        n, atoms, data, synth_to_row, row_to_synth,
                    )
                    s3.write_issue_file(n, "final.md", final_body)
                    s3.write_issue_file(n, "thesis.md", thesis + "\n")
                else:
                    # ❌ — render from current row order, no edits.
                    final_body = _render_final_passthrough(n, atoms)
                    s3.write_issue_file(n, "final.md", final_body)

                html_url = await asyncio.to_thread(
                    render.render_and_upload_html, n, "final", final_body,
                    title=f"WT{n} — final",
                    subtitle=f"FINAL (post-Eddy ordering) · WT{n} · awaiting publish.md",
                    strip_block_markers=True,
                )
                view = _md_html_links(n, "final", html_url)
                cta_slots_n = len(data.get("membership_blocks") or []) if approved is True else 0
                next_steps = _NEXT_STEPS_WITH_CTA_AUTOFIRE if cta_slots_n else _NEXT_STEPS
                await channel.send(
                    f"✅ `final.md` written for WT{n}.{view}\n\n{next_steps}",
                    suppress_embeds=True,
                )
                # Auto-fire compose-cta when Eddy declared slots and
                # Jamie approved. Background task so create-final returns
                # immediately (compose-cta is interactive — it'll prompt
                # Jamie in #supporters per slot, independently of
                # whatever else is in flight in #editorial).
                if cta_slots_n:
                    _schedule_compose_cta(ctx, issue_number=n, slots_declared=cta_slots_n)
                return _base.JobResult(
                    True,
                    f"`final.md` written for WT{n}"
                    + (f" · 📄 {html_url}" if html_url else "")
                    + f". {next_steps}",
                    data={
                        "issue_number": n,
                        "preview_url": html_url,
                        "thesis_written": approved is True,
                        "cta_autofired": bool(cta_slots_n),
                        "cta_slots_declared": cta_slots_n,
                    },
                )

            # Refresh rounds exhausted — write current order as final.
            await channel.send(
                f"⚠️ `create-final` for WT{n} couldn't get a valid proposal after "
                f"{_llm_job.MAX_REFRESH_ROUNDS} attempts. Writing the current row order as `final.md`; "
                "re-run create-final if you want another pass.",
                suppress_embeds=True,
            )
            final_body = _render_final_passthrough(n, atoms)
            s3.write_issue_file(n, "final.md", final_body)
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "final", final_body,
                title=f"WT{n} — final",
                subtitle=f"FINAL (rows as-is) · WT{n} · awaiting publish.md",
                strip_block_markers=True,
            )
            return _base.JobResult(
                True,
                f"`final.md` written for WT{n} (rows as-is — LLM exhausted retries). {_NEXT_STEPS}",
                data={"issue_number": n, "preview_url": html_url, "thesis_written": False},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `create-final` already running ({exc.holder_desc}).")
