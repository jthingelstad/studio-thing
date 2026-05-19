"""Row-to-markdown rendering for ``issue_items``.

Shared between the three jobs that emit assembled documents:

- ``update-draft`` renders ``draft.md`` from the current row state (in
  per-section position order — i.e. whatever order ``create-final``
  last established, or the upstream-arrival order if no reorder has
  run yet).
- ``create-final`` renders the body of ``final.md`` after reordering.
- ``build-publish`` renders the body of ``buttondown.md``, splicing
  promoted (featured) sections into their declared positions.

The output bytes mirror the section shapes the chunk parser
(``tools.content.chunks``) recognises:

- **Notable** — a one-paragraph italicised Reddit-discuss preamble,
  one blank line, then ``### [Title](url)`` items separated by two
  blank lines.
- **Briefly** — one paragraph per item: ``{commentary} → **[Title](url)**``
  (or just the bolded link when commentary is empty). One blank line
  between items.
- **Journal** — entries separated by two blank lines; titled posts
  render as ``### [Title](url)  \\n{label}\\n\\n{body}``, status posts
  render as ``[{label}]({url})\\n\\n{body}``.

The ``label`` for a Journal entry is taken from the row's
``metadata.label`` if present (the sync layer pre-computes it from
``published`` so re-renders are deterministic across clock drift);
otherwise it falls back to recomputing.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .content import microblog


# Membership-block markers live in ``final.md`` (placed there by
# ``create-final`` at editorial time) — NEVER in a row's ``body_md``.
# An older manual-seed path baked the rendered marker into a notable
# item's body and the harness caught it leaking into every subsequent
# render. Strip them defensively at the renderer boundary so a stray
# marker in body_md can't slip into draft.md / passthrough final.md.
_MEMBERSHIP_MARKER_RE = re.compile(r"<!--\s*(?:cta|thanks):\d+\s*-->")


def strip_membership_markers(text: str) -> str:
    """Remove any ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers from
    ``text``. Used to sanitize ``body_md`` reads — placement of these
    markers is editorial state (``final.md``), not row content."""
    if not text or "<!--" not in text:
        return text
    cleaned = _MEMBERSHIP_MARKER_RE.sub("", text)
    # Collapse any blank-line clusters left behind so the output doesn't
    # carry a "ghost paragraph" where the marker used to sit.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip("\n")


# ---------- preamble helpers ----------

def reddit_tag_line(issue_number: int) -> str:
    """The pinned "discuss on Reddit" preamble at the top of Notable.

    Generated (not templated) because it carries the issue number, which
    only ``update-draft`` / ``create-final`` know at fill time.
    """
    n = int(issue_number)
    return (
        f"_You can discuss any of these links at the "
        f"[Weekly Thing {n} tag in r/WeeklyThing]"
        f"(https://www.reddit.com/r/weeklything/?f=flair_name%3A%22Weekly%20Thing%20{n}%22)._"
    )


# ---------- per-row renderers ----------

def _row_str(row: dict[str, Any], key: str) -> str:
    """Pull a string field from a row, treating None/empty as ''. Strips
    membership-block markers from ``body_md`` reads — see
    :func:`strip_membership_markers`."""
    v = row.get(key)
    if not isinstance(v, str):
        return ""
    text = v.strip()
    if key == "body_md":
        text = strip_membership_markers(text)
    return text


def _journal_label(row: dict[str, Any]) -> str:
    """Use the stored label when present (computed at sync time); else
    recompute from ``metadata.published``. Falls back to the raw
    ``published`` string when both are absent — defensive."""
    meta = row.get("metadata") or {}
    label = (meta.get("label") or "").strip() if isinstance(meta, dict) else ""
    if label:
        return label
    published = meta.get("published") if isinstance(meta, dict) else None
    dt = microblog.published_local(published)
    if dt is None:
        return str(published or "").strip()
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A')} @ {hour12}:{dt.minute:02d} {ampm}"


def _render_notable_item(row: dict[str, Any]) -> str:
    url = _row_str(row, "url")
    title = _row_str(row, "title") or url or "(untitled)"
    commentary = _row_str(row, "body_md")
    head = f"### [{title}]({url})"
    return f"{head}\n\n{commentary}" if commentary else head


def _render_brief_item(row: dict[str, Any]) -> str:
    url = _row_str(row, "url")
    title = _row_str(row, "title") or url or "(untitled)"
    commentary = _row_str(row, "body_md")
    link = f"**[{title}]({url})**"
    return f"{commentary} → {link}" if commentary else link


def _render_journal_entry(row: dict[str, Any]) -> str:
    url = _row_str(row, "url")
    title = _row_str(row, "title")
    body = _row_str(row, "body_md")
    label = _journal_label(row)
    if title and url:
        head = f"### [{title}]({url})  \n{label}"
    elif url:
        head = f"[{label}]({url})"
    else:
        head = label
    return f"{head}\n\n{body}" if body else head


# ---------- section renderers ----------

def render_notable(rows: list[dict[str, Any]], issue_number: int) -> str:
    """Render the Notable block body: preamble + items.

    Empty rows → empty string (the block is dropped from the assembled
    document by the parent renderer; matches the existing behavior).
    """
    bodies = [_render_notable_item(r) for r in rows]
    if not bodies:
        return ""
    return reddit_tag_line(issue_number) + "\n\n" + "\n\n\n".join(bodies)


def render_brief(rows: list[dict[str, Any]]) -> str:
    """Render the Briefly block body. One blank line between items."""
    return "\n\n".join(_render_brief_item(r) for r in rows)


def render_journal(rows: list[dict[str, Any]]) -> str:
    """Render the Journal block body. Two blank lines between entries
    (one paragraph break between the head and the body inside each
    entry)."""
    return "\n\n\n".join(_render_journal_entry(r) for r in rows)


# ---------- section bodies with inline markers ----------
#
# ``create-final`` needs to splice ``<!-- cta:N -->`` / ``<!-- thanks:N -->``
# markers after specific items in a section. These helpers do the same
# join-and-separate as the plain renderers above, with each marker
# emitted as its own paragraph after the item that declared it.

def _build_marker_seq(
    row: dict[str, Any],
    markers_after: dict[Any, list[str]],
) -> list[str]:
    """Lookup markers anchored to a row, in declaration order. Keyed by
    row id (the int) so callers don't have to maintain a separate
    synthetic-id map."""
    return list(markers_after.get(row.get("id"), ()))


def render_notable_with_markers(
    rows: list[dict[str, Any]],
    issue_number: int,
    markers_after: dict[Any, list[str]],
    *,
    trailing_markers: Optional[list[str]] = None,
) -> str:
    """Like :func:`render_notable`, but with markers spliced inline after
    the items that declared them. ``trailing_markers`` (when given) are
    appended after the last item — that's where ``before_haiku``
    markers land when this section is the last non-empty one."""
    if not rows:
        if trailing_markers:
            return reddit_tag_line(issue_number) + "\n\n" + "\n\n\n".join(trailing_markers)
        return ""
    pieces: list[str] = []
    for r in rows:
        pieces.append(_render_notable_item(r))
        pieces.extend(_build_marker_seq(r, markers_after))
    if trailing_markers:
        pieces.extend(trailing_markers)
    return reddit_tag_line(issue_number) + "\n\n" + "\n\n\n".join(pieces)


def render_brief_with_markers(
    rows: list[dict[str, Any]],
    markers_after: dict[Any, list[str]],
    *,
    trailing_markers: Optional[list[str]] = None,
) -> str:
    pieces: list[str] = []
    for r in rows:
        pieces.append(_render_brief_item(r))
        pieces.extend(_build_marker_seq(r, markers_after))
    if trailing_markers:
        pieces.extend(trailing_markers)
    return "\n\n".join(pieces)


def render_journal_with_markers(
    rows: list[dict[str, Any]],
    markers_after: dict[Any, list[str]],
    *,
    trailing_markers: Optional[list[str]] = None,
) -> str:
    pieces: list[str] = []
    for r in rows:
        pieces.append(_render_journal_entry(r))
        pieces.extend(_build_marker_seq(r, markers_after))
    if trailing_markers:
        pieces.extend(trailing_markers)
    return "\n\n\n".join(pieces)


# ---------- featured (promoted) sections ----------

def render_featured_section(row: dict[str, Any]) -> str:
    """Render one promoted item as its own standalone ``## {heading}``
    section body. The heading is the editorial heading Eddy chose; the
    body is the item's content rendered the same way it would render in
    its parent section (a promoted Journal post still renders with its
    weekday-time label; a promoted Notable item still renders with its
    H3 link + commentary).

    Used by ``build-publish`` (splice into ``buttondown.md`` at
    ``promoted_position``) and by the updated ``final.md`` renderer (so
    ``final.md`` reads as the issue will actually publish — feature
    blocks inline at the right spot, not gathered at the bottom of the
    file).
    """
    section = (row.get("section") or "").strip()
    heading = (row.get("promoted_heading") or "").strip()
    if not heading:
        raise ValueError(
            f"promoted row id={row.get('id')!r} is missing promoted_heading"
        )
    if section == "notable":
        body = _render_notable_item(row)
    elif section == "brief":
        body = _render_brief_item(row)
    elif section == "journal":
        body = _render_journal_entry(row)
    else:
        raise ValueError(
            f"promoted row id={row.get('id')!r} has unknown section {section!r}"
        )
    return f"## {heading}\n\n{body}"
