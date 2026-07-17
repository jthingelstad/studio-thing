"""Remove the trailing "Here are some other things you can do…" CTA block.

Present at the bottom of issues #299–#310, following the fortune +
subscriber-conditional. The block is a bulleted list asking readers
to share, post, join the forum, etc. — email-only CTA with template
tags like `{{ email.subject }}` and `{{ email_url }}` that don't
belong in the archive.

Tail cut: find the "Here are some other things…" line and remove
from there through end-of-body.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

# Match the heading line + immediately following bullet lines + any
# interleaved/trailing blank lines. Stop at the first line that is not
# blank and not a bullet — that's the next structural element (a
# `{% else %}` / `{% endif %}` template tag, or end-of-body, etc.).
BLOCK_RE = re.compile(
    r"\n+Here are some other things you can do[^\n]*\n"  # heading line
    r"(?:\n|-\s[^\n]*\n)+",  # bullets + blanks
    re.MULTILINE,
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

    # Replace with a single blank line so adjacent structural elements
    # (e.g., `{% endif %}` followed by `{% else %}`) keep a clean break.
    new_inner, n = BLOCK_RE.subn("\n\n", inner)
    if n == 0:
        return False
    if n > 1:
        print(f"  WARNING {fp.name}: matched {n} times (expected 1)")
        return False

    new_inner = new_inner.rstrip("\n")
    new_body = raw_open + new_inner + raw_close
    new_content = fm + new_body
    if not dry_run:
        fp.write_text(new_content)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int)
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
            print(f"#{fp.stem}: removed CTA block")

    action = "Would modify" if args.dry_run else "Modified"
    print(f"\n{action} {len(changed)} file(s).")


if __name__ == "__main__":
    main()
