"""Row-to-markdown rendering for ``issue_items``.

Shared by the surfaces that emit assembled section markdown:

- ``update-draft`` renders ``draft.md`` from the current row state (in
  per-section position order — i.e. whatever order ``reorder`` last
  established, or the upstream-arrival order if no reorder has run yet).
- ``tools/renderers`` renders the section bodies of ``archive.md`` /
  ``buttondown.md`` / the transcript, splicing promoted (featured)
  sections into their declared positions.

The output bytes mirror the section shapes the chunk parser
(``tools.content.chunks``) recognises:

- **Notable** — a one-paragraph italicised Reddit-discuss preamble,
  one blank line, then ``### [Title](url)`` items separated by two
  blank lines.
- **Briefly** — one paragraph per item: ``{commentary} → **[Title](url)**``
  (or just the bolded link when commentary is empty). One blank line
  between items.
- **Journal** — grouped under per-day ``### {Weekday}, {Month} {D}``
  sub-headers (chronological, only days with entries shown). Inside
  each day:
    * Titled posts: ``### [Title](url)\\n\\n{time}\\n\\n{body}`` (H3
      link, time label on its own line below, then body). The day
      header is also H3 (no link); CSS distinguishes the two via
      ``h3:has(a)`` for titled posts vs plain H3 for day headers.
    * Notes (no title): ``[{time}]({url}) — {body}`` (single paragraph
      with the linked time + em-dash + body — compact for one-liners).

The local-time date used for day-bucketing and the time portion shown
on each entry come from the row's ``metadata.published`` (sync layer
records UTC ISO; ``microblog.published_local`` converts to
``America/Chicago``). Falls back to the legacy ``metadata.label``
(``Weekday @ time``) when ``published`` is absent.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .content import microblog


# Membership-block markers (``<!-- cta:N -->`` / ``<!-- thanks:N -->``)
# are a retired editorial vocabulary — they're NEVER in a row's
# ``body_md``. An older manual-seed path baked a rendered marker into a
# notable item's body and the harness caught it leaking into every
# subsequent render. Strip them defensively at the renderer boundary so a
# stray marker in body_md can't slip into draft.md / the shipped bodies.
_MEMBERSHIP_MARKER_RE = re.compile(r"<!--\s*(?:cta|thanks):\d+\s*-->")


def strip_membership_markers(text: str) -> str:
    """Remove any ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers from
    ``text``. Used to sanitize ``body_md`` reads — these markers are a
    retired vocabulary and must never appear in row content."""
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
    is only known at render time.
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
    """Legacy "Weekday @ H:MM AM/PM" label — kept for any caller that
    still needs the full combined form. The new Journal renderer uses
    :func:`_journal_time` (time-only) and :func:`_journal_day_label`
    (day-only) instead, since the day moved into a sub-header."""
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


def _journal_published(row: dict[str, Any]):
    """Return the row's local-time published datetime (or None)."""
    meta = row.get("metadata") or {}
    if not isinstance(meta, dict):
        return None
    return microblog.published_local(meta.get("published"))


def _journal_time(row: dict[str, Any]) -> str:
    """Time-only portion of the entry's local timestamp, e.g. ``3:02 PM``.
    Falls back to splitting a legacy ``Weekday @ time`` label when
    ``metadata.published`` is missing; finally falls back to the raw
    label itself."""
    dt = _journal_published(row)
    if dt is not None:
        hour12 = dt.hour % 12 or 12
        ampm = "AM" if dt.hour < 12 else "PM"
        return f"{hour12}:{dt.minute:02d} {ampm}"
    meta = row.get("metadata") or {}
    legacy = (meta.get("label") or "").strip() if isinstance(meta, dict) else ""
    if " @ " in legacy:
        return legacy.split(" @ ", 1)[1].strip()
    return legacy


def _journal_day_label(row: dict[str, Any]) -> str:
    """Per-day H3 sub-header text — ``Weekday, Month D`` (no year).
    Falls back to the weekday portion of a legacy ``Weekday @ time``
    label when ``metadata.published`` is missing."""
    dt = _journal_published(row)
    if dt is not None:
        # %-d is non-portable across platforms; format the day separately.
        return f"{dt.strftime('%A, %B')} {dt.day}"
    meta = row.get("metadata") or {}
    legacy = (meta.get("label") or "").strip() if isinstance(meta, dict) else ""
    if " @ " in legacy:
        return legacy.split(" @ ", 1)[0].strip()
    return legacy or "Undated"


