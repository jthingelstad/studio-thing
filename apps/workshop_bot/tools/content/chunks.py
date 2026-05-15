"""Chunk parser for ``draft.md`` section blocks.

The chunk-based reorder design hinges on **code moving the content; the LLM
only specifying the order**. This module is the parser half: it walks the
content of a single ``<!-- block:NAME -->`` … ``<!-- /block:NAME -->``
section and emits typed items keyed by stable ids, each carrying the *exact
byte slice* of the original block text. The reassembler in
:mod:`apps.workshop_bot.tools.content.reorder` then glues those slices back
together in whatever order the LLM specified — without ever touching the
bytes themselves.

Three section shapes, mirroring the renderers in
``apps/workshop_bot/jobs/update_draft.py`` (``_render_notable`` /
``_render_brief`` / ``_render_journal``):

- **Notable** — a one-paragraph italicized Reddit-discuss preamble (pinned,
  never reorderable), then ``### [Title](url)`` H3-link items separated by
  two blank lines. Each item is the H3 line plus zero-or-more paragraphs of
  commentary.
- **Briefly** — paragraphs separated by one blank line; each paragraph ends
  with a bolded link ``**[Title](url)**`` (optionally preceded by an arrow
  ``→`` and commentary).
- **Journal** — entries separated by two blank lines; each entry is either
  an *elevated* H3-titled post (``### [Title](url)  \\n{Weekday @ H:MM
  AM/PM}\\n\\n{body}``) or a *status* update (``[Weekday @ H:MM
  AM/PM](url)\\n\\n{body}``). Photos already live inside the body as native
  ``<img>`` tags from ``tools/journal_images``.

Item ids are deterministic — ``n1`` / ``n2`` for Notable, ``b1`` / ``b2``
for Briefly, ``j1`` / ``j2`` for Journal — assigned in input order. The
ids are what the LLM names in its ordering JSON; the reassembler validates
that the LLM's order is a strict permutation of the parsed ids.

This parser handles Buttondown-era bodies (the shape ``update-draft``
produces). The much older Tinyletter and MailChimp eras have different
section conventions (see the era table in repo ``CLAUDE.md``); those are
not used by the in-flight editorial chain and are out of scope here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------- regexes ----------

# Notable item — H3-link heading on its own line: `### [Title](url)`.
_NOTABLE_H3_RE = re.compile(r"^### \[([^\]]+)\]\(([^)]+)\)\s*$", re.MULTILINE)

# Briefly item — bolded markdown link, anywhere in the paragraph.
_BRIEF_LINK_RE = re.compile(r"\*\*\[([^\]]+)\]\(([^)]+)\)\*\*")

# Journal entry — *elevated* H3-titled. The H3 line ends with a markdown
# hard break (two trailing spaces); the weekday/time label is on the next
# line, followed by an optional body paragraph.
_JOURNAL_TITLED_HEAD_RE = re.compile(
    r"^### \[([^\]]+)\]\(([^)]+)\) {2}\n([A-Z][a-z]+ @ \d{1,2}:\d{2} [AP]M)\s*$",
    re.MULTILINE,
)

# Journal entry — *status* update. Single-line header: `[Weekday @ X:XX AM/PM](url)`.
_JOURNAL_STATUS_HEAD_RE = re.compile(
    r"^\[([A-Z][a-z]+ @ \d{1,2}:\d{2} [AP]M)\]\(([^)]+)\)\s*$",
    re.MULTILINE,
)


# ---------- dataclasses ----------

@dataclass(frozen=True)
class NotableItem:
    """One Notable item. ``raw_bytes`` is the exact slice from the block
    text — the H3 line, blank line, and the commentary paragraphs. Trailing
    whitespace is stripped so the reassembler can re-glue with a clean
    two-blank-line separator."""

    id: str
    title: str
    url: str
    raw_bytes: str


@dataclass(frozen=True)
class BriefItem:
    """One Briefly item. ``raw_bytes`` is the exact paragraph including the
    bolded link at the end."""

    id: str
    title: str
    url: str
    raw_bytes: str


@dataclass(frozen=True)
class JournalEntry:
    """One Journal entry. ``label`` is the human-readable header (weekday +
    12-hour time, e.g. ``Sunday @ 4:16 PM``). ``url`` is the micro.blog
    post URL. Elevated (titled) entries also carry a ``title``; status
    entries leave that empty."""

    id: str
    label: str
    url: str
    title: str
    raw_bytes: str


# ---------- parse ----------

def parse_notable(block: str) -> tuple[str, list[NotableItem]]:
    """Parse a Notable block into ``(preamble, items)``.

    The preamble is the Reddit-discuss italicized line (carrying the issue
    number) that ``update-draft`` puts at the top of the rendered block.
    It is pinned — the LLM cannot reorder it, and the reassembler always
    re-emits it at the top.

    An empty block returns ``("", [])``. A block with content but no H3
    items returns the content as preamble and an empty items list.
    """
    text = (block or "").strip()
    if not text:
        return "", []
    first = _NOTABLE_H3_RE.search(text)
    if first is None:
        return text, []
    preamble = text[: first.start()].rstrip()
    matches = list(_NOTABLE_H3_RE.finditer(text))
    items: list[NotableItem] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # Strip only trailing newlines (the inter-item ``\n\n\n`` separator
        # or, for the last item, any tail newlines from the input). Trailing
        # spaces on the last commentary line are preserved — they're part of
        # the item's bytes and must round-trip exactly.
        raw = text[start:end].rstrip("\n")
        items.append(
            NotableItem(
                id=f"n{i + 1}",
                title=m.group(1).strip(),
                url=m.group(2).strip(),
                raw_bytes=raw,
            )
        )
    return preamble, items


def parse_brief(block: str) -> list[BriefItem]:
    """Parse a Briefly block into items.

    Items are paragraph-separated. Each item is a paragraph whose last (or
    only) bolded markdown link is the item's link; commentary precedes the
    arrow. Stray paragraphs without a bolded link are silently dropped
    (placeholders, etc.).
    """
    text = (block or "").strip()
    if not text:
        return []
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    items: list[BriefItem] = []
    counter = 0
    for chunk in chunks:
        link_matches = list(_BRIEF_LINK_RE.finditer(chunk))
        if not link_matches:
            continue
        m = link_matches[-1]
        counter += 1
        items.append(
            BriefItem(
                id=f"b{counter}",
                title=m.group(1).strip(),
                url=m.group(2).strip(),
                raw_bytes=chunk,
            )
        )
    return items


def parse_journal(block: str) -> list[JournalEntry]:
    """Parse a Journal block into entries.

    Entries are separated by two blank lines (``\\n\\n\\n``). Each entry
    must start with either an elevated H3-titled header or a status-update
    header; chunks that don't match either are silently dropped.
    """
    text = (block or "").strip()
    if not text:
        return []
    chunks = [c.strip() for c in re.split(r"\n\s*\n\s*\n+", text) if c.strip()]
    entries: list[JournalEntry] = []
    counter = 0
    for chunk in chunks:
        titled = _JOURNAL_TITLED_HEAD_RE.match(chunk)
        if titled is not None:
            counter += 1
            entries.append(
                JournalEntry(
                    id=f"j{counter}",
                    label=titled.group(3).strip(),
                    url=titled.group(2).strip(),
                    title=titled.group(1).strip(),
                    raw_bytes=chunk,
                )
            )
            continue
        status = _JOURNAL_STATUS_HEAD_RE.match(chunk)
        if status is not None:
            counter += 1
            entries.append(
                JournalEntry(
                    id=f"j{counter}",
                    label=status.group(1).strip(),
                    url=status.group(2).strip(),
                    title="",
                    raw_bytes=chunk,
                )
            )
            continue
        # silently skip un-recognized chunks
    return entries


# ---------- reassemble ----------
#
# The separators here mirror the renderers in ``update_draft.py`` exactly:
# Notable + Journal items glue with two blank lines (``\n\n\n``); Briefly
# items glue with one blank line (``\n\n``). The Notable preamble (when
# present) is followed by one blank line before the first item.

def reassemble_notable(preamble: str, items: list[NotableItem]) -> str:
    blocks = [it.raw_bytes for it in items]
    if not blocks:
        return preamble
    body = "\n\n\n".join(blocks)
    return f"{preamble}\n\n{body}" if preamble else body


def reassemble_brief(items: list[BriefItem]) -> str:
    return "\n\n".join(it.raw_bytes for it in items)


def reassemble_journal(items: list[JournalEntry]) -> str:
    return "\n\n\n".join(it.raw_bytes for it in items)
