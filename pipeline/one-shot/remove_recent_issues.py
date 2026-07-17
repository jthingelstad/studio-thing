"""Remove the "Recent Issues" section from archive .md files.

Strips:
  - the heading line (`### Recent Issues` or `## Recent Issues`)
  - all following blank and bullet lines up to the first non-bullet,
    non-blank line (the next structural element)
  - if the removed section was flanked by `---` dividers on both sides,
    also removes the preceding divider (so one divider remains between
    the neighbors, which is what the original layout intended).

Only edits bodies inside `{% raw %}...{% endraw %}`; never touches
front matter or markers.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

HEADING_RE = re.compile(r"^(#{2,3})\s+Recent Issues\s*$", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*-\s+\[", re.MULTILINE)


def remove_section(text):
    """Return (new_text, removed:bool).

    Surgical line-based removal. Cuts exactly one contiguous span so we
    never touch whitespace outside the section being removed.
    """
    lines = text.split("\n")

    heading_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^#{2,3}\s+Recent Issues\s*$", line):
            heading_idx = i
            break
    if heading_idx is None:
        return text, False

    # Walk forward: consume blank lines and bullet lines. Stop at first line
    # that is neither. Include trailing blanks so deletion lands on the NEXT
    # structural line (this keeps exactly one blank-line gap between neighbors).
    j = heading_idx + 1
    while j < len(lines):
        stripped = lines[j].strip()
        if stripped == "":
            j += 1
            continue
        if re.match(r"^\s*-\s+\[", lines[j]):
            j += 1
            continue
        break

    # Walk back from heading_idx to find the preceding non-blank line.
    pre_idx = heading_idx - 1
    while pre_idx >= 0 and lines[pre_idx].strip() == "":
        pre_idx -= 1
    preceded_by_divider = pre_idx >= 0 and lines[pre_idx].strip() == "---"

    # The next structural line is lines[j] (if j is in range).
    followed_by_divider = j < len(lines) and lines[j].strip() == "---"

    if preceded_by_divider and followed_by_divider:
        # Drop the preceding --- along with the heading + bullets.
        # Deletion range: [pre_idx, j). Keeps the trailing --- at j.
        del_start, del_end = pre_idx, j
    else:
        # Plain removal: just the heading + bullets + trailing blanks.
        del_start, del_end = heading_idx, j

    new_lines = lines[:del_start] + lines[del_end:]
    return "\n".join(new_lines), True


def process_file(fp, dry_run=False):
    """Process one archive .md: only modify the body inside {% raw %}...{% endraw %}."""
    content = fp.read_text()
    # Split front matter / body. Only operate inside the body.
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    body = fm_match.group(2)

    # Only operate inside {% raw %} ... {% endraw %}
    raw_match = re.match(r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL)
    if not raw_match:
        return False
    raw_open, inner, raw_close = raw_match.groups()

    new_inner, changed = remove_section(inner)
    if not changed:
        return False

    new_body = raw_open + new_inner + raw_close
    new_content = fm + new_body

    if dry_run:
        return True

    fp.write_text(new_content)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int, help="Issue numbers (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        files = sorted(ARCHIVE_DIR.glob("*.md"))

    changed = []
    for fp in files:
        if not fp.exists():
            continue
        if process_file(fp, dry_run=args.dry_run):
            changed.append(fp.stem)

    action = "Would modify" if args.dry_run else "Modified"
    print(f"{action} {len(changed)} file(s).")
    if changed:
        print("  First 10:", changed[:10])


if __name__ == "__main__":
    main()
