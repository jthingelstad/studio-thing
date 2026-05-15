"""``create-final`` — Eddy's editorial pass: reorder + thesis + membership-block placements.

Reads ``draft.md``, parses each section (Notable / Briefly / Journal) into
**byte-exact chunks** with stable ids, hands those to Eddy along with the
draft's full text per chunk, and asks for an **ordering-only** JSON response:

```json
{
  "thesis": "…",
  "notable_order": ["n3", "n1", "n2", "n4"],
  "brief_order":   ["b2", "b1", "b4", "b3"],
  "journal_order": ["j2", "j1", "j3", "j4"],
  "membership_blocks": [
    {"kind": "cta",    "after": "n1", "rationale": "..."},
    {"kind": "cta",    "before_haiku": true, "rationale": "..."},
    {"kind": "thanks", "after": "n2", "rationale": "..."}
  ]
}
```

Code then reassembles each section from the original ``raw_bytes`` slices in
the LLM's order, inserts ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers
inline at the declared positions, and writes ``final.md`` (block structure
preserved) plus ``thesis.md``. The LLM cannot retitle, paraphrase, mutate
a URL, or drop an image, because it never touches the bytes — only the
order specification.

A belt-and-suspenders ``validate_lossless`` pass runs after reassembly: it
re-parses the reassembled section and asserts the chunk multiset matches
the draft's. Any mismatch refuses to write and surfaces 🔄 in
``#editorial``.

Eddy posts to ``#editorial``: the thesis, per-section ``was → now`` reorder
map (or "no change"), and the membership-block plan with rationale per slot.
Jamie reacts ✅ / ❌ / 🔄. On ❌, ``final.md`` is written verbatim from
``draft.md`` (today's fallback) and no ``thesis.md`` is written —
downstream jobs (compose-meta, compose-haiku, compose-cta) handle a missing
thesis gracefully.

Refuses if ``final.md`` already exists — delete it explicitly to re-run.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from ..tools import db, render, s3
from ..tools.content import chunks, draft as draft_mod, reorder
from ..tools.discord import discord_io, interaction
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.create_final")

NAME = "create-final"

_NEXT_STEPS = (
    "Next, in any order: `/eddy issue haiku`, `/eddy issue subject`, "
    "`/patty cta` — then `/eddy issue publish` (it'll list "
    "anything still missing if you run it early)."
)

# Hard caps on Eddy's membership-block declaration (enforced after parse).
_MAX_CTA = 2
_MAX_THANKS = 1

# Hard cap on promotions. 0 is fine; 1 is the common Featured-slot case;
# 2 is rare. ≥3 is refused — too many featured sections dilute the issue.
_MAX_PROMOTIONS = 2
_PROMOTION_POSITIONS = ("after_notable", "after_journal", "after_brief")


# ---------- LLM input formatting ----------

def _format_notable_chunks(items: list[chunks.NotableItem]) -> str:
    if not items:
        return "_(no Notable items)_"
    parts: list[str] = []
    for it in items:
        parts.append(f"### `{it.id}` — {it.title}\n{it.url}\n\n{it.raw_bytes}")
    return "\n\n---\n\n".join(parts)


def _format_brief_chunks(items: list[chunks.BriefItem]) -> str:
    if not items:
        return "_(no Briefly items)_"
    parts: list[str] = []
    for it in items:
        parts.append(f"### `{it.id}` — {it.title}\n{it.url}\n\n{it.raw_bytes}")
    return "\n\n---\n\n".join(parts)


def _format_journal_chunks(items: list[chunks.JournalEntry]) -> str:
    if not items:
        return "_(no Journal entries)_"
    parts: list[str] = []
    for it in items:
        label = it.title or it.label
        parts.append(f"### `{it.id}` — {label}\n{it.url}\n\n{it.raw_bytes}")
    return "\n\n---\n\n".join(parts)


def _build_user_message(
    base_prompt: str,
    issue_number: int,
    notable_items: list[chunks.NotableItem],
    brief_items: list[chunks.BriefItem],
    journal_items: list[chunks.JournalEntry],
) -> str:
    """Build the full user message: base prompt + the three sections' chunks.

    Eddy needs the full commentary per chunk to make sound ordering
    decisions, but each chunk is shown with its id so the JSON response
    can refer to them precisely."""
    return (
        f"{base_prompt}\n\n"
        f"---\n\n"
        f"## Parsed chunks for WT{issue_number}\n\n"
        f"### Notable items\n\n{_format_notable_chunks(notable_items)}\n\n"
        f"---\n\n"
        f"### Briefly items\n\n{_format_brief_chunks(brief_items)}\n\n"
        f"---\n\n"
        f"### Journal entries\n\n{_format_journal_chunks(journal_items)}\n"
    )


# ---------- JSON validation ----------

class _ProposalError(Exception):
    """Raised when the LLM's JSON proposal can't be applied. The message
    is operator-readable and surfaced to ``#editorial``."""


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
    # `promotions` is optional in the JSON; default to [] when absent so
    # back-compat with a leaner LLM response shape (no promotions
    # declared) doesn't break.
    promos = data.get("promotions", [])
    if not isinstance(promos, list):
        raise _ProposalError("`promotions` must be a list (or omitted)")


