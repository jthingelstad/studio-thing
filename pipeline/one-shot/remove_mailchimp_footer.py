"""Remove the MailChimp-era bottom-of-body footer cruft.

Two variants observed:

Pattern A (#42–#52): simple footer
    ## Thanks 🎬

    Thank you for subscribing to the Weekly Thing! If you know of people
    that would like the Weekly Thing please forward it along!

    Unsubscribe (*|UNSUB|*) *|EMAIL|* from this list.

Pattern B (#106): everything after `🎈🎈🎈` — a mix of subscriber-management
boilerplate, CC license note, and MailChimp merge tags. Jamie confirmed
to cut at the balloon separator.

Both patterns appear at the very end of the inner body (just before
`{% endraw %}`). Removal is a tail cut — delete from the first match
through end-of-body.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

# Pattern A: find the last `## Thanks 🎬` in the file and cut from there.
# The section's contents are always short (a thank-you + unsubscribe line)
# and always at end-of-body, so tail-cutting from the heading is safe.
FOOTER_A = re.compile(
    r"\n##\s+Thanks\s+🎬\s*\n.*?Unsubscribe\s*\(\*\|UNSUB\|\*\)\s*\*\|EMAIL\|\*\s*from this list\.\s*\Z",
    re.DOTALL,
)

# Pattern B: find a line of consecutive balloon emojis (2 or more) and
# cut from there to end-of-body. Tightened to ≥2 balloons so we never
# match a single 🎈 that appears inside a section heading like
# `## Microposts 🎈` (which the earlier runs confirmed never matched
# anyway, since balloons in headings don't start a new line).
FOOTER_B = re.compile(r"\n+🎈{2,}\s*\n.*\Z", re.DOTALL)


def process_file(fp, dry_run=False):
    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL)
    if not raw_match:
        return None
    raw_open, inner, raw_close = raw_match.groups()

    # Try Pattern B first (balloon separator) — only affects #106
    new_inner, nb = FOOTER_B.subn("", inner)
    variant = None
    if nb:
        variant = "B"
    else:
        new_inner, na = FOOTER_A.subn("", inner)
        if na:
            variant = "A"
    if not variant:
        return None

    # Re-strip trailing whitespace so raw_close (which starts with \n) lands cleanly
    new_inner = new_inner.rstrip("\n")
    new_body = raw_open + new_inner + raw_close
    new_content = fm + new_body
    if not dry_run:
        fp.write_text(new_content)
    return variant


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
        v = process_file(fp, dry_run=args.dry_run)
        if v:
            changed.append((fp.stem, v))
            print(f"#{fp.stem}: variant {v}")

    action = "Would modify" if args.dry_run else "Modified"
    print(f"\n{action} {len(changed)} file(s).")


if __name__ == "__main__":
    main()
