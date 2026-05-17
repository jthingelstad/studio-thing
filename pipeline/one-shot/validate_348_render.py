"""Re-render WT348 from ``issue_items`` and diff against the snapshot.

Run :mod:`migrate_348_to_items` first to populate the rows. This
script then re-renders ``draft.md`` and ``final.md`` from the row
state plus the file-backed atoms (read from
``tmp/wt348-snapshot/*``) and emits a structured comparison report.

What we expect:

- **draft.md** content is the same as the snapshot *minus* the
  promoted Team article (which lives in feature1 in the snapshot
  but is filtered out of draft renders in the row-backed model).
- **final.md** has all the same content as the snapshot, with the
  Team article spliced inline as ``## The Weekly Thing Team``
  between Notable and Journal — NOT as a ``<!-- block:feature1 -->``
  block at the bottom of the file. This is the explicit fix for
  Jamie's WT348 feedback (the file now reads as the issue will
  publish).
- No content drift: every original byte that survived create-final
  appears in the re-render.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools import (
    db, issue_assembly, issue_items, issue_items_render,
)
from apps.workshop_bot.jobs import _base


SNAPSHOT_DIR = REPO / "tmp" / "wt348-snapshot"


def _read_snapshot(name: str) -> str:
    return (SNAPSHOT_DIR / name).read_text(encoding="utf-8")


def _atoms_from_snapshot() -> dict[str, str]:
    """Pull each atom out of the snapshot draft.md as it was when WT348
    shipped. Using draft.md (not final.md) so we get the exact
    pre-rendered atom content (final.md should have the same atoms,
    but draft.md is the canonical source)."""
    draft = _read_snapshot("draft.md")
    return {
        "intro": (_base.get_block(draft, "intro") or "").strip(),
        "currently": (_base.get_block(draft, "currently") or "").strip(),
        "cover": (_base.get_block(draft, "cover") or "").strip(),
        "outro": (_base.get_block(draft, "outro") or "").strip(),
        "haiku": (_base.get_block(draft, "haiku") or "").strip(),
    }


def _render_draft_from_rows(atoms: dict[str, str]) -> str:
    """Same shape ``update-draft._gather_fills`` produces: rebuild from
    the template, fill each block from rows + atoms. Promoted items
    are excluded from the parent section (they'd appear in final.md
    inline; draft.md is the pre-final view)."""
    notable_rows = issue_items.list_items(348, section="notable", include_promoted=False)
    journal_rows = issue_items.list_items(348, section="journal", include_promoted=False)
    brief_rows = issue_items.list_items(348, section="brief", include_promoted=False)
    fills = {
        "intro": atoms["intro"],
        "currently": atoms["currently"],
        "cover": atoms["cover"],
        "notable": issue_items_render.render_notable(notable_rows, 348),
        "journal": issue_items_render.render_journal(journal_rows),
        "brief": issue_items_render.render_brief(brief_rows),
        "outro": atoms["outro"],
        "haiku": atoms["haiku"],
    }
    text = _base.starter_template()
    for name, content in fills.items():
        text = _base.replace_block(text, name, content)
    return text


def _render_final_from_rows(atoms: dict[str, str]) -> str:
    notable_rows = issue_items.list_items(348, section="notable", include_promoted=False)
    journal_rows = issue_items.list_items(348, section="journal", include_promoted=False)
    brief_rows = issue_items.list_items(348, section="brief", include_promoted=False)
    promoted = issue_items.promoted_items(348)
    section_bodies = {
        "notable": issue_items_render.render_notable(notable_rows, 348),
        "journal": issue_items_render.render_journal(journal_rows),
        "brief": issue_items_render.render_brief(brief_rows),
    }
    features = [
        (p["promoted_position"], issue_items_render.render_featured_section(p))
        for p in promoted
        if p.get("promoted_position")
    ]
    return issue_assembly.assemble_final(
        atoms=atoms, section_bodies=section_bodies, features=features,
    )


def _all_urls(text: str) -> set[str]:
    """Extract every URL referenced in the text — the cheapest
    high-signal way to confirm no link was dropped or mutated."""
    return set(re.findall(r"https?://[^\s)\"']+", text))


def _report(label: str, snapshot: str, rendered: str) -> None:
    snap_urls = _all_urls(snapshot)
    rend_urls = _all_urls(rendered)
    lost = snap_urls - rend_urls
    added = rend_urls - snap_urls
    print(f"\n=== {label} ===")
    print(f"  snapshot len:  {len(snapshot):>6} bytes / {len(snap_urls)} URLs")
    print(f"  rendered len:  {len(rendered):>6} bytes / {len(rend_urls)} URLs")
    if lost:
        print(f"  LOST URLs ({len(lost)}):")
        for u in sorted(lost):
            print(f"    - {u}")
    if added:
        print(f"  ADDED URLs ({len(added)}):")
        for u in sorted(added):
            print(f"    + {u}")
    if not lost and not added:
        print("  URL set: identical ✓")


def main() -> None:
    db.run_migrations()
    atoms = _atoms_from_snapshot()
    snap_draft = _read_snapshot("draft.md")
    snap_final = _read_snapshot("final.md")
    rend_draft = _render_draft_from_rows(atoms)
    rend_final = _render_final_from_rows(atoms)

    _report("draft.md", snap_draft, rend_draft)
    _report("final.md", snap_final, rend_final)

    # Save the re-renders for visual diffing.
    out_draft = REPO / "tmp" / "wt348-rendered-draft.md"
    out_final = REPO / "tmp" / "wt348-rendered-final.md"
    out_draft.write_text(rend_draft, encoding="utf-8")
    out_final.write_text(rend_final, encoding="utf-8")
    print(f"\nRe-renders written to:")
    print(f"  {out_draft}")
    print(f"  {out_final}")
    print(f"\nDiff with:")
    print(f"  diff {SNAPSHOT_DIR / 'draft.md'} {out_draft}")
    print(f"  diff {SNAPSHOT_DIR / 'final.md'} {out_final}")


if __name__ == "__main__":
    main()