def _validate_promotions(
    promotions: list,
    notable_id_set: set[str],
    brief_id_set: set[str],
    journal_id_set: set[str],
) -> None:
    """Validate the `promotions` JSON entries against the parsed item ids.

    Constraints (matching the prompt + the plan):
    - At most ``_MAX_PROMOTIONS`` entries.
    - Each `id` must be a Journal (``j*``) item. Notable (``n*``) and
      Brief (``b*``) items cannot be promoted in the current design —
      only Jamie's own Journal posts earn standalone featured treatment.
    - Each `id` must appear at most once across the promotions list.
    - `position` must be one of the named slots.
    - `heading` must be a non-empty string.
    """
    if len(promotions) > _MAX_PROMOTIONS:
        raise _ProposalError(
            f"too many promotions ({len(promotions)}); max {_MAX_PROMOTIONS}"
        )
    seen_ids: set[str] = set()
    for i, p in enumerate(promotions):
        if not isinstance(p, dict):
            raise _ProposalError(f"promotions[{i}] is not an object")
        pid = p.get("id")
        if not isinstance(pid, str):
            raise _ProposalError(f"promotions[{i}].id must be a string")
        if pid in brief_id_set:
            raise _ProposalError(
                f"promotions[{i}].id={pid!r} is a Brief item — Brief items cannot be promoted"
            )
        if pid in notable_id_set:
            raise _ProposalError(
                f"promotions[{i}].id={pid!r} is a Notable item — only Journal items can be promoted"
            )
        if pid not in journal_id_set:
            raise _ProposalError(
                f"promotions[{i}].id={pid!r} doesn't match any parsed Journal item"
            )
        if pid in seen_ids:
            raise _ProposalError(f"promotions[{i}].id={pid!r} appears in more than one promotion")
        seen_ids.add(pid)
        heading = p.get("heading")
        if not isinstance(heading, str) or not heading.strip():
            raise _ProposalError(f"promotions[{i}].heading must be a non-empty string")
        position = p.get("position")
        if position not in _PROMOTION_POSITIONS:
            raise _ProposalError(
                f"promotions[{i}].position={position!r} must be one of "
                f"{', '.join(_PROMOTION_POSITIONS)}"
            )


