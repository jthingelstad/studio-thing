"""Remove template/AI-generated intro paragraphs from archive .md bodies.

The Weekly Thing used several families of pre-issue intro blurbs:

  1. A set of ~15 rotating hand-written "Hi, I'm Jamie Thingelstad..."
     templates, and their minor one-off variants (range #131-#262).
  2. ChatGPT-generated number-themed welcomes (#263-#271).
  3. Procedural stats headers like "Weekly Thing 280 with eighteen links
     and twelve journal entries..." (selected issues #274-#292).

All appear immediately after the `<!-- buttondown-editor-mode -->` comment
and are followed by `\\n\\n---\\n\\n`, after which the real body begins.

The exact opener texts to remove are stored in `pipeline/one-shot/intro_openers.txt`,
separated by `<<<NEXT>>>` lines. The script only removes an opener if the
extracted text matches one of those strings *exactly* — so it is fully
idempotent and safe to re-run, and new variants can be added just by
appending to the data file.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = ROOT / "site" / "archive"
OPENERS_FILE = Path(__file__).parent / "intro_openers.txt"

EDITOR_COMMENT_RE = re.compile(r"^<!--\s*buttondown-editor-mode:[^>]*-->")


def load_openers():
    """Return the set of opener texts to remove, loaded from the data file."""
    if not OPENERS_FILE.exists():
        print(f"ERROR: {OPENERS_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    text = OPENERS_FILE.read_text()
    openers = [o.strip() for o in text.split("\n<<<NEXT>>>\n")]
    return {o for o in openers if o}


def remove_intro(inner, openers):
    """If inner starts with editor-comment + <one of `openers`> + `\\n\\n---\\n\\n`,
    strip the opener + divider. Returns (new_inner, changed:bool)."""
    m = EDITOR_COMMENT_RE.match(inner)
    if not m:
        return inner, False
    comment_end = m.end()
    after = inner[comment_end:]
    div_match = re.search(r"\n\n---\n\n", after)
    if not div_match:
        return inner, False
    opener = after[: div_match.start()].strip()
    if opener not in openers:
        return inner, False
    rest = after[div_match.end():]
    return inner[:comment_end] + rest, True


def process_file(fp, openers, dry_run=False):
    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL
    )
    if not raw_match:
        return False
    raw_open, inner, raw_close = raw_match.groups()

    new_inner, changed = remove_intro(inner, openers)
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

    openers = load_openers()
    print(f"Loaded {len(openers)} opener texts from {OPENERS_FILE.name}.")

    if args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        files = sorted(ARCHIVE_DIR.glob("*.md"))

    changed = []
    for fp in files:
        if not fp.exists():
            continue
        if process_file(fp, openers, dry_run=args.dry_run):
            changed.append(fp.stem)

    action = "Would modify" if args.dry_run else "Modified"
    print(f"{action} {len(changed)} file(s).")
    if changed:
        print(f"  First 10: {changed[:10]}")


if __name__ == "__main__":
    main()
