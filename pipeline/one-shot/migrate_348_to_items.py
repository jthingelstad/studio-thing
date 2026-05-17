"""Migrate WT348's existing ``draft.md`` / ``final.md`` into
``issue_items`` rows.

WT348 is the harness for the row-backed rework — it shipped on
2026-05-16 via the iOS-Shortcut path, before the bot's
``build-publish`` / ``send-to-buttondown`` flow existed. The
snapshot at ``tmp/wt348-snapshot/`` carries the as-shipped
workspace.

What this does:

1. Read ``tmp/wt348-snapshot/draft.md`` (or final.md if the user
   passes ``--source final``).
2. Parse Notable / Brief / Journal blocks via the existing chunk
   parser.
3. INSERT one ``issue_items`` row per item, with ``source='manual'``
   (we don't have the original Pinboard hashes / micro.blog URLs
   without re-running the upstream queries — which is fine for a
   one-time migration). ``source_id`` is the synthetic id from the
   chunk parser (``n1``, ``b2``, ``j3``).
4. For the Team featured entry (visible as ``<!-- block:feature1 -->``
   in final.md), insert it as a journal row with ``is_promoted=1``
   so the re-renderer puts it where it landed in the shipped issue.

Usage::

    venv/bin/python pipeline/one-shot/migrate_348_to_items.py
    venv/bin/python pipeline/one-shot/migrate_348_to_items.py --source final

After running, ``draft.md`` + ``final.md`` can be re-rendered from
rows and diffed against the snapshot to validate the rewrite.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools import db, issue_items
from apps.workshop_bot.tools.content import chunks, draft as draft_mod


SNAPSHOT_DIR = REPO / "tmp" / "wt348-snapshot"


def _strip_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, m.group(2).lstrip("\n")


def _parse_journal_label(raw_bytes: str) -> str | None:
    """Extract the weekday-time label from a journal entry's raw bytes.

    Status entries: ``[Weekday @ H:MM AM/PM](url)`` as the first line.
    Titled entries: ``### [Title](url)  \\n{Weekday @ H:MM AM/PM}``.
    """
    head = raw_bytes.splitlines()
    if not head:
        return None
    first = head[0]
    titled = re.match(r"^### \[[^\]]+\]\([^)]+\) {2}$", first)
    if titled and len(head) >= 2:
        return head[1].strip()
    status = re.match(r"^\[([A-Z][a-z]+ @ \d{1,2}:\d{2} [AP]M)\]", first)
    if status:
        return status.group(1)
    return None


def _journal_body(item: chunks.JournalEntry) -> str:
    """Strip the head line(s) from raw_bytes, leaving just the body
    paragraphs (commentary + inline ``<img>`` tags)."""
    raw = item.raw_bytes
    lines = raw.splitlines()
    if not lines:
        return ""
    if item.title:
        # Titled: head spans 2 lines (H3 + label).
        return "\n".join(lines[2:]).lstrip("\n").rstrip()
    return "\n".join(lines[1:]).lstrip("\n").rstrip()


def _notable_body(item: chunks.NotableItem) -> str:
    """Strip the H3 head, leave the commentary."""
    lines = item.raw_bytes.splitlines()
    return "\n".join(lines[1:]).lstrip("\n").rstrip()


def _brief_body(item: chunks.BriefItem) -> str:
    """Strip the bolded-link suffix from the paragraph; what remains is
    commentary. Brief items look like ``{commentary} → **[Title](url)**``
    (or just the bolded link)."""
    raw = item.raw_bytes
    # Look for the rightmost ``→ **[`` to split commentary from link.
    arrow_idx = raw.rfind(" → **[")
    if arrow_idx > 0:
        return raw[:arrow_idx].rstrip()
    return ""


def migrate(source: str = "draft", verbose: bool = True) -> dict:
    """Parse the WT348 snapshot and INSERT rows. Returns a count summary."""
    src_path = SNAPSHOT_DIR / f"{source}.md"
    if not src_path.exists():
        raise FileNotFoundError(f"snapshot not found: {src_path}")
    text = src_path.read_text(encoding="utf-8")

    blocks = draft_mod.parse_blocks(text)
    notable_preamble, notable_items = chunks.parse_notable(blocks.get("notable") or "")
    brief_items = chunks.parse_brief(blocks.get("brief") or "")
    journal_items = chunks.parse_journal(blocks.get("journal") or "")

    n = 348
    issue_items.clear_issue(n)  # idempotent — re-running the migration is safe

    for it in notable_items:
        issue_items.upsert_item(
            issue_number=n, section="notable", source="manual",
            source_id=f"wt348-{it.id}",
            url=it.url, title=it.title, body_md=_notable_body(it),
        )

    for it in brief_items:
        issue_items.upsert_item(
            issue_number=n, section="brief", source="manual",
            source_id=f"wt348-{it.id}",
            url=it.url, title=it.title, body_md=_brief_body(it),
        )

    for it in journal_items:
        issue_items.upsert_item(
            issue_number=n, section="journal", source="manual",
            source_id=f"wt348-{it.id}",
            url=it.url, title=it.title or None,
            body_md=_journal_body(it),
            metadata={"label": it.label or _parse_journal_label(it.raw_bytes) or "", "published": ""},
        )

    # Feature block (only present when source=final). WT348's final.md
    # has feature1 carrying the Team article promoted from Journal.
    # Note: the ``source_id: jN`` in the frontmatter is the chunk-parser
    # synthetic id from the *original* draft, *before* the promotion
    # removed it from the Journal block. final.md's Journal block was
    # re-parsed after Team was removed, so its synth ids (j1..j14) are
    # renumbered and don't match jN in the frontmatter. Match by URL
    # instead — it's stable.
    feature_raw = (blocks.get("feature1") or "").strip()
    promoted_id = None
    promoted_heading = None
    promoted_position = None
    if feature_raw:
        meta, body = _strip_frontmatter(feature_raw)
        promoted_position = (meta.get("position") or "").strip() or None
        promoted_heading = (meta.get("heading") or "").strip() or None
        if promoted_position and promoted_heading:
            # Extract title/url from the H3 head of the feature body.
            head_match = re.match(
                r"^### \[([^\]]+)\]\(([^)]+)\) {2}\n([A-Z][a-z]+ @ \d{1,2}:\d{2} [AP]M)",
                body,
            )
            if head_match:
                title = head_match.group(1)
                url = head_match.group(2)
                label = head_match.group(3)
                feature_body = "\n".join(body.splitlines()[2:]).lstrip("\n").rstrip()
                # Match by URL against existing journal rows. If found, promote it
                # (it shouldn't normally be in the post-promotion final.md, but
                # defensive). If not, insert as a new journal row + promote.
                rows = issue_items.list_items(n, section="journal")
                target_row = next((r for r in rows if r.get("url") == url), None)
                if target_row is None:
                    new_id = issue_items.upsert_item(
                        issue_number=n, section="journal", source="manual",
                        source_id=f"wt348-feature-{re.sub(r'[^a-z0-9]+', '-', url.lower())[:60]}",
                        url=url, title=title, body_md=feature_body,
                        metadata={"label": label, "published": ""},
                    )
                    target_row = issue_items.get_item(new_id)
                issue_items.promote(
                    int(target_row["id"]),
                    promoted_position=promoted_position,
                    promoted_heading=promoted_heading,
                )
                promoted_id = int(target_row["id"])

    summary = {
        "notable": len(notable_items),
        "brief": len(brief_items),
        "journal": len(journal_items),
        "promoted_id": promoted_id,
        "promoted_heading": promoted_heading,
        "promoted_position": promoted_position,
    }
    if verbose:
        print("WT348 migration:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("draft", "final"), default="final",
                        help="Which snapshot file to read (default: final).")
    args = parser.parse_args()
    db.run_migrations()
    migrate(source=args.source)


if __name__ == "__main__":
    main()
