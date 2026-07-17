"""Remove the trailing "About" section from archive .md bodies.

The About section was a rotating canned bio + a list of profile links,
always appearing as the last section of the body, preceded by a `---`
divider. Removes the divider + heading + everything through end of body.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

HEADING_RE = re.compile(r"^(#{2,3})\s+About\s*$", re.MULTILINE)


def remove_about_tail(text):
    """Return (new_text, removed:bool). Cuts from the `---` divider
    preceding `## About` through end of text. If no preceding divider,
    cuts from the heading itself."""
    m = HEADING_RE.search(text)
    if not m:
        return text, False

    lines = text[: m.start()].rstrip("\n").split("\n")

    # Walk back from heading: skip blank lines, then expect a `---` divider.
    k = len(lines) - 1
    while k >= 0 and lines[k].strip() == "":
        k -= 1
    if k >= 0 and lines[k].strip() == "---":
        # Cut from this divider (inclusive) onward.
        cut_at_line = k
    else:
        # No preceding divider — fall back to cutting from the heading itself.
        # Find character position of the heading start and use that.
        new_text = text[: m.start()].rstrip("\n") + "\n"
        return new_text, True

    # Reconstruct up to (but excluding) lines[cut_at_line].
    kept = "\n".join(lines[:cut_at_line]).rstrip("\n")
    if kept:
        kept += "\n"
    return kept, True


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

    new_inner, changed = remove_about_tail(inner)
    if not changed:
        return False

    # Strip any trailing newlines on new_inner so raw_close (which starts with \n) lands cleanly.
    new_inner = new_inner.rstrip("\n")
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