def _validate_membership_blocks(
    blocks: list, valid_ids: set[str], *, promoted_ids: set[str] = frozenset(),
) -> None:
    cta_count = 0
    thanks_count = 0
    for i, b in enumerate(blocks):
        if not isinstance(b, dict):
            raise _ProposalError(f"membership_blocks[{i}] is not an object")
        kind = b.get("kind")
        if kind not in ("cta", "thanks"):
            raise _ProposalError(f"membership_blocks[{i}].kind must be 'cta' or 'thanks' (got {kind!r})")
        has_after = "after" in b
        has_before = bool(b.get("before_haiku"))
        if has_after == has_before:  # both or neither
            raise _ProposalError(
                f"membership_blocks[{i}] must have exactly one of `after` (an item id) or `before_haiku: true`"
            )
        if has_after:
            after_id = b["after"]
            if not isinstance(after_id, str) or after_id not in valid_ids:
                raise _ProposalError(
                    f"membership_blocks[{i}].after={after_id!r} doesn't match any parsed item id"
                )
            if after_id in promoted_ids:
                raise _ProposalError(
                    f"membership_blocks[{i}].after={after_id!r} is a promoted item; "
                    f"membership-block `after` references cannot point at a promoted id"
                )
        if kind == "cta":
            cta_count += 1
        else:
            thanks_count += 1
    if cta_count > _MAX_CTA:
        raise _ProposalError(f"too many cta blocks ({cta_count}); max {_MAX_CTA}")
    if thanks_count > _MAX_THANKS:
        raise _ProposalError(f"too many thanks blocks ({thanks_count}); max {_MAX_THANKS}")


# ---------- marker insertion ----------

def _markers_after(blocks: list, kind_counts: dict[str, int]) -> dict[str, list[str]]:
    """Walk the membership_blocks in declaration order and assign each one a
    1-indexed marker string (``<!-- cta:1 -->``, ``<!-- thanks:1 -->``, etc.).
    Returns a dict mapping ``after_id`` → list of markers to insert after
    that item, plus a special ``"_before_haiku"`` key.

    ``kind_counts`` is mutated to track the running 1-indexed count per kind
    so the caller can build a render map for the editorial surface.
    """
    out: dict[str, list[str]] = {"_before_haiku": []}
    for b in blocks:
        kind = b["kind"]
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        marker = f"<!-- {kind}:{kind_counts[kind]} -->"
        if b.get("before_haiku"):
            out["_before_haiku"].append(marker)
        else:
            out.setdefault(b["after"], []).append(marker)
    return out


def _assemble_with_markers(
    items: list,
    order: list[str],
    markers_by_after: dict[str, list[str]],
    separator: str,
    preamble: str = "",
) -> str:
    """Glue items back together with the given separator, inserting any
    declared markers after each item id. Used for Notable / Brief / Journal
    section bodies."""
    by_id = {it.id: it for it in items}
    pieces: list[str] = []
    for oid in order:
        pieces.append(by_id[oid].raw_bytes)
        for marker in markers_by_after.get(oid, ()):
            pieces.append(marker)
    body = separator.join(pieces)
    return f"{preamble}\n\n{body}" if preamble else body


def _append_before_haiku_markers(
    notable: str, journal: str, brief: str, markers: list[str],
) -> tuple[str, str, str]:
    """Append ``before_haiku`` markers to the last non-empty section's body.

    Published shape goes intro → Currently → cover → Notable → Journal →
    Briefly → haiku close; "before haiku" naturally falls inside Briefly
    when it's present, then Journal, then Notable as the issue thins out.
    If all three sections are empty (edge case), the markers land in Brief
    as a degenerate placement.
    """
    if not markers:
        return notable, journal, brief
    suffix = "\n\n" + "\n\n".join(markers)
    if brief.strip():
        return notable, journal, brief + suffix
    if journal.strip():
        return notable, journal + suffix, brief
    if notable.strip():
        return notable + suffix, journal, brief
    return notable, journal, suffix.lstrip()


# ---------- feature blocks (promotions) ----------

def _feature_block_content(promotion: dict, raw_bytes: str) -> str:
    """Build the body for a ``<!-- block:featureN -->`` block.

    YAML frontmatter (``position``, ``heading``, ``source_id``) followed by
    the promoted item's ``raw_bytes`` verbatim. ``build-publish`` reads
    the frontmatter and renders ``## {heading}\\n\\n{body}`` into
    ``publish.md`` at the named position.
    """
    return (
        f"---\n"
        f"position: {promotion['position']}\n"
        f"heading: {promotion['heading'].strip()}\n"
        f"source_id: {promotion['id']}\n"
        f"---\n\n"
        f"{raw_bytes}"
    )