def _journal_day_key(row: dict[str, Any]) -> str:
    """Stable bucketing key for grouping rows by local-date. Rows that
    can't be dated bucket under the literal ``undated`` key (last)."""
    dt = _journal_published(row)
    if dt is not None:
        return dt.date().isoformat()
    return "zzz-undated"


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
    """Render a single Journal entry. Two tiers:

    - **Titled post** (title + url): H3 link, then the time label as a
      paragraph below, then the body.
    - **Note** (no title, url-linked timestamp): single paragraph with
      the linked time + em-dash + body, so one-liners stay compact.

    The day no longer appears on the entry itself — it lives in the
    per-day H3 sub-header :func:`render_journal` emits above the entry.
    """
    url = _row_str(row, "url")
    title = _row_str(row, "title")
    body = _row_str(row, "body_md")
    time_label = _journal_time(row)
    if title and url:
        head = f"### [{title}]({url})"
        if time_label:
            head += f"\n\n{time_label}"
        return f"{head}\n\n{body}" if body else head
    if url:
        if time_label and body:
            return f"[{time_label}]({url}) — {body}"
        if time_label:
            return f"[{time_label}]({url})"
        return body or ""
    # No URL — bare time + body (defensive; sync always gives us a URL).
    if time_label and body:
        return f"{time_label} — {body}"
    return time_label or body or ""


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


def _bucket_journal_by_day(rows: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group ``rows`` by local-time date, preserving the iteration order
    within and across days. Returns ``[(day_label, [rows…]), …]``.
    Empty days are naturally absent (only days with ≥1 entry appear)."""
    buckets: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for r in rows:
        key = _journal_day_key(r)
        if key not in buckets:
            buckets[key] = (_journal_day_label(r), [])
        buckets[key][1].append(r)
    # Iterate in insertion order — rows arrive in publish-date sequence
    # from sync, so day buckets land chronologically too. The ``undated``
    # bucket (if any) sorts last because its key starts with ``zzz-``.
    return [(label, rs) for _key, (label, rs) in sorted(buckets.items())]


def render_journal(rows: list[dict[str, Any]]) -> str:
    """Render the Journal block body: per-day ``### {Weekday}, {Month} D``
    sub-headers grouping their entries below them. Titled posts render
    with H3-link heading + time line; notes render as bare-time
    paragraphs (``[3:02 PM](url) — body``). Empty days are skipped.

    Within a day, entries are separated by one blank line (paragraph
    break). Days are separated by two blank lines for visual rhythm.
    """
    if not rows:
        return ""
    pieces: list[str] = []
    for day_label, day_rows in _bucket_journal_by_day(rows):
        block = [f"### {day_label}"]
        for r in day_rows:
            entry = _render_journal_entry(r)
            if entry:
                block.append(entry)
        pieces.append("\n\n".join(block))
    return "\n\n\n".join(pieces)


# ---------- section bodies with inline markers (retired) ----------
#
# These helpers spliced ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers
# after specific items in a section, back when membership-block placement
# was an inline marker. Placement is now hardcoded in ``render_email``'s
# ``CTA_SLOT_POSITIONS`` map; these are unused and kept only for reference.

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
    """Day-grouped Journal renderer with ``<!-- cta:N -->`` / ``<!-- thanks:N -->``
    markers spliced inline after the items that declared them.

    Markers anchored to a row appear inside that row's day-block (after
    the row, separated by a blank line). ``trailing_markers``
    (``before_haiku`` placements) append after the entire section, at
    the same nesting level as the last day-block."""
    if not rows:
        if trailing_markers:
            return "\n\n\n".join(trailing_markers)
        return ""
    pieces: list[str] = []
    for day_label, day_rows in _bucket_journal_by_day(rows):
        block: list[str] = [f"### {day_label}"]
        for r in day_rows:
            entry = _render_journal_entry(r)
            if entry:
                block.append(entry)
            block.extend(_build_marker_seq(r, markers_after))
        pieces.append("\n\n".join(block))
    if trailing_markers:
        pieces.extend(trailing_markers)
    return "\n\n\n".join(pieces)


# ---------- featured (promoted) sections ----------

def render_featured_sections(rows: list[dict[str, Any]]) -> str:
    """Render every promoted row as a sequence of ``## {heading}\\n\\n{body}``
    sections, joined with two blank lines so they read as standalone
    H2-level sections of the issue. Used by ``update-draft`` to populate
    the new ``featured`` block above Notable; rows are passed in their
    natural publish-date order (caller filters to ``is_promoted=1``)."""
    if not rows:
        return ""
    return "\n\n\n".join(render_featured_section(r) for r in rows)


def render_featured_section(row: dict[str, Any]) -> str:
    """Render one promoted item as its own standalone ``## {heading}``
    section body. The heading is the editorial heading Eddy chose; the
    body is the item's content rendered the same way it would render in
    its parent section (a promoted Journal post still renders with its
    weekday-time label; a promoted Notable item still renders with its
    H3 link + commentary).

    Used by the renderers (``tools/renderers``) to splice the feature
    block into ``archive.md`` / ``buttondown.md`` at ``promoted_position``
    — inline at the right spot, not gathered at the bottom of the file.
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
