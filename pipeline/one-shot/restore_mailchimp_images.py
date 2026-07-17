"""Phase A: restore orphan image filenames in MailChimp-era issues.

Bodies imported from Mailchimp's plain-text rendering contain bare
image filenames (e.g. `b233f89660.jpg`) on lines of their own,
sometimes multiple per line. The HTML version of each Mailchimp
campaign has the real URLs — for issue #75 every bare filename
matches a full URL like `https://micro.thingelstad.com/uploads/2018/<same>`.

For each affected issue: load the cached Mailchimp HTML for that
campaign, build a `{filename: full_url}` map from every `<img src>`,
and substitute each bare filename with `![](full_url)` markdown.
Unresolvable filenames are logged and left alone.
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

# A line that consists of only hex-filename tokens separated by spaces/tabs.
# `[ \t]` (not `\s`) so we never consume the line-ending newline, which
# would collapse the blank line between this line and the following heading.
# Example lines seen in archive:
#   "b233f89660.jpg b75aeea229.jpg"
#   "d5f1c8a164.jpg"
ORPHAN_LINE_RE = re.compile(
    r"^(?P<tokens>(?:[a-f0-9]{6,}\.(?:jpg|jpeg|png|gif)[ \t]*)+)$",
    re.MULTILINE,
)
TOKEN_RE = re.compile(r"[a-f0-9]{6,}\.(?:jpg|jpeg|png|gif)")

HTML_IMG_RE = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)


def build_filename_map(html):
    """Return {filename: full_url} from every <img src> in the HTML."""
    m = {}
    for url in HTML_IMG_RE.findall(html):
        fn = url.rsplit("/", 1)[-1]
        # strip any query string
        fn = fn.split("?", 1)[0]
        if re.match(r"^[a-f0-9]{6,}\.(?:jpg|jpeg|png|gif)$", fn, re.IGNORECASE):
            # Preserve the first occurrence (closer to content top)
            m.setdefault(fn.lower(), url)
    return m


def process_file(fp, campaigns, issue_map, dry_run=False):
    """Return (changed:bool, resolved:int, unresolved_list)."""
    issue_num_str = fp.stem
    if not issue_num_str.isdigit():
        return False, 0, []
    issue_num = int(issue_num_str)
    if str(issue_num) not in issue_map:
        return False, 0, []

    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return False, 0, []
    fm = fm_match.group(1)
    body = fm_match.group(2)
    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$",
        body,
        re.DOTALL,
    )
    if not raw_match:
        return False, 0, []
    raw_open, inner, raw_close = raw_match.groups()

    # Are there any orphan filenames to resolve?
    if not ORPHAN_LINE_RE.search(inner):
        return False, 0, []

    campaign_id = issue_map[str(issue_num)]
    html = campaigns.get(campaign_id, {}).get("html", "")
    if not html:
        print(f"#{issue_num}: no Mailchimp HTML cached, skipping")
        return False, 0, []

    fn_map = build_filename_map(html)
    resolved = 0
    unresolved = []

    def repl(m):
        nonlocal resolved
        tokens = TOKEN_RE.findall(m.group("tokens"))
        out_lines = []
        for tok in tokens:
            url = fn_map.get(tok.lower())
            if url:
                out_lines.append(f"![]({url})")
                resolved += 1
            else:
                out_lines.append(tok)  # leave filename as-is
                unresolved.append(tok)
        return "\n\n".join(out_lines)

    new_inner = ORPHAN_LINE_RE.sub(repl, inner)
    if new_inner == inner:
        return False, 0, []

    new_body = raw_open + new_inner + raw_close
    new_content = fm + new_body
    if not dry_run:
        fp.write_text(new_content)
    return True, resolved, unresolved


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

    total_issues = 0
    total_resolved = 0
    total_unresolved = 0
    for fp in files:
        if not fp.exists():
            continue
        changed, resolved, unresolved = process_file(fp, campaigns, issue_map, dry_run=args.dry_run)
        if changed:
            total_issues += 1
            total_resolved += resolved
            total_unresolved += len(unresolved)
            note = ""
            if unresolved:
                sample = ", ".join(unresolved[:3])
                if len(unresolved) > 3:
                    sample += f", … (+{len(unresolved) - 3})"
                note = f"  UNRESOLVED: {sample}"
            action = "would restore" if args.dry_run else "restored"
            print(f"#{fp.stem}: {action} {resolved} (of {resolved + len(unresolved)}){note}")

    action = "Would modify" if args.dry_run else "Modified"
    print(
        f"\n{action} {total_issues} file(s). "
        f"{total_resolved} filenames resolved, "
        f"{total_unresolved} unresolved."
    )


if __name__ == "__main__":
    main()