def _write_feature_block(text: str, name: str, content: str) -> str:
    """Like :func:`_base.replace_block`, but strips only trailing newlines
    from ``content`` (not all trailing whitespace) so a promoted item's
    trailing space in its commentary round-trips byte-identical."""
    open_tag = f"<!-- block:{name} -->"
    close_tag = f"<!-- /block:{name} -->"
    i = text.find(open_tag)
    if i < 0:
        return text
    j = text.find(close_tag, i + len(open_tag))
    if j < 0:
        return text
    body = (content or "").rstrip("\n")
    inner = f"\n{body}\n" if body else "\n"
    return text[: i + len(open_tag)] + inner + text[j:]


def _filter_items_by_promotions(
    items: list, promoted_ids: set[str],
) -> list:
    """Return ``items`` minus any whose id was promoted. Used both for
    reorder validation and for the lossless-multiset comparison."""
    return [it for it in items if it.id not in promoted_ids]


# ---------- editorial-surface rendering ----------

def _render_was_now(
    items: list, order: list[str], *, kind_label: str,
    promoted_ids: set[str] = frozenset(),
) -> str:
    """Build the ``was → now`` reorder map for one section.

    ``promoted_ids`` lets the map flag "(N promoted out)" when one or more
    items in the parsed list were promoted to a feature section (so the
    reorder is over a smaller set than the original)."""
    if not items:
        return f"**{kind_label}** — _(empty)_"
    items_in_order = [it for it in items if it.id not in promoted_ids]
    by_id = {it.id: it for it in items}
    original_ids = [it.id for it in items_in_order]
    promoted_note = ""
    promoted_in_section = [it.id for it in items if it.id in promoted_ids]
    if promoted_in_section:
        n = len(promoted_in_section)
        promoted_note = f" ({n} promoted out)"
    if original_ids == list(order):
        if not original_ids:
            return f"**{kind_label}** — _(empty after promotion)_"
        return f"**{kind_label}** — no change{promoted_note}"
    titles_for = (
        lambda ids: " · ".join(
            f"{i+1}. {by_id[oid].title if hasattr(by_id[oid], 'title') and by_id[oid].title else by_id[oid].label}"
            for i, oid in enumerate(ids)
        )
    )
    return (
        f"**{kind_label}** — reordered{promoted_note}\n"
        f"  was: {titles_for(original_ids)}\n"
        f"  now: {titles_for(order)}"
    )


def _render_promotions_plan(
    promotions: list,
    notable_items: list,
    journal_items: list,
) -> str:
    """Build the promotions card for ``#editorial``."""
    if not promotions:
        return ""
    title_for_id = {it.id: it.title for it in notable_items}
    for it in journal_items:
        title_for_id[it.id] = it.title or it.label
    section_for_id = {it.id: "Notable" for it in notable_items}
    for it in journal_items:
        section_for_id[it.id] = "Journal"
    lines = [f"**Promotions:** {len(promotions)} item(s) elevated to standalone section(s)"]
    for p in promotions:
        pid = p["id"]
        heading = p["heading"].strip()
        position = p["position"]
        source_label = section_for_id.get(pid, "?")
        source_title = title_for_id.get(pid, pid)
        rationale = (p.get("rationale") or "").strip()
        position_label = position.replace("_", " ")
        line = (
            f"  · \"{heading}\" — was {source_label} `{pid}` "
            f"({source_title!r}) → standalone section {position_label}"
        )
        if rationale:
            line += f" — {rationale}"
        lines.append(line)
    return "\n".join(lines)


def _render_membership_plan(
    blocks: list,
    notable_items: list[chunks.NotableItem],
    brief_items: list[chunks.BriefItem],
    journal_items: list[chunks.JournalEntry],
) -> str:
    """Build the membership-block plan card for ``#editorial``."""
    if not blocks:
        return "**Membership blocks:** _(none — this issue runs clean)_"
    title_for_id = {}
    for it in notable_items:
        title_for_id[it.id] = it.title
    for it in brief_items:
        title_for_id[it.id] = it.title
    for it in journal_items:
        title_for_id[it.id] = it.title or it.label
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
            title = title_for_id.get(aid, aid)
            position = f"after \"{title}\" (`{aid}`)"
        rationale = (b.get("rationale") or "").strip()
        line = f"  · {marker} {position}"
        if rationale:
            line += f" — {rationale}"
        lines.append(line)
    return "\n".join(lines)


