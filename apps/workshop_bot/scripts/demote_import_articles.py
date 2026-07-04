"""Demote import-created article productions back to the seeds garden.

The Drafts blog-export import (``import_drafts.py``) routed ``stage::draft`` /
``stage::outline`` / ``wip`` entries into *article productions* — treating a
messy idea archive as real in-flight work. This reverses that call: each
import-created article becomes a **seed** (Jamie's verbatim prose as the seed
body, provenance preserved via ``source = drafts:{uuid}``), and the production
row is archived.

Idempotent both ways: seeds are keyed by the same ``drafts:{uuid}`` source the
importer uses (a re-run of *either* script skips already-present entries), and
already-archived productions are skipped here.

Usage (from the repo root):
    venv/bin/python -m apps.workshop_bot.scripts.demote_import_articles [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools import content_store, db  # noqa: E402


def run(*, dry_run: bool) -> dict:
    seed_sources = {s.get("source") for s in db.seed_list(limit=100000)}
    counts = {"demoted": 0, "seed_existed": 0, "skipped": 0}
    lines: list[str] = []
    for p in db.list_productions(production_type="article", limit=100000):
        det = p.get("details") or {}
        if p.get("created_by") != "import" or not isinstance(det, dict):
            counts["skipped"] += 1
            continue
        if p.get("status") != "active":
            counts["skipped"] += 1
            continue
        uuid = det.get("drafts_uuid") or ""
        src = f"drafts:{uuid}" if uuid else f"demoted:{p['id']}"
        body = content_store.get(p["id"], "body.md") or p["title"]
        if src in seed_sources:
            counts["seed_existed"] += 1
        else:
            counts["demoted"] += 1
            if not dry_run:
                db.seed_add(body, title=p["title"], source=src,
                            tags=det.get("tags") and ", ".join(
                                t for t in det["tags"] if t != "blog") or None,
                            created_by="demote")
        lines.append(f"  {p['id']:6} · {p['title'][:64]}")
        if not dry_run:
            db.update_production(p["id"], status="archived", updated_by="demote")
    return {"counts": counts, "lines": lines, "dry_run": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Demote import-created article productions to seeds.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be demoted without writing.")
    args = ap.parse_args()
    db.run_migrations()
    r = run(dry_run=args.dry_run)
    c = r["counts"]
    print(f"Demote import articles{' (DRY RUN — nothing written)' if r['dry_run'] else ''}:")
    print(f"  demoted to seeds:            {c['demoted']}")
    print(f"  seed already existed:        {c['seed_existed']}")
    print(f"  skipped (not import/active): {c['skipped']}")
    if r["lines"]:
        print("  productions archived:" if not r["dry_run"] else "  would archive:")
        print("\n".join(r["lines"]))


if __name__ == "__main__":
    main()
