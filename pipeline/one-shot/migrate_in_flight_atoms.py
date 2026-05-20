#!/usr/bin/env python3
"""Migrate the in-flight issue's atom files to the ``atoms/`` subdir.

Step 2 of the workshop_bot pipeline refactor relocates author-content
atoms (intro.md / outro.md / cover.json / haiku.md / metadata.json /
thesis.md / cta-N.md / thanks-N.md) from ``weekly-thing/{N}/`` to
``weekly-thing/{N}/atoms/``. The s3 helpers dual-read (try atoms/
first, fall back to root) during the migration, so reads keep working
without backfill. This script copies the current in-flight issue's
atoms to the new location so the layout becomes canonical going
forward.

The legacy root copies are *not* deleted by this script — leave them
in place until step 6 of the refactor lands and we're sure nothing
falls back to root. Until then, dual-read makes both copies safe.

Usage:

    venv/bin/python pipeline/one-shot/migrate_in_flight_atoms.py [--issue N]

If ``--issue`` is omitted, the active issue from ``workshop.db`` is
migrated. Idempotent — re-runs only copy atoms that aren't already at
the new path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from apps.workshop_bot.tools import db, s3  # noqa: E402


def migrate(issue_number: int) -> dict:
    """Copy every atom file at the legacy root path to ``atoms/``.

    Returns ``{copied: [...], skipped_already_at_new: [...], missing: [...]}``
    for the caller to log.
    """
    bucket = s3._bucket()
    client = s3._client()

    listing = s3.list_issue(issue_number)
    seen = {obj["filename"] for obj in listing.get("objects", [])}

    copied: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []

    for atom_name in sorted(seen):
        if not s3._is_atom_name(atom_name):
            continue
        new_key = s3._resolve_key(issue_number, atom_name)
        legacy_key = s3._resolve_legacy_key(issue_number, atom_name)
        if new_key == legacy_key:
            continue
        # Already at new path? Check via HEAD (cheap).
        try:
            client.head_object(Bucket=bucket, Key=new_key)
            skipped.append(atom_name)
            continue
        except client.exceptions.ClientError:
            pass

        # Legacy copy present?
        try:
            client.head_object(Bucket=bucket, Key=legacy_key)
        except client.exceptions.ClientError:
            missing.append(atom_name)
            continue

        # Copy.
        client.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": legacy_key},
            Key=new_key,
        )
        copied.append(atom_name)

    return {"copied": copied, "skipped_already_at_new": skipped, "missing": missing}


def _active_issue_number() -> int:
    window = db.get_active_issue_window()
    if window is None:
        raise SystemExit(
            "No active issue window in workshop.db — pass --issue N explicitly."
        )
    return int(window["issue_number"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue", type=int, default=None,
        help="Issue number to migrate. Defaults to the active issue from workshop.db.",
    )
    args = parser.parse_args()

    n = args.issue if args.issue else _active_issue_number()
    print(f"Migrating atoms for issue #{n}...")
    result = migrate(n)
    if result["copied"]:
        print(f"  ✅ copied to atoms/: {', '.join(result['copied'])}")
    if result["skipped_already_at_new"]:
        print(
            f"  ↩️  already at new path: {', '.join(result['skipped_already_at_new'])}"
        )
    if result["missing"]:
        print(
            "  ⚠️  not present (skipped — write via the normal flow when ready): "
            f"{', '.join(result['missing'])}"
        )
    if not any(result.values()):
        print("  (nothing to do — no atom files present in this issue's workspace)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