def _render_editorial_card(
    issue_number: int,
    thesis: str,
    notable_items: list[chunks.NotableItem],
    notable_order: list[str],
    brief_items: list[chunks.BriefItem],
    brief_order: list[str],
    journal_items: list[chunks.JournalEntry],
    journal_order: list[str],
    promotions: list,
    membership_blocks: list,
) -> str:
    """Compose the full ``#editorial`` card surfaced before ✅/❌/🔄."""
    promoted_ids = {p["id"] for p in promotions}
    parts = [
        f"📝 **create-final** for WT{issue_number}",
        "",
        f"**Thesis:** {thesis.strip()}",
        "",
        _render_was_now(notable_items, notable_order, kind_label="Notable", promoted_ids=promoted_ids),
        _render_was_now(brief_items, brief_order, kind_label="Briefly"),
        _render_was_now(journal_items, journal_order, kind_label="Journal", promoted_ids=promoted_ids),
    ]
    promotions_card = _render_promotions_plan(promotions, notable_items, journal_items)
    if promotions_card:
        parts.extend(["", promotions_card])
    parts.extend(["", _render_membership_plan(membership_blocks, notable_items, brief_items, journal_items)])
    return "\n".join(parts)


# ---------- I/O ----------

def _draft_text(n: int) -> str:
    res = s3.read_issue_file(n, "draft.md")
    return res["text"] if (res.get("found") and isinstance(res.get("text"), str)) else ""


_ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"


def _md_html_links(issue_number: int, name: str, html_url: Optional[str]) -> str:
    """Build the trailing ``📄 [HTML] · 📝 [markdown]`` link pair for the
    success message. The ``.md`` URL is constructed from the public-bucket
    pattern (no separate render step needs to return it). When
    ``html_url`` is missing (render failed), only the ``.md`` link is
    shown so the operator can still review."""
    md_url = f"{_ASSETS_BASE}/{issue_number}/{name}.md"
    if html_url:
        return f"\n\n📄 [HTML]({html_url}) · 📝 [markdown]({md_url})"
    return f"\n\n📝 [markdown]({md_url})"


def _write_final_draft_as_is(n: int, draft: str) -> None:
    """❌ fallback — write the draft body verbatim to ``final.md`` (today's
    behaviour). No thesis is written; downstream jobs degrade gracefully."""
    body = draft if draft.endswith("\n") else draft + "\n"
    s3.write_issue_file(n, "final.md", body)


# ---------- main ----------

