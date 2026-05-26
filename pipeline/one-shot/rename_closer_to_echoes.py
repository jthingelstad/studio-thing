"""One-shot migration: rename `closer.md` → `echoes.md` in the
workshop_bot per-issue layout (S3 + local repo mirror).

The reader-facing section heading was always `## Echoes`; the on-disk
filename had stayed `closer.md` for legacy reasons. T2.2 of the drift
audit cleaned that up: composer writes go to `atoms/echoes.md`,
renderers read echoes.md with a closer.md fallback. This script
finishes the rename by moving every existing `closer.md` to its new
home so we can eventually drop the fallback code.

What it does
============

For each issue prefix under `s3://files.thingelstad.com/weekly-thing/`:

- If `weekly-thing/{N}/atoms/closer.md` exists → copy to
  `atoms/echoes.md`, then delete `atoms/closer.md`.
- If `weekly-thing/{N}/closer.md` exists (legacy, before the atoms/
  layout) → copy to `atoms/echoes.md`, then delete the root copy.
- Same for `data/issues/{N}/closer.md` in the local repo: rename to
  `data/issues/{N}/echoes.md`.

Idempotent: re-running after a successful pass is a no-op (nothing
named closer.md exists anywhere).

Usage
=====

    venv/bin/python pipeline/one-shot/rename_closer_to_echoes.py --dry-run
    venv/bin/python pipeline/one-shot/rename_closer_to_echoes.py --apply

The dry-run path prints what would change but writes nothing. `--apply`
executes the moves. The script never deletes a `closer.md` whose
contents weren't successfully written to the new echoes.md key first.

After this runs successfully, the `closer.md` fallback paths in
`apps/workshop_bot/tools/renderers.py:_read_echoes_atom`,
`apps/workshop_bot/jobs/compose_echoes.py:_prior_closers`,
`apps/workshop_bot/jobs/publish_card.py:gather_state`, and
`apps/workshop_bot/jobs/publish.py:_collect_ship_files` can be
dropped in a follow-up commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

BUCKET = "files.thingelstad.com"
PREFIX = "weekly-thing"
LOCAL_ISSUES_ROOT = REPO / "data" / "issues"


def _list_issue_numbers_on_s3(client) -> list[int]:
    """List every issue number with a per-issue prefix on S3 (whether or
    not it has a closer.md). Uses the standard delimiter trick to
    enumerate one level of sub-prefixes."""
    out: list[int] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{PREFIX}/", Delimiter="/"):
        for cp in page.get("CommonPrefixes", []) or []:
            # cp["Prefix"] looks like "weekly-thing/348/"
            stem = cp["Prefix"].rstrip("/").rsplit("/", 1)[-1]
            try:
                out.append(int(stem))
            except ValueError:
                continue
    return sorted(out)


def _s3_key_exists(client, key: str) -> bool:
    try:
        client.head_object(Bucket=BUCKET, Key=key)
        return True
    except client.exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _s3_rename(client, *, src: str, dst: str, dry_run: bool) -> None:
    """Copy src → dst, then delete src. No-op if src doesn't exist.
    Refuses to overwrite an existing dst — surfaces that for review."""
    if not _s3_key_exists(client, src):
        return
    if _s3_key_exists(client, dst):
        print(f"  ⚠️ skip: {src} → {dst} (dst already exists; manual review)")
        return
    print(f"  s3: {src} → {dst}")
    if dry_run:
        return
    client.copy_object(
        Bucket=BUCKET,
        Key=dst,
        CopySource={"Bucket": BUCKET, "Key": src},
        MetadataDirective="COPY",
    )
    client.delete_object(Bucket=BUCKET, Key=src)


def _local_rename(*, src: Path, dst: Path, dry_run: bool) -> None:
    if not src.exists():
        return
    if dst.exists():
        print(f"  ⚠️ skip: {src} → {dst} (dst already exists; manual review)")
        return
    print(f"  local: {src} → {dst}")
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Actually move files. Without this, the script only prints.")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Print the moves that would happen and exit (default).")
    args = ap.parse_args()
    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — no files will be changed. Re-run with --apply to commit.\n")

    import boto3
    client = boto3.client("s3")

    issue_numbers = _list_issue_numbers_on_s3(client)
    print(f"Found {len(issue_numbers)} issue prefixes on S3.\n")

    moves = 0
    for n in issue_numbers:
        # S3: try both legacy locations for closer.md and rename to atoms/echoes.md.
        atoms_closer = f"{PREFIX}/{n}/atoms/closer.md"
        root_closer = f"{PREFIX}/{n}/closer.md"
        atoms_echoes = f"{PREFIX}/{n}/atoms/echoes.md"
        for src in (atoms_closer, root_closer):
            if _s3_key_exists(client, src):
                _s3_rename(client, src=src, dst=atoms_echoes, dry_run=dry_run)
                moves += 1
                break  # only one source should exist

        # Local: data/issues/{N}/closer.md → data/issues/{N}/echoes.md
        local_closer = LOCAL_ISSUES_ROOT / str(n) / "closer.md"
        local_echoes = LOCAL_ISSUES_ROOT / str(n) / "echoes.md"
        if local_closer.exists():
            _local_rename(src=local_closer, dst=local_echoes, dry_run=dry_run)
            moves += 1

    print(f"\n{moves} rename(s) {'would be applied' if dry_run else 'completed'}.")
    if dry_run and moves:
        print("Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
