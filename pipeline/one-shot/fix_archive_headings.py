#!/usr/bin/env python3
"""
Demote in-body H1 section headings to H2 for issues that use `# Section`
section titles. These five issues (#132–#136) use H1 for section titles
like "Must Read", "Currently", etc. — breaking the TOC (which only
captures H2/H3) and visual hierarchy (H1 is reserved for the page title).

Only processes lines matching ^# text at the start (standard markdown H1),
and only in the body portion (after YAML front matter).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = REPO_ROOT / "apps" / "site" / "archive"
ISSUES = [132, 133, 134, 135, 136]

FRONTMATTER_RE = re.compile(r"^(---\n.*?\n---\n)", re.S)
# Section-title H1: plain text after `# ` (no markdown link brackets).
H1_SECTION_RE = re.compile(r"^# ([^#\[\n].*)$", re.M)
# Link-title H2: `## [Title](url)` — these sit under the section H1/H2.
H2_LINK_RE = re.compile(r"^## (\[)", re.M)


def main() -> None:
    for num in ISSUES:
        path = ARCHIVE / f"{num}.md"
        text = path.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(text)
        if not m:
            print(f"[#{num}] no front matter, skipping", flush=True)
            continue
        fm = m.group(1)
        body = text[m.end():]

        # Step 1: demote link-title H2 → H3 FIRST (before H1 demotion
        # creates new H2s that would be mis-matched).
        body, link_count = H2_LINK_RE.subn(r"### \1", body)
        # Step 2: demote section H1 → H2.
        body, section_count = H1_SECTION_RE.subn(r"## \1", body)

        if link_count == 0 and section_count == 0:
            print(f"[#{num}] no matching headings, skipping", flush=True)
            continue

        path.write_text(fm + body, encoding="utf-8")
        print(
            f"[#{num}] demoted {section_count} section H1→H2, "
            f"{link_count} link H2→H3",
            flush=True,
        )


if __name__ == "__main__":
    main()
