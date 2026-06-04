"""Push the generated 11ty site inputs from Studio to the website repo.

Studio owns production: it builds ``apps/site/archive/{N}.md``, the
``apps/site/_data/*.json`` index files, and ``data/librarian/graph.json``, then
ships them to ``weekly.thingelstad.com``, which only renders. This is the
Phase-1 content handoff (see ``STUDIO_MIGRATION_PLAN.md`` /
``PHASE_1.md``). It reuses workshop_bot's ``github_repo.put_tree`` so the whole
set lands as one atomic, idempotent commit.

Default mode is a **dry run**: compare the generated files against the website
repo's current ``main`` tree and report what *would* change, committing nothing.
That is the Phase-1 verification gate — confirm the diff is empty/expected
before the cutover flips the push on.

Usage:
  python pipeline/deploy/push_site_inputs.py           # dry-run diff (default, safe)
  python pipeline/deploy/push_site_inputs.py --push     # actually commit to the website repo

Env:
  GITHUB_PAT_TOKEN   fine-grained PAT, Contents: write on the website repo
  GITHUB_REPO_NWO    target repo (default jthingelstad/weekly.thingelstad.com)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# github_repo lives in workshop_bot's tools; reuse it rather than re-implement
# the Git Data API dance. Candidate to promote into librarian_core later, since
# both the ship sequence and this handoff now depend on it.
sys.path.insert(0, str(REPO_ROOT / "apps" / "workshop_bot" / "tools"))
import github_repo  # noqa: E402

SITE = REPO_ROOT / "apps" / "site"
LIBRARIAN = REPO_ROOT / "data" / "librarian"


def collect_files() -> list[tuple[str, bytes]]:
    """Gather the generated site inputs as (repo-relative path, bytes)."""
    paths: list[Path] = sorted((SITE / "archive").glob("*.md"))
    for rel in ("_data/emails.json", "_data/stats.json", "_data/status.json"):
        p = SITE / rel
        if p.exists():
            paths.append(p)
    graph = LIBRARIAN / "graph.json"
    if graph.exists():
        paths.append(graph)
    return [(p.relative_to(REPO_ROOT).as_posix(), p.read_bytes()) for p in paths]


def remote_blob_shas(branch: str) -> dict[str, str]:
    """path -> blob sha for the website repo's current branch tree (one call)."""
    tree = github_repo._get(f"/git/trees/{branch}", {"recursive": "1"})
    return {e["path"]: e["sha"] for e in tree.get("tree", []) if e.get("type") == "blob"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--push", action="store_true",
                    help="Commit to the website repo. Default is a dry-run diff.")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    files = collect_files()
    if not files:
        print("No generated site inputs found — did the build steps run?", file=sys.stderr)
        return 1
    print(f"Collected {len(files)} generated files for {github_repo._repo()}.")

    if args.push:
        sha = github_repo.put_tree(files, "Refresh site inputs from Studio", branch=args.branch)
        print(f"Pushed @ {sha[:7]} on {args.branch} (no-op if nothing changed).")
        return 0

    # Dry run: diff generated files against the website repo's current tree.
    remote = remote_blob_shas(args.branch)
    added, changed, unchanged = [], [], 0
    for path, content in files:
        local = github_repo.git_blob_sha(content)
        rsha = remote.get(path)
        if rsha is None:
            added.append(path)
        elif rsha != local:
            changed.append(path)
        else:
            unchanged += 1

    print(f"DRY RUN vs {github_repo._repo()}@{args.branch}: "
          f"{len(added)} added, {len(changed)} changed, {unchanged} unchanged.")
    for p in added:
        print(f"  + {p}")
    for p in changed:
        print(f"  ~ {p}")
    if not added and not changed:
        print("Clean — Studio reproduces the website repo's current inputs exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
