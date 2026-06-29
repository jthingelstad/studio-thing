"""Import a Drafts blog export (JSON) into the studio, routed by stage tag.

Each Drafts entry is routed by Jamie's own ``stage::*`` / ``wip`` tags:
- ``stage::draft`` / ``stage::edit`` / ``wip``  -> article production, phase ``draft``
- ``stage::outline``                            -> article production, phase ``outline``
- ``stage::seed`` + everything untagged         -> the seeds garden

His prose is preserved verbatim (relocated, never rewritten) — articles carry it
as ``body.md``; seeds carry it as the seed body. Idempotent: the Drafts ``uuid``
is recorded (seed ``source`` = ``drafts:{uuid}``; article ``details.drafts_uuid``)
so re-runs skip already-imported entries.

Usage (from the repo root):
    venv/bin/python -m apps.workshop_bot.scripts.import_drafts <export.json> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools import content_store, db  # noqa: E402


def _route(tags: list[str]) -> tuple[str, str | None]:
    """Return (destination, phase). destination ∈ {'article', 'seed'}."""
    t = set(tags or [])
    if "stage::draft" in t or "stage::edit" in t:
        return "article", "draft"
    if "stage::outline" in t:
        return "article", "outline"
    if "wip" in t:
        return "article", "draft"
    return "seed", None  # stage::seed + untagged


def _title(content: str) -> str:
    for line in content.splitlines():
        s = line.strip()
        if s:
            return s.lstrip("#").strip()[:80] or "(untitled)"
    return "(untitled)"


def _meaningful_tags(tags: list[str]) -> str:
    keep = [t for t in (tags or []) if t not in ("blog",)]
    return ", ".join(keep)


def run(path: str, *, dry_run: bool) -> dict:
    entries = json.loads(Path(path).expanduser().read_text())
    # Idempotency ledgers.
    seed_sources = {s.get("source") for s in db.seed_list(limit=100000)}
    article_uuids = set()
    for p in db.list_productions(production_type="article", limit=100000):
        det = p.get("details") or {}
        if isinstance(det, dict) and det.get("drafts_uuid"):
            article_uuids.add(det["drafts_uuid"])

    counts = {"article:draft": 0, "article:outline": 0, "seed": 0, "skipped": 0}
    samples: list[str] = []
    for e in entries:
        content = (e.get("content") or "").strip()
        uuid = e.get("uuid") or ""
        if not content:
            counts["skipped"] += 1
            continue
        dest, phase = _route(e.get("tags") or [])
        title = _title(content)
        if dest == "article":
            if uuid in article_uuids:
                counts["skipped"] += 1
                continue
            counts[f"article:{phase}"] += 1
            if len(samples) < 8:
                samples.append(f"  article/{phase:7} · {title[:64]}")
            if not dry_run:
                row = db.create_production(
                    production_type="article", title=title, phase=phase,
                    details={"drafts_uuid": uuid, "source": "drafts",
                             "tags": e.get("tags"), "created_at": e.get("created_at")},
                    created_by="import")
                content_store.set(row["id"], "body.md", content, by="import")
        else:
            src = f"drafts:{uuid}"
            if src in seed_sources:
                counts["skipped"] += 1
                continue
            counts["seed"] += 1
            if len(samples) < 8:
                samples.append(f"  seed           · {title[:64]}")
            if not dry_run:
                db.seed_add(content, title=title, source=src,
                            tags=_meaningful_tags(e.get("tags") or []) or None,
                            created_by="import")
    return {"counts": counts, "samples": samples, "total": len(entries), "dry_run": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser(description="Import a Drafts blog export, routed by stage tag.")
    ap.add_argument("path", help="Path to the Drafts export JSON.")
    ap.add_argument("--dry-run", action="store_true", help="Show the routing without writing.")
    args = ap.parse_args()
    db.run_migrations()
    r = run(args.path, dry_run=args.dry_run)
    c = r["counts"]
    print(f"Drafts import{' (DRY RUN — nothing written)' if r['dry_run'] else ''}: "
          f"{r['total']} entries")
    print(f"  articles (draft):   {c['article:draft']}")
    print(f"  articles (outline): {c['article:outline']}")
    print(f"  seeds:              {c['seed']}")
    print(f"  skipped (empty/already imported): {c['skipped']}")
    if r["samples"]:
        print("  sample routing:")
        print("\n".join(r["samples"]))


if __name__ == "__main__":
    main()
