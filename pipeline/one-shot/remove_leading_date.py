"""Remove the Tinyletter-era leading date stamp and location dateline
from early issue bodies.

Issues #3–#22 began the body with a date line like `May 27, 2017`,
sometimes followed by one or two location lines like `Minneapolis, MN`
or `Home`. Both are redundant platform artifacts from the old
newsletter template. Strip both.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "site" / "archive"

DATE_RE = re.compile(
    r"^(?P<date>"
    r"(?:#\d+\s*/\s*)?"  # optional "#N / " prefix (used in #60–#69)
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"\s+\d{1,2},?\s+\d{4})\s*\n+",
)

# Location dateline: a short line (≤60 chars, no markdown) that either
# ends in a 2-letter uppercase state/region code (optionally preceded
# by a comma and Unicode LRM U+200E) or is the bare word "Home".
LOCATION_RE = re.compile(
    r"^(?P<loc>"
    r"(?:Home|Cabin)"  # bare "Home" or "Cabin"
    r"|[^\n\[\]]{1,60}[\u200e]?,?[\u200e]?\s+[A-Z]{2}[\u200e]?"  # "… MN" or "…, MN"
    r")\s*\n+"
)


def process_file(fp, dry_run=False):
    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL
    )
    if not raw_match:
        return None
    raw_open, inner, raw_close = raw_match.groups()

    ec = re.match(r"^(<!--\s*buttondown-editor-mode:[^>]*-->\n*)", inner)
    if not ec:
        return None
    comment = ec.group(1)
    after = inner[ec.end():]

    removed = []
    # Strip the date if present.
    m = DATE_RE.match(after)
    if m:
        removed.append(m.group("date"))
        after = after[m.end():]
    # Strip up to 2 location lines that follow.
    for _ in range(2):
        m = LOCATION_RE.match(after)
        if not m:
            break
        removed.append(m.group("loc").strip("\u200e "))
        after = after[m.end():]

    if not removed:
        return None
    new_inner = comment + after
    new_content = fm + raw_open + new_inner + raw_close
    if not dry_run:
        fp.write_text(new_content)
    return removed


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
        removed = process_file(fp, dry_run=args.dry_run)
        if removed:
            changed.append((fp.stem, removed))
            print(f"#{fp.stem}: removed {removed!r}")

    action = "Would modify" if args.dry_run else "Modified"
    print(f"\n{action} {len(changed)} file(s).")


if __name__ == "__main__":
    main()