async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])

    final_exists = (await asyncio.to_thread(s3.read_issue_file, n, "final.md")).get("found")
    if final_exists:
        return _base.JobResult(False, f"❌ WT{n} already has `final.md` — delete it to re-run `create-final`.")
    draft = await asyncio.to_thread(_draft_text, n)
    if not draft.strip():
        return _base.JobResult(False, f"❌ no `draft.md` for WT{n} — run `/eddy issue update` first.")
    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(False, f"(create-final skipped — {reason})")

    # Parse draft blocks then per-section chunks.
    blocks = draft_mod.parse_blocks(draft)
    notable_preamble, notable_items = chunks.parse_notable(blocks.get("notable") or "")
    brief_items = chunks.parse_brief(blocks.get("brief") or "")
    journal_items = chunks.parse_journal(blocks.get("journal") or "")

    asset = f"{n}/final.md"
    html_url: Optional[str] = None
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-create-final")
            base_user_msg = _build_user_message(
                base_prompt, n, notable_items, brief_items, journal_items,
            )
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
                    notable_id_set = {it.id for it in notable_items}
                    brief_id_set = {it.id for it in brief_items}
                    journal_id_set = {it.id for it in journal_items}
                    promotions = data.get("promotions") or []
                    _validate_promotions(
                        promotions, notable_id_set, brief_id_set, journal_id_set,
                    )
                    promoted_ids = {p["id"] for p in promotions}
                    # Per-section orders must be permutations of (parsed - promoted).
                    notable_for_order = _filter_items_by_promotions(notable_items, promoted_ids)
                    journal_for_order = _filter_items_by_promotions(journal_items, promoted_ids)
                    reorder.validate_order(notable_for_order, data["notable_order"], section="notable")
                    reorder.validate_order(brief_items, data["brief_order"], section="brief")
                    reorder.validate_order(journal_for_order, data["journal_order"], section="journal")
                    valid_ids = notable_id_set | brief_id_set | journal_id_set
                    _validate_membership_blocks(
                        data["membership_blocks"], valid_ids, promoted_ids=promoted_ids,
                    )
                except (_ProposalError, reorder.StrictValidationError) as exc:
                    await channel.send(
                        f"⚠️ Eddy's `create-final` proposal for WT{n} didn't validate: "
                        f"`{exc}` — retrying with a tighter hint.",
                        suppress_embeds=True,
                    )
                    user_msg = base_user_msg + (
                        f"\n\n(That response was rejected: `{exc}`. Follow the JSON schema "
                        f"exactly — every parsed id must appear exactly once in its section's order.)"
                    )[: _llm_job.CREATE_FINAL_BODY_CAP]
                    continue

                thesis = data["thesis"].strip()
                membership_blocks = data["membership_blocks"]

                # Walk membership_blocks → marker assignments.
                kind_counts: dict[str, int] = {}
                markers_map = _markers_after(membership_blocks, kind_counts)

                # Reassemble each section with inline markers at the after-id
                # positions. Use the filtered item lists so a promoted item
                # doesn't appear in its parent section.
                notable_text = _assemble_with_markers(
                    notable_for_order, data["notable_order"],
                    markers_map, separator="\n\n\n", preamble=notable_preamble,
                )
                brief_text = _assemble_with_markers(
                    brief_items, data["brief_order"],
                    markers_map, separator="\n\n",
                )
                journal_text = _assemble_with_markers(
                    journal_for_order, data["journal_order"],
                    markers_map, separator="\n\n\n",
                )

                # Append before_haiku markers to the last non-empty section.
                notable_text, journal_text, brief_text = _append_before_haiku_markers(
                    notable_text, journal_text, brief_text, markers_map.get("_before_haiku", []),
                )

                # Belt-and-suspenders lossless check. The reassembled section
                # should contain the same chunk multiset as the draft's
                # section **minus** the promoted items. Strip the markers
                # first so the chunk parser sees just the item bytes.
                draft_notable_filtered = chunks.reassemble_notable(
                    notable_preamble, notable_for_order,
                )
                draft_brief_filtered = chunks.reassemble_brief(brief_items)
                draft_journal_filtered = chunks.reassemble_journal(journal_for_order)
                try:
                    reorder.validate_lossless(
                        draft_notable_filtered, _strip_markers(notable_text), section="notable",
                    )
                    reorder.validate_lossless(
                        draft_brief_filtered, _strip_markers(brief_text), section="brief",
                    )
                    reorder.validate_lossless(
                        draft_journal_filtered, _strip_markers(journal_text), section="journal",
                    )
                except reorder.StrictValidationError as exc:
                    logger.error("create-final: lossless check failed: %s", exc)
                    await channel.send(
                        f"⚠️ Internal reassembly check failed for WT{n}: `{exc}` — retrying.",
                        suppress_embeds=True,
                    )
                    user_msg = base_user_msg
                    continue

                # Surface to #editorial and await approval.
                card = _render_editorial_card(
                    n, thesis,
                    notable_items, data["notable_order"],
                    brief_items, data["brief_order"],
                    journal_items, data["journal_order"],
                    promotions,
                    membership_blocks,
                )
                # The editorial card can exceed Discord's 2000-char limit
                # (thesis + 3 was/now maps + membership plan + promotions).
                # Chunk via the standard splitter so a long-form review
                # surface doesn't 400 the whole job.
                for _part in discord_io.split_for_discord(card):
                    await channel.send(_part, suppress_embeds=True)
                approved = await interaction.await_approval(
                    bot, channel,
                    prompt=f"Accept Eddy's editorial pass for WT{n}? (❌ keeps the draft order, no thesis/markers/feature blocks.)",
                )
                if approved == "refresh":
                    user_msg = base_user_msg + "\n\n(Jamie wants a different cut — try again.)"
                    continue

                if approved is True:
                    # Build final.md: draft text with the three section blocks
                    # replaced by the reassembled (markered) content, plus
                    # feature1/feature2 blocks filled for any promotions.
                    final_body = draft
                    final_body = _base.replace_block(final_body, "notable", notable_text)
                    final_body = _base.replace_block(final_body, "journal", journal_text)
                    final_body = _base.replace_block(final_body, "brief", brief_text)
                    # Write each promotion into a feature block. raw_bytes are
                    # captured from the original parsed item; _write_feature_block
                    # preserves trailing whitespace so the promoted bytes
                    # round-trip exactly.
                    promotion_items_by_id = {it.id: it for it in notable_items + journal_items}
                    for idx, promotion in enumerate(promotions, start=1):
                        block_name = f"feature{idx}"
                        item = promotion_items_by_id[promotion["id"]]
                        block_content = _feature_block_content(promotion, item.raw_bytes)
                        final_body = _write_feature_block(final_body, block_name, block_content)
                    if not final_body.endswith("\n"):
                        final_body += "\n"
                    s3.write_issue_file(n, "final.md", final_body)
                    s3.write_issue_file(n, "thesis.md", thesis + "\n")
                else:
                    # ❌: write draft as final, no thesis, no feature blocks.
                    _write_final_draft_as_is(n, draft)
                    final_body = draft

                html_url = await asyncio.to_thread(
                    render.render_and_upload_html, n, "final", final_body,
                    title=f"WT{n} — final",
                    subtitle=f"FINAL (post-Eddy ordering) · WT{n} · awaiting publish.md",
                    strip_block_markers=True,
                )
                view = _md_html_links(n, "final", html_url)
                await channel.send(
                    f"✅ `final.md` written for WT{n}.{view}\n\n{_NEXT_STEPS}",
                    suppress_embeds=True,
                )
                return _base.JobResult(
                    True,
                    f"`final.md` written for WT{n}"
                    + (f" · 📄 {html_url}" if html_url else "")
                    + f". {_NEXT_STEPS}",
                    data={
                        "issue_number": n,
                        "preview_url": html_url,
                        "thesis_written": approved is True,
                    },
                )

            # Exhausted refresh rounds without a valid proposal — write draft as final.
            await channel.send(
                f"⚠️ `create-final` for WT{n} couldn't get a valid proposal after "
                f"{_llm_job.MAX_REFRESH_ROUNDS} attempts. Writing the draft order as `final.md`; "
                "re-run create-final if you want another pass.",
                suppress_embeds=True,
            )
            _write_final_draft_as_is(n, draft)
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "final", draft,
                title=f"WT{n} — final",
                subtitle=f"FINAL (draft as-is) · WT{n} · awaiting publish.md",
                strip_block_markers=True,
            )
            return _base.JobResult(
                True,
                f"`final.md` written for WT{n} (draft as-is — LLM exhausted retries). {_NEXT_STEPS}",
                data={"issue_number": n, "preview_url": html_url, "thesis_written": False},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `create-final` already running ({exc.holder_desc}).")


# ---------- marker stripping (for validate_lossless) ----------

import re  # noqa: E402  (kept low; used only by the helper below)

_MARKER_RE = re.compile(r"<!--\s*(cta|thanks):\d+\s*-->")


def _strip_markers(section_text: str) -> str:
    """Strip ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers from a section
    body so the lossless multiset check sees just the item bytes. Also
    collapses any double-separators left behind."""
    stripped = _MARKER_RE.sub("", section_text)
    # Collapse runs of 4+ newlines that the marker may have left.
    stripped = re.sub(r"\n{4,}", "\n\n\n", stripped)
    return stripped.strip()
