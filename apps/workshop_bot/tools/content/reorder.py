"""Strict ordering + lossless reassembly for ``draft.md`` section chunks.

The pair to :mod:`apps.workshop_bot.tools.content.chunks`. Given parsed
items and an LLM-supplied ordering, this module:

1. Validates the order is a strict permutation of the parsed item ids —
   no missing ids, no extra ids, no duplicates. Validation failures
   raise :class:`StrictValidationError` with a precise reason, so the
   ``create-final`` job can surface it back to Jamie in ``#editorial``
   and offer 🔄.
2. Reassembles the section using the item's ``raw_bytes`` (the original
   slice of ``draft.md``) — never anything the LLM produced. The bytes
   that land in ``final.md`` are byte-identical to the bytes in
   ``draft.md``, modulo order. The LLM cannot silently retitle,
   re-phrase, mutate a URL, or drop an image, because it never touches
   the bytes.
3. Optionally runs a belt-and-suspenders multiset check
   (:func:`validate_lossless`) that compares the items parsed from the
   reassembled output against the items parsed from the draft. If the
   two multisets differ, something went wrong in our own code (the
   reassembly path; not the LLM) and the job refuses to write.

The reorder module knows about three section names: ``"notable"``,
``"brief"``, ``"journal"``. Each has its own item type and its own
separator, but the validate-and-reassemble shape is identical across
the three.
"""

from __future__ import annotations

from typing import Iterable, Union

from .chunks import (
    BriefItem,
    JournalEntry,
    NotableItem,
    parse_brief,
    parse_journal,
    parse_notable,
    reassemble_brief,
    reassemble_journal,
    reassemble_notable,
)

Chunk = Union[NotableItem, BriefItem, JournalEntry]

# Sections this module knows how to validate + reassemble.
SECTIONS = ("notable", "brief", "journal")


class StrictValidationError(ValueError):
    """Raised when the LLM's ordering can't be applied losslessly.

    The message is operator-readable (surfaced to ``#editorial``);
    callers should pass it through unchanged.
    """


# ---------- validation ----------

def validate_order(items: Iterable[Chunk], order: list[str], *, section: str) -> None:
    """Check that ``order`` is a strict permutation of ``[i.id for i in items]``.

    Raises :class:`StrictValidationError` with a precise reason on the
    first problem found. The reasons are designed to be readable in a
    Discord refuse-card.
    """
    have = [it.id for it in items]
    have_set = set(have)
    order_set: set[str] = set()
    duplicates: list[str] = []
    for oid in order:
        if oid in order_set:
            duplicates.append(oid)
        order_set.add(oid)
    if duplicates:
        raise StrictValidationError(
            f"{section}: duplicate id(s) in order: {', '.join(sorted(set(duplicates)))}"
        )
    extra = sorted(order_set - have_set)
    if extra:
        raise StrictValidationError(
            f"{section}: order names id(s) that don't exist in the draft: "
            f"{', '.join(extra)}"
        )
    missing = sorted(have_set - order_set)
    if missing:
        raise StrictValidationError(
            f"{section}: order is missing id(s): {', '.join(missing)}"
        )


# ---------- reassemble ----------

def reorder_notable(
    preamble: str, items: list[NotableItem], order: list[str]
) -> str:
    """Validate + reassemble the Notable section.

    The preamble (the Reddit-discuss line) is pinned at the top; only the
    items are reorderable.
    """
    validate_order(items, order, section="notable")
    by_id = {it.id: it for it in items}
    ordered = [by_id[oid] for oid in order]
    return reassemble_notable(preamble, ordered)


def reorder_brief(items: list[BriefItem], order: list[str]) -> str:
    validate_order(items, order, section="brief")
    by_id = {it.id: it for it in items}
    ordered = [by_id[oid] for oid in order]
    return reassemble_brief(ordered)


def reorder_journal(items: list[JournalEntry], order: list[str]) -> str:
    validate_order(items, order, section="journal")
    by_id = {it.id: it for it in items}
    ordered = [by_id[oid] for oid in order]
    return reassemble_journal(ordered)


# ---------- belt-and-suspenders lossless check ----------

def _multiset(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def validate_lossless(
    draft_block: str, final_block: str, *, section: str
) -> None:
    """Compare the chunk multiset (by ``raw_bytes``) in draft vs final.

    Reordering preserves the multiset; any modification breaks it. This
    is a final guard *after* the LLM's order has been applied and the
    section reassembled — it catches bugs in our own reassembly path
    (the LLM never gets a chance to introduce a mismatch because it
    never touches ``raw_bytes``, but a subtle parser-bug or off-by-one
    in the reassembler would).

    Notable's preamble is checked separately and must match exactly.
    """
    if section == "notable":
        d_pre, d_items = parse_notable(draft_block)
        f_pre, f_items = parse_notable(final_block)
        if d_pre != f_pre:
            raise StrictValidationError(
                "notable: preamble does not match between draft and final"
            )
        d_bytes = [it.raw_bytes for it in d_items]
        f_bytes = [it.raw_bytes for it in f_items]
    elif section == "brief":
        d_bytes = [it.raw_bytes for it in parse_brief(draft_block)]
        f_bytes = [it.raw_bytes for it in parse_brief(final_block)]
    elif section == "journal":
        d_bytes = [it.raw_bytes for it in parse_journal(draft_block)]
        f_bytes = [it.raw_bytes for it in parse_journal(final_block)]
    else:
        raise ValueError(f"unknown section: {section!r}")

    if _multiset(d_bytes) != _multiset(f_bytes):
        raise StrictValidationError(
            f"{section}: chunk multiset differs between draft and final "
            f"(draft has {len(d_bytes)} items, final has {len(f_bytes)})"
        )
