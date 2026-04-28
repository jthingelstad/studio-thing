"""Repair #106 — a one-off: the plain-text import flattened every
section heading (dropped the `##` prefix) and every editorial link
(turned `[Title](URL)` into `Title (URL)\ndomain`).

Two targeted transformations:

  1. Bare-heading lines (the canonical set of section names for this
     era) get a `## ` prefix.

  2. `Title (URL)\ndomain\n` triples become `### [Title](URL)\n`.
     The bare domain line is redundant with the URL and is dropped.

Nothing else is touched. Specifically: inline `text (url)` parenthetical
references in commentary are left alone — the target pattern there is
ambiguous with natural parenthetical writing and risks false positives.
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
FP = ROOT / "site" / "archive" / "106.md"

SECTION_HEADINGS = [
    "Featured Links 🏅",
    "Notable Links 📌",
    "Briefly",
    "Microposts 🎈",
    "My Weekly Photo 📷",
    "Fortune 🥠",
    "Give Back 🎁",
    "Promotion 🎁",
    "Thanks 🎬",
    "The end 🎬",
    "Highlighted iOS App 📱",
    "Featured App 📱",
    "Status 🎈",
    "Stream",
]


def main():
    content = FP.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    fm, body = fm_match.group(1), fm_match.group(2)
    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$",
        body, re.DOTALL)
    raw_open, inner, raw_close = raw_match.groups()

    before = inner

    # 1. Heading prefix
    headings_added = 0
    for h in SECTION_HEADINGS:
        pattern = rf"(?:^|\n)\n({re.escape(h)})\n\n"
        replacement = r"\n\n## \1\n\n"
        new_inner, n = re.subn(pattern, replacement, inner)
        if n:
            inner = new_inner
            headings_added += n

    # 2. Link block: `Title (https://url)\ndomain\n` → `### [Title](url)\n`.
    # The domain line has no leading whitespace and contains no parens or
    # slashes beyond its hostname. Keep it conservative: require the
    # pattern to appear as a standalone 2-line block, preceded and
    # followed by blank lines.
    #
    # Title can include arbitrary chars except a nested '(' at the point
    # where the URL starts.
    link_re = re.compile(
        r"(?m)^(?P<title>[^\n(]+?(?:\([^\n)]*\)[^\n(]*)*?) \((?P<url>https?://[^\s)]+)\)\n"
        r"(?P<domain>[a-zA-Z0-9][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,})\n"
    )

    links_converted = 0

    def link_repl(m):
        nonlocal links_converted
        links_converted += 1
        title = m.group("title").strip()
        url = m.group("url").strip()
        return f"### [{title}]({url})\n"

    inner = link_re.sub(link_repl, inner)

    if inner == before:
        print("#106: no changes made.")
        return

    print(f"#106: headings prefixed: {headings_added}, "
          f"link blocks converted: {links_converted}")

    new_content = fm + raw_open + inner + raw_close
    FP.write_text(new_content)


if __name__ == "__main__":
    main()
