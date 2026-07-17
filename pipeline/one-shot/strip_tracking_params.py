"""Strip MailChimp tracking query params from every URL in archive bodies.

Targets `mc_cid` and `mc_eid` — the MailChimp campaign-id / email-id
tracking pair that leaked into links when I copied URLs from forwarded
MailChimp issues in the Tinyletter/MailChimp era (~10 affected issues).

Operates on the body inside `{% raw %}...{% endraw %}` only. Front
matter `url` / `heading_context` / `domains` fields are derived from
body extraction, so after the body is clean and resynced to Buttondown,
the next pipeline run (`pipeline/content/build_data.py`) will rewrite the front
matter from the clean source.
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

STRIP_PARAMS = {"mc_cid", "mc_eid"}

# Match URL up to the first whitespace / markdown-end / HTML-end delimiter.
URL_RE = re.compile(r"https?://[^\s<>)\]\"'}]+")


def clean_url(url):
    """Return url with STRIP_PARAMS removed from its query string."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k not in STRIP_PARAMS]
    if len(kept) == len(pairs):
        return url
    new_query = urlencode(kept)
    return urlunparse(parsed._replace(query=new_query))


def clean_text(text):
    """Replace every URL in text with its tracking-params-stripped form.
    Returns (new_text, count_of_urls_cleaned)."""
    cleaned_count = 0

    def repl(m):
        nonlocal cleaned_count
        original = m.group(0)
        cleaned = clean_url(original)
        if cleaned != original:
            cleaned_count += 1
        return cleaned

    new_text = URL_RE.sub(repl, text)
    return new_text, cleaned_count


def process_file(fp, dry_run=False):
    content = fp.read_text()
    fm_match = re.match(r"^(---\n.+?\n---\n)(.*)$", content, re.DOTALL)
    if not fm_match:
        return 0
    fm = fm_match.group(1)
    body = fm_match.group(2)

    raw_match = re.match(
        r"^(\{%\s*raw\s*%\}\n)(.*?)(\n\{%\s*endraw\s*%\}\n?)$", body, re.DOTALL
    )
    if not raw_match:
        return 0
    raw_open, inner, raw_close = raw_match.groups()

    new_inner, n = clean_text(inner)
    if n == 0:
        return 0

    new_body = raw_open + new_inner + raw_close
    new_content = fm + new_body
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

    total_urls = 0
    total_files = 0
    for fp in files:
        if not fp.exists():
            continue
        n = process_file(fp, dry_run=args.dry_run)
        if n:
            total_files += 1
            total_urls += n
            print(f"#{fp.stem}: cleaned {n} URL{'s' if n != 1 else ''}")

    action = "Would modify" if args.dry_run else "Modified"
    print(f"\n{action} {total_files} file(s), {total_urls} URLs total.")


if __name__ == "__main__":
    main()
