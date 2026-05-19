"""One-shot migration: data/buttondown/ → data/issues/{N}/{archive.md, metadata.json, links.json}.

After this runs, every existing issue has a canonical home under data/issues/
so the website build can switch off the Buttondown U-turn. The script is the
read-side equivalent of pipeline/content/content.py:build_from_snapshots — same
transform (archive_body_from_issue + process_emails.extract_links) — but it
writes to data/issues/ instead of apps/site/archive/.

archive.md carries the full editorial-facing front matter (the same fields
write_archive_md emits today, minus the 11ty-build artifacts layout / permalink
/ tags / audio_*). The new build path reads this file and adds those 11ty
fields back to produce a byte-identical apps/site/archive/{N}.md.

metadata.json mirrors the shape workshop_bot writes in its S3 workspace
(number, buttondown_id, subject, slug, description, image, publish_date,
absolute_url) — useful for symmetry with workshop output and for non-markdown
consumers (status report, etc.).

links.json carries the structured link extraction (notable_links, briefly_links,
domains, word_count) — JSON-friendly for downstream consumers like the corpus
chunker.

Idempotent: re-runs produce the same files. Pass --issue N to migrate just one
issue, or --all (default) for the whole manifest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "content"))
sys.stdout.reconfigure(line_buffering=True)

import content  # noqa: E402 — sibling pipeline module
import process_emails  # noqa: E402

ISSUES_ROOT = REPO / "data" / "issues"

# Defensive strip: pre-Workshop bodies shouldn't carry these markers, but a few
# late-2025 issues that went through early workshop iterations might. Cleaning
# them here is cheap insurance.
MEMBERSHIP_MARKER_RE = re.compile(r"\n?<!--\s*(cta|thanks):\d+\s*-->\n?")

# Fields that go into archive.md's front matter (mirrors write_archive_md but
# without layout/permalink/tags — those are 11ty-build concerns added by the
# new content.py build read path).
ARCHIVE_FRONTMATTER_FIELDS = [
    "buttondown_id",
    "number",
    "subject",
    "publish_date",
    "slug",
    "description",
    "image",
    "absolute_url",
    "domains",
    "links",
    "word_count",
]

# metadata.json mirrors workshop_bot's compose-meta + send-to-buttondown shape.
METADATA_FIELDS = [
    "number",
    "buttondown_id",
    "subject",
    "slug",
    "description",
    "image",
    "publish_date",
    "absolute_url",
]


def strip_membership_markers(body: str) -> str:
    return MEMBERSHIP_MARKER_RE.sub("\n", body)


def issue_dir(number) -> Path:
    return ISSUES_ROOT / str(number)


def build_archive_frontmatter(issue: dict) -> dict:
    """Same field order as write_archive_md so YAML serialization matches."""
    return {
        "buttondown_id": issue["id"],
        "number": issue["number"],
        "subject": issue["subject"],
        "publish_date": issue["publish_date"],
        "slug": issue["slug"],
        "description": issue["description"],
        "image": issue["image"],
        "absolute_url": issue["absolute_url"],
        "domains": issue["domains"],
        "links": issue["links"],
        "word_count": issue.get("word_count", 0),
    }


def build_metadata_json(issue: dict) -> dict:
    return {
        "number": issue["number"],
        "buttondown_id": issue["id"],
        "subject": issue["subject"],
        "slug": issue["slug"],
        "description": issue["description"],
        "image": issue["image"],
        "publish_date": issue["publish_date"],
        "absolute_url": issue["absolute_url"],
    }


def build_links_json(issue: dict) -> dict:
    return {
        "notable_links": issue.get("notable_links", []),
        "briefly_links": issue.get("briefly_links", []),
        "domains": issue["domains"],
        "word_count": issue.get("word_count", 0),
    }


def write_archive_md(out_dir: Path, frontmatter: dict, body: str) -> None:
    fm_str = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    content_str = f"---\n{fm_str}---\n{body}\n"
    (out_dir / "archive.md").write_text(content_str, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def migrate_one(snapshot: dict) -> None:
    """Build the issue dict the same way content.py:issue_from_snapshot does,
    then write the three files."""
    issue = content.issue_from_snapshot(snapshot)
    # Re-strip membership markers on the rendered body (post-Liquid).
    issue["body"] = strip_membership_markers(issue["body"])

    out_dir = issue_dir(issue["number"])
    out_dir.mkdir(parents=True, exist_ok=True)

    write_archive_md(out_dir, build_archive_frontmatter(issue), issue["body"])
    write_json(out_dir / "metadata.json", build_metadata_json(issue))
    write_json(out_dir / "links.json", build_links_json(issue))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="Migrate every issue (default)")
    group.add_argument("--issue", help="Migrate a single issue number")
    args = parser.parse_args()

    snapshots = content.load_snapshots()
    if not snapshots:
        raise SystemExit("No Buttondown snapshots found in data/buttondown/emails/")

    if args.issue:
        target = str(args.issue)
        snapshots = [s for s in snapshots if str(s["number"]) == target]
        if not snapshots:
            raise SystemExit(f"No snapshot found for issue {args.issue}")

    ISSUES_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"Migrating {len(snapshots)} issue(s) → data/issues/")
    for snapshot in snapshots:
        migrate_one(snapshot)
        print(f"  #{snapshot['number']} ✓")

    print(f"Done. Wrote {len(snapshots)} issue dir(s) under {ISSUES_ROOT}.")


if __name__ == "__main__":
    main()
