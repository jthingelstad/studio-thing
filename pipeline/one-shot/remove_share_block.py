"""Remove the "Want to share this issue" share-link block from archive bodies.

Present at the bottom of recent issues (#309–#344) in three shapes:

  1. `The URL is…` + dashed-border div + `{{ email_url }}` + `</div>` (#309–#312)
  2. `The link is…` + dashed-border div + `{{ email_url }}` + `</div>` (#313–#343)
  3. `The link is…` text only, no div (#344)

Removes just the share block (text + div if present) and the trailing
blank line, leaving any following content ("Here are some other things
you can do…", 👨‍💻, etc.) exactly where it was.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

# Full share block: text line, blank, div (5 lines), blank.
# The div portion is optional for the text-only variant (#344).
SHARE_BLOCK_RE = re.compile(
    r"Want to share this issue with others\? The (?:link|URL) is…\n"
    r"(?:\n<div style=\"border: 2px dashed;[^\"]*\">\n"
    r"\{\{ email_url \}\}\n"
    r"</div>\n)?"
    r"\n"
)


def process_file(fp, dry_run=False):
    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL)
    if not raw_match:
        return False
    raw_open, inner, raw_close = raw_match.groups()

    new_inner, n = SHARE_BLOCK_RE.subn("", inner)
    if n == 0:
        return False
    if n > 1:
        print(f"  WARNING {fp.name}: matched {n} times (expected 1); skipping.")
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
        print(f"  First 10: {changed[:10]}")


if __name__ == "__main__":
    main()
