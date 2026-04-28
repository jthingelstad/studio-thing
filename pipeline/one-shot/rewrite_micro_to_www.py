"""Rewrite `micro.thingelstad.com` → `www.thingelstad.com` in archive
bodies (and any other URL references). Both scheme variants (http and
https) are normalized to `https://www.thingelstad.com`.

Jamie's micro.blog redirects to the main site; replacing the hostname
pins every reference to the canonical domain. Verified that both the
`/uploads/...` image paths and the `/YYYY/MM/DD/slug.html` post paths
serve at www.thingelstad.com.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "site" / "archive"

# Matches both https://micro and http://micro. Captures nothing — we
# replace the whole prefix with the canonical form.
MICRO_RE = re.compile(r"https?://micro\.thingelstad\.com")
REPLACEMENT = "https://www.thingelstad.com"


def process_file(fp, dry_run=False):
    content = fp.read_text()
    new_content, n = MICRO_RE.subn(REPLACEMENT, content)
    if n == 0:
        return 0
    if not dry_run:
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

    total_files = 0
    total_urls = 0
    for fp in files:
        if not fp.exists():
            continue
        n = process_file(fp, dry_run=args.dry_run)
        if n:
            total_files += 1
            total_urls += n
            print(f"#{fp.stem}: {n} URL{'s' if n != 1 else ''}")

    print(f"\n{'Would rewrite' if args.dry_run else 'Rewrote'} "
          f"{total_urls} URL(s) in {total_files} file(s).")


if __name__ == "__main__":
    main()
