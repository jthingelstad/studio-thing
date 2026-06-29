"""Import a directory of idea-snippet text files into the seeds garden.

Jamie has ~150 text files (a sentence to an outline each) of things he might
write. This walks a directory of .txt/.md files and inserts each as a seed, so
Eddy can curate/cluster/connect them. Idempotent on re-run via the file path
recorded in `source` (skips already-imported files).

Usage (from the repo root):
    venv/bin/python -m apps.workshop_bot.scripts.import_seeds /path/to/ideas
    venv/bin/python -m apps.workshop_bot.scripts.import_seeds /path/to/ideas --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tools import db  # noqa: E402

_EXTS = {".txt", ".md", ".markdown", ".text"}


def _existing_sources() -> set[str]:
    return {s.get("source", "") for s in db.seed_list(limit=100000)}


def import_dir(directory: str, *, dry_run: bool = False) -> dict:
    root = Path(directory).expanduser()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _EXTS)
    existing = _existing_sources()
    imported, skipped = 0, 0
    for p in files:
        src = f"import:{p}"
        if src in existing:
            skipped += 1
            continue
        body = p.read_text(errors="replace").strip()
        if not body:
            skipped += 1
            continue
        # First non-empty line (sans markdown heading marks) as the title.
        first = next((ln.strip().lstrip("#").strip() for ln in body.splitlines() if ln.strip()), "")
        title = first[:80] if first else p.stem
        if dry_run:
            imported += 1
            continue
        db.seed_add(body, title=title, source=src, created_by="import")
        imported += 1
    return {"files": len(files), "imported": imported, "skipped": skipped, "dry_run": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser(description="Import idea snippets into the seeds garden.")
    ap.add_argument("directory", help="Directory of .txt/.md idea files.")
    ap.add_argument("--dry-run", action="store_true", help="Count without writing.")
    args = ap.parse_args()
    db.run_migrations()
    result = import_dir(args.directory, dry_run=args.dry_run)
    print(f"seeds import: {result['imported']} imported, {result['skipped']} skipped "
          f"of {result['files']} files{' (dry-run)' if result['dry_run'] else ''}.")


if __name__ == "__main__":
    main()
