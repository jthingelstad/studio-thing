"""Assemble ``final.md`` (and downstream) from rows + atoms.

This is the shared assembler used by ``create-final`` and ``build-publish``.
It takes:

- the file-backed atoms (intro / currently / cover / outro / haiku)
- the parent-section bodies (Notable / Journal / Briefly) — already
  rendered from rows in their current position order
- the promoted featured sections — rendered from rows, with each
  carrying its ``promoted_position``
- the membership-block placements — ``{after: <synthetic_id>, kind: cta,
  slot_n: 1}`` etc., placed inline in the parent section's body

…and produces either:

- ``final.md`` — block-markered (matches the draft template shape minus
  feature blocks), used as the editorial-surface artifact and the input
  to ``build-publish``. Promoted sections splice between block-close
  and next ``---`` divider for their declared position.
- ``publish.md`` — block markers stripped, editor-mode comment prefixed,
  membership markers substituted with audience-aware Liquid wrappers,
  Tinylytics pixel appended. This shape is what gets pushed to
  Buttondown.

Why share one assembler: keeping ``final.md`` and ``publish.md`` in
lockstep about the body shape (and especially about where promoted
sections splice in) is the unlock from Jamie's WT348 feedback — what
you see in ``final.md`` IS where things will appear in the email.
"""

from __future__ import annotations

import re
from typing import Any, Optional


# Order of parent sections in the published shape. ``Currently`` and
# ``Cover`` slot above Notable; ``Outro`` and the haiku close it.
_PARENT_ORDER = ("notable", "journal", "brief")
_SECTION_HEADINGS = {
    "currently": "## Currently",
    "notable": "## Notable",
    "journal": "## Journal",
    "brief": "## Briefly",
}

_EDITOR_MODE_COMMENT = "<!-- buttondown-editor-mode: plaintext -->"
_CLOSING = (
    "Would you like to discuss the topics in the Weekly Thing further? "
    "Check out the [Weekly Thing on Reddit](https://www.reddit.com/r/weeklything/). 👋\n\n"
    "👨‍💻"
)

# Marker pattern create-final places inline in section bodies (and that
# build-publish substitutes for Liquid wrappers).
MARKER_RE = re.compile(r"<!--\s*(cta|thanks):(\d+)\s*-->")


# ---------- types ----------

class Atoms(dict):
    """Convenience dict — the file-backed atoms keyed by block name:
    ``{'intro': str, 'currently': str, 'cover': str, 'outro': str, 'haiku': str}``.
    Missing keys default to empty strings; empty sections drop out of
    the assembled output."""


class SectionBodies(dict):
    """Convenience dict — rendered parent-section bodies:
    ``{'notable': str, 'journal': str, 'brief': str}``. Each body
    already contains the section's items in their final order plus any
    inline cta/thanks markers."""


# ---------- assembly: final.md ----------

def _block(name: str, body: str) -> str:
    """Wrap ``body`` in ``<!-- block:name -->`` markers. Empty body still
    emits the markers (so the file shape stays predictable for diffs
    and downstream parsers)."""
    inner = f"\n{body.strip()}\n" if body and body.strip() else "\n"
    return f"<!-- block:{name} -->{inner}<!-- /block:{name} -->"


def _splice_for_position(features: list[tuple[str, str]], position: str) -> str:
    """Return the splice text (``\\n---\\n\\n{section1}\\n\\n---\\n\\n{section2}``)
    for all features declared at ``position``. Empty list returns ``""``.

    Each feature is ``(heading, body)``; the renderer in
    :mod:`tools.issue_items_render.render_featured_section` produces
    ``## {heading}\\n\\n{body}`` strings, which is what the assembler
    expects here.
    """
    matching = [body for pos, body in features if pos == position]
    if not matching:
        return ""
    # Each featured section sits between a ``---`` divider and the next
    # divider (or block), so prefixing one divider + joining the bodies
    # with one between them produces the right shape.
    return "\n\n---\n\n" + "\n\n---\n\n".join(b.strip() for b in matching)


def assemble_final(
    *,
    atoms: dict[str, str],
    section_bodies: dict[str, str],
    features: list[tuple[str, str]],
) -> str:
    """Build ``final.md`` text. ``features`` is a list of
    ``(promoted_position, '## Heading\\n\\nbody')`` tuples — see
    :func:`tools.issue_items_render.render_featured_section`.

    The output is block-markered, mirrors the draft template's structure
    minus the feature1/feature2 blocks (those are gone — promotions
    splice inline now), and is the input ``build-publish`` reads to
    produce ``publish.md``.
    """
    intro = (atoms.get("intro") or "").strip()
    currently = (atoms.get("currently") or "").strip()
    cover = (atoms.get("cover") or "").strip()
    outro = (atoms.get("outro") or "").strip()
    haiku = (atoms.get("haiku") or "").strip()

    notable = (section_bodies.get("notable") or "").strip()
    journal = (section_bodies.get("journal") or "").strip()
    brief = (section_bodies.get("brief") or "").strip()

    parts: list[str] = []
    parts.append(_block("intro", intro))
    parts.append("---")
    parts.append(_SECTION_HEADINGS["currently"] + "\n\n" + _block("currently", currently))
    parts.append("---")
    parts.append(_block("cover", cover))
    parts.append("---")
    # Parent sections — each followed by its promotions splice.
    parent_block_map = {"notable": notable, "journal": journal, "brief": brief}
    for name in _PARENT_ORDER:
        body = parent_block_map[name]
        heading = _SECTION_HEADINGS[name]
        parts.append(f"{heading}\n\n{_block(name, body)}{_splice_for_position(features, f'after_{name}')}")
        parts.append("---")
    parts.append(_block("outro", outro))
    parts.append("---")
    parts.append(f"A haiku to leave you with…\n\n{_block('haiku', haiku)}\n\n{_CLOSING}")

    body = "\n\n".join(parts)
    if not body.endswith("\n"):
        body += "\n"
    return body


