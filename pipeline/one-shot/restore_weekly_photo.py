"""Phase C: restore the "My Weekly Photo" image inside MailChimp-era
issue bodies.

Every MailChimp-era issue had an `<img>` under a `## My Weekly Photo 📷`
heading. The plain-text import kept the alt text (as a duplicated line)
but dropped the image itself. Result on the site: a caption with no
photo, and the alt text appearing twice.

For each of the 76 affected issues:
  1. Pull the first `<img>` that follows `My Weekly Photo` in the
     cached Mailchimp HTML. Capture both `alt` and `src`.
  2. In the archive body, find the heading. Inspect the first
     non-blank line after it.
  3. If that line matches the alt text (loosely — stripped, lowercased,
     with markdown link syntax reduced), treat it as a leftover image-
     alt duplicate and REPLACE it with `![alt](src)`.
  4. Otherwise, it's real commentary — INSERT `![alt](src)` before it
     so the image lands right after the heading and the commentary
     is preserved verbatim.

Unmatched issues (no img tag found near the heading, or no HTML cached)
are logged and skipped.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = ROOT / "apps" / "site" / "archive"
CAMPAIGNS_CACHE = ROOT / "cache" / "mailchimp_campaigns.json"
ISSUE_MAP_CACHE = ROOT / "cache" / "mailchimp_issue_map.json"

HEADING_RE = re.compile(r"^##\s+My Weekly Photo[^\n]*$", re.MULTILINE)
IMG_TAG_RE = re.compile(r"<img\s+[^>]*>", re.IGNORECASE)
SRC_ATTR_RE = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)
ALT_ATTR_RE = re.compile(r'alt=["\']([^"\']*)["\']', re.IGNORECASE)


def extract_photo(html):
    """Find the first <img> after 'My Weekly Photo' in HTML; return (alt, src)."""
    m = re.search(r"My Weekly Photo", html)
    if not m:
        return None, None
    segment = html[m.start() : m.start() + 5000]
    img_m = IMG_TAG_RE.search(segment)
    if not img_m:
        return None, None
    tag = img_m.group(0)
    src_m = SRC_ATTR_RE.search(tag)
    alt_m = ALT_ATTR_RE.search(tag)
    if not src_m:
        return None, None
    return (alt_m.group(1) if alt_m else "").strip(), src_m.group(1).strip()


def normalize(s):
    """Loose normalization for line<->alt comparison: strip, lowercase,
    collapse whitespace, remove common markdown link syntax so
    '[foo](bar)' and 'foo' compare equal."""
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # [text](url) -> text
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Drop trailing period/space for leniency
    return s.rstrip(". ")


def process_file(fp, campaigns, issue_map, dry_run=False):
    """Return a status string or None if nothing to do."""
    stem = fp.stem
    if not stem.isdigit():
        return None
    n = int(stem)
    if str(n) not in issue_map:
        return None

    content = fp.read_text()
    if "## My Weekly Photo" not in content:
        return None

    cid = issue_map[str(n)]
    html = campaigns.get(cid, {}).get("html", "")
    alt, src = extract_photo(html)
    if not src:
        return f"#{n}: no <img> found in HTML — skipped"

    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    body = fm_match.group(2)
    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$",
        body,
        re.DOTALL,
    )
    if not raw_match:
        return None
    raw_open, inner, raw_close = raw_match.groups()

    heading_m = HEADING_RE.search(inner)
    if not heading_m:
        return None

    # Inspect the region right after the heading
    after = inner[heading_m.end() :]
    # Pattern: \n+ followed by a non-blank line
    post_match = re.match(r"(\n+)([^\n]+)\n", after)
    if not post_match:
        return f"#{n}: heading has nothing after it — skipped"

    leading_blanks = post_match.group(1)
    first_line = post_match.group(2)
    img_markdown = f"![{alt}]({src})"

    if normalize(first_line) == normalize(alt) and alt:
        # Case A: first line is leftover alt duplicate — replace it.
        # Reconstruct: heading + original leading blanks + image + rest after this line
        rest = after[post_match.end() :]
        new_after = leading_blanks + img_markdown + "\n" + rest
        status = f"#{n}: replaced alt-duplicate with image"
    else:
        # Case B: first line is real commentary — insert image before it.
        new_after = leading_blanks + img_markdown + "\n\n" + after[len(leading_blanks) :]
        status = f"#{n}: inserted image before commentary"

    new_inner = inner[: heading_m.end()] + new_after
    if new_inner == inner:
        return f"#{n}: no change"

    if not dry_run:
        new_content = fm + raw_open + new_inner + raw_close
        fp.write_text(new_content)
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    campaigns = json.loads(CAMPAIGNS_CACHE.read_text())
    issue_map = json.loads(ISSUE_MAP_CACHE.read_text())

    if args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        files = sorted(ARCHIVE_DIR.glob("*.md"))

    results = []
    for fp in files:
        if not fp.exists():
            continue
        status = process_file(fp, campaigns, issue_map, dry_run=args.dry_run)
        if status:
            results.append(status)
            print(status)

    print(
        f"\n{'Would modify' if args.dry_run else 'Modified'} "
        f"{sum(1 for r in results if 'replaced' in r or 'inserted' in r)} "
        f"file(s); {sum(1 for r in results if 'skipped' in r or 'no change' in r)} skipped."
    )


if __name__ == "__main__":
    main()
