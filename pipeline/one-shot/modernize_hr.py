"""Modernize the `**\\n<60 hyphens>` section-divider pattern to `---`.

Appears in Tinyletter/early-MailChimp era issues (#32–#41, #46) as an
artifact of the old email templates. Replace with the standard markdown
horizontal rule `---` so it renders as an HR and stays consistent with
the rest of the archive.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

# The exact fingerprint: ** on its own, newline, then ≥5 hyphens (the old
# template used 60), optional trailing newlines. Always replace with a
# clean `---` markdown HR surrounded by blank lines.
HR_PATTERN = re.compile(r"\*\*\n[-]{5,}\n*")


def process_file(fp, dry_run=False):
    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return 0
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL
    )
    if not raw_match:
        return 0
    raw_open, inner, raw_close = raw_match.groups()

    new_inner, n = HR_PATTERN.subn("---\n\n", inner)
    if n == 0:
        return 0

    new_body = raw_open + new_inner + raw_close
    new_content = fm + new_body

    if dry_run:
        return n

    fp.write_text(new_content)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        files = sorted(ARCHIVE_DIR.glob("*.md"))

    total_reps = 0
    total_files = 0
    for fp in files:
        if not fp.exists():
            continue
        reps = process_file(fp, dry_run=args.dry_run)
        if reps:
            total_files += 1
            total_reps += reps
            action = "would modify" if args.dry_run else "modified"
            print(f"#{fp.stem}: {action} ({reps} replacement{'s' if reps != 1 else ''})")

    print(f"\n{'Would modify' if args.dry_run else 'Modified'} {total_files} file(s), "
          f"{total_reps} total replacements.")


if __name__ == "__main__":
    main()
