"""Remove the MailChimp-era top-of-body header block.

Two variants observed:

Pattern A (#42–#52):
    Weekly Newsletter from
    Jamie Thingelstad

    #42 | Feb 24, 2018 | Permalink (*|ARCHIVE|*)

Pattern B (#106):
    View this email in your browser (*|ARCHIVE|*)


    https://weekly.thingelstad.com/

    Weekly Newsletter from
    Jamie Thingelstad

    Issue #106 / May 18, 2019

Both are pure platform artifacts — the issue number, date, and archive
URL are all in front matter. Remove entirely, keeping the editor-mode
comment and the real content that follows.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

HEADER_A = re.compile(
    r"^(?:##\s+Weekly Thing\s*\n+)?"  # optional "## Weekly Thing" heading (#53–#58)
    r"Weekly Newsletter from\n"
    r"Jamie Thingelstad\n"
    r"\n"
    r"#\d+\s*[|•]\s*[^|•\n]+[|•]\s*Permalink\s*\(\*\|ARCHIVE\|\*\)\n"
    r"\n+"
)

HEADER_B = re.compile(
    r"^View this email in your browser\s*\(\*\|ARCHIVE\|\*\)\n+"
    r"https://weekly\.thingelstad\.com/?\n+"
    r"Weekly Newsletter from\n"
    r"Jamie Thingelstad\n"
    r"\n+"
    r"Issue\s+#\d+\s*/\s*[^\n]+\n"
    r"\n+"
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

    # Must have an editor-mode comment at the very start
    ec = re.match(r"^(<!--\s*buttondown-editor-mode:[^>]*-->)", inner)
    if not ec:
        return None
    comment = ec.group(1)
    after = inner[ec.end():]

    new_after, nb = HEADER_B.subn("", after, count=1)
    variant = None
    if nb:
        variant = "B"
    else:
        new_after, na = HEADER_A.subn("", after, count=1)
        if na:
            variant = "A"
    if not variant:
        return None

    new_inner = comment + new_after
    new_content = fm + raw_open + new_inner + raw_close
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