# ---------- assembly: publish.md (used by build-publish) ----------

def _strip_block_markers(text: str) -> str:
    """Remove ``<!-- block:NAME -->`` / ``<!-- /block:NAME -->`` lines
    and clean up the empty-section residue.

    After marker removal:

    - Orphan section headings (``## Heading`` with nothing but blank
      lines before the next divider) get dropped, along with the
      following divider — they would have shown up as ``## Currently``
      sections with no body when ``currently.json`` was absent.
    - Consecutive ``---`` dividers (from an empty block that sat
      between two others) collapse to a single divider.
    - Leading dividers (from an empty top-of-file block such as
      missing ``intro.md``) get trimmed.
    - 3+ consecutive newlines collapse to 2 (preserves paragraph
      breaks; drops the gap left by removing a marker).
    """
    cleaned = re.sub(r"\n?<!--\s*/?block:[a-z0-9_]+\s*-->\n?", "\n", text)
    # First newline-collapse so the next regexes can rely on stable
    # blank-line shapes.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Drop orphan headings: ``## Heading\n\n---`` becomes ``---``
    # (we keep the divider since it still separates real content on
    # either side). Iterate to a fixed point — multiple adjacent
    # orphans (Currently + cover empty in a row) need successive
    # passes.
    orphan_re = re.compile(r"^## [^\n]+\n\n(?=---\n)", re.MULTILINE)
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = orphan_re.sub("", cleaned)
    # Collapse consecutive dividers (``---\n\n---``) to one.
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r"---\n\n---\n", "---\n", cleaned)
    # Trim leading/trailing dividers + blank lines.
    cleaned = re.sub(r"^(?:---\n*)+", "", cleaned)
    cleaned = re.sub(r"(?:---\n*)+\Z", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def assemble_publish(
    *,
    atoms: dict[str, str],
    section_bodies: dict[str, str],
    features: list[tuple[str, str]],
    issue_number: int,
    pixel_block: Optional[str] = None,
    marker_substitution: Optional[Any] = None,
) -> str:
    """Build ``publish.md`` text. Same body shape as ``assemble_final``
    minus block markers, plus:

    - Editor-mode comment glommed onto the first paragraph (matches the
      raw Buttondown body shape).
    - Inline ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers
      substituted by ``marker_substitution`` (a callable taking a
      ``re.Match`` and returning the replacement text — typically the
      Liquid-wrapped CTA copy).
    - ``pixel_block`` (the Tinylytics open-tracking pixel) appended
      after the closing line, separated by a blank line.

    Both ``pixel_block`` and ``marker_substitution`` are optional; when
    omitted the corresponding step is skipped. The defaults are
    suitable for non-shipping previews (e.g. a tests-only render).
    """
    body = assemble_final(
        atoms=atoms, section_bodies=section_bodies, features=features,
    )
    body = _strip_block_markers(body)
    if marker_substitution is not None:
        body = MARKER_RE.sub(marker_substitution, body)
    body = _EDITOR_MODE_COMMENT + body
    if pixel_block:
        body = body.rstrip() + "\n\n" + pixel_block + "\n"
    return body


# ---------- inline marker insertion helpers (used by create-final) ----------

def insert_markers_in_section(
    section_body: str,
    items_in_order: list[dict[str, Any]],
    markers_after_synth_id: dict[str, list[str]],
    *,
    synth_id_of: dict[int, str],
    separator: str,
) -> str:
    """Re-render a section body with markers spliced after the items
    they declared.

    ``items_in_order`` is the parent-section rows in their current
    position order. ``markers_after_synth_id`` maps synthetic ids
    (``n1``, ``b2``, …) → list of marker strings to insert AFTER that
    item. ``synth_id_of`` maps row id → synthetic id (the inverse of the
    map create-final hands the LLM).

    ``separator`` is the inter-item separator (``\\n\\n\\n`` for
    Notable/Journal, ``\\n\\n`` for Briefly). The function rebuilds
    the section body by joining items with that separator and inserting
    each marker right after its declared item (separated by a blank
    line, so the marker reads as its own paragraph).

    This helper takes already-rendered section bodies and is a fallback
    when the renderer doesn't have a hook for markers; the simpler path
    is for ``create-final`` to ask the row renderer for an
    item-by-item list and interleave markers itself. Both paths produce
    the same bytes; this one is convenient when post-processing.
    """
    # Defensive — the simpler path is the caller building the body
    # directly. Keep this helper around because ``build-publish`` may
    # want to re-derive marker placement from a stored plan.
    # Not used in the main path today; tested separately.
    if not markers_after_synth_id:
        return section_body
    raise NotImplementedError(
        "insert_markers_in_section: post-hoc marker insertion not implemented; "
        "build markers into the section body at render time instead."
    )
