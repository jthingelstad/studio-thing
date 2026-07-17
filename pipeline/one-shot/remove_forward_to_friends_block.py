"""Remove "forward this email / tell your friends" share-CTA blocks.

Present in 9 MailChimp/early-Buttondown-era issues (#131, #142, #146,
#156, #163, #164, #165, #167, #168), these are short prompts inserted
between two `---` separators asking readers to share the newsletter.
Openers vary ("Like this email?", "Thank you for reading!", "Your
friends already read this?", "Want smarter friends?", "Know someone
who'd like this?", etc.) so detection is done by content signature
rather than lead-in phrase:

  - `mailto:?subject=Check%20out%20The%20Weekly%20Thing…` (share link)
  - `[sign up here]` (older, mailto-less variant in #131/#142/#146/#156)

Strategy: split the body on `---` separators (flexible whitespace),
drop each block that matches a signature, and rejoin with a single
`---` — so each removed block leaves behind one `---` as a clean
section break, not zero and not two.

Follows the same frontmatter + `{% raw %}…{% endraw %}` parsing as
pipeline/one-shot/remove_share_block.py.
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

SEPARATOR_RE = re.compile(r"(\n+---\n+)")
NORMALIZED_SEP = "\n\n---\n\n"

CTA_SIGNATURES = (
    # The share link's subject line is distinctive enough on its own;
    # allow for mailto target variants including a typo'd `jamie@` in #163.
    "subject=Check%20out%20The%20Weekly%20Thing",
    # Older share variant in #131/#142/#146/#156 uses no mailto at all,
    # just a `[sign up here]` link inside a **Like this email?** block.
    "[sign up here]",
)


def is_cta_block(content: str) -> bool:
    return any(sig in content for sig in CTA_SIGNATURES)


def strip_cta_blocks(body: str) -> tuple[str, list[str]]:
    """Remove CTA blocks bracketed by `---` separators.

    Returns (new_body, removed_previews) where removed_previews is a
    list of short snippets of what was removed (for logging).
    """
    parts = SEPARATOR_RE.split(body)
    # After re.split with a capturing group:
    #   even indices = content blocks
    #   odd indices  = `---` separators

    cta_indices = [i for i in range(0, len(parts), 2) if is_cta_block(parts[i])]
    if not cta_indices:
        return body, []

    keep = [True] * len(parts)
    previews: list[str] = []
    for idx in cta_indices:
        keep[idx] = False
        previews.append(parts[idx].strip().splitlines()[0][:80] if parts[idx].strip() else "")
        # Drop exactly one adjacent separator so the net result is a
        # single `---` between the surviving neighbors.
        if idx + 1 < len(parts):
            keep[idx + 1] = False
        elif idx - 1 >= 0:
            keep[idx - 1] = False

    kept = [p for i, p in enumerate(parts) if keep[i]]
    return "".join(kept), previews


def process_file(fp: Path, dry_run: bool = False) -> list[str] | None:
    content = fp.read_text(encoding="utf-8")
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL)
    if raw_match:
        raw_open, inner, raw_close = raw_match.groups()
    else:
        raw_open, raw_close = "", ""
        inner = body

    new_inner, previews = strip_cta_blocks(inner)
    if not previews:
        return None

    new_content = fm + raw_open + new_inner + raw_close
    if not dry_run:
        fp.write_text(new_content, encoding="utf-8")
    return previews


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int, help="Issue numbers (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        files = sorted(ARCHIVE_DIR.glob("*.md"))

    changed: list[tuple[str, list[str]]] = []
    for fp in files:
        if not fp.exists():
            continue
        previews = process_file(fp, dry_run=args.dry_run)
        if previews:
            changed.append((fp.stem, previews))
            for p in previews:
                print(f"#{fp.stem}: removed — {p}")

    action = "Would modify" if args.dry_run else "Modified"
    total_blocks = sum(len(p) for _, p in changed)
    print(f"\n{action} {len(changed)} file(s), removed {total_blocks} block(s).")


if __name__ == "__main__":
    main()
