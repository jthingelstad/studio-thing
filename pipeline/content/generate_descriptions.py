"""Generate literal meta descriptions for archive issues using Claude.

For each targeted issue:
  1. Pull the editorial link titles from front matter. Prefer the "main"
     sections (Notable, Featured, Must Read). Fall back to the full set
     (adding Briefly, Recommended Links, FYI) if fewer than 3 main links.
  2. Call Claude Sonnet 4.6 with a strict literal-extraction prompt and
     prompt caching on the system prompt (so the 300-issue batch pays
     the system-prompt token cost once).
  3. Print the generated description with character count.
  4. If --write, update the front matter's `description:` field in place.

Does NOT push to Buttondown; that's the sync script's job.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"

MAIN_SECTIONS = {
    "Notable", "Featured", "Must Read",
    "Notable Links 📌", "Featured Links 🏅", "Links 📌",
}
ALL_EDITORIAL_SECTIONS = MAIN_SECTIONS | {
    "Briefly", "Recommended Links", "FYI", "Yet More Links 🍞",
}

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You write meta descriptions for issues of the Weekly Thing, a newsletter by Jamie Thingelstad. Each description appears as (a) a subtitle on the web archive, (b) og:description and other meta tags, and (c) the preheader in email clients — rendered right next to the subject line, so avoid repeating subject-line topics verbatim when possible.

Input: a list of article titles from the issue's Notable, Featured, and Must Read sections.

Output: a single line — a comma-separated list of concrete topics drawn directly from those titles.

Length — this is the most important rule:
- Target 130 to 150 characters. Absolute maximum: 160. If in doubt, stop earlier.
- Typical output: 6 to 8 comma-separated items. Pick the most specific and newsworthy; drop the rest.
- Each item should be 2–5 words. Prefer concise forms of longer titles (drop "The", "Is", subtitles after colons or em dashes, author names).

Content rules:
- Use words and short phrases lifted verbatim from the titles. Do NOT invent synonyms, summaries, themes, or commentary.
- Prefer named things: products, technologies, people, specific ideas that appear in the titles.
- No sentences. No verbs or connecting phrases like "covers", "explores", "featuring".
- No intro or prefix like "This issue:", "Including:", "Topics:".
- No emoji, no hashtags, no quotation marks, no brackets.
- End with a single period.

Return only the description text — no explanation, no preamble."""


RETRY_PROMPT = """Your previous response was {over} characters over the 160 limit ({length} chars total). Remove the least-specific items from the list so the result is 130–150 characters. Same rules apply. Return only the new description text."""


BODY_SYSTEM_PROMPT = """\
You write meta descriptions for issues of the Weekly Thing, a newsletter by Jamie Thingelstad. This is a themed essay or journal issue — not a link roundup — so the description must capture what the issue is ABOUT, drawn from the body text.

Input: the body text of one issue.

Output: a single line — a comma-separated list of concrete topics lifted directly from the body.

Length — most important rule:
- Target 130 to 150 characters. Absolute maximum: 160.
- Typical output: 5 to 8 comma-separated items.

Content rules:
- Use words and short phrases lifted verbatim from the body. Do NOT invent synonyms, summaries, themes, or commentary.
- Prefer named things that appear in the body: specific places, people, events, trips, projects.
- No sentences. No verbs or connecting phrases.
- No intro or prefix. No emoji, hashtags, quotation marks, brackets.
- End with a single period.

Return only the description text."""


def load_links(fp):
    """Return (subject, main_titles, all_titles) for an issue."""
    c = fp.read_text()
    m = re.match(r"^---\n(.+?)\n---\n", c, re.DOTALL)
    if not m:
        return None, [], []
    fm = yaml.safe_load(m.group(1))
    subject = fm.get("subject", "")
    links = fm.get("links") or []
    main = [l["text"] for l in links if l.get("section") in MAIN_SECTIONS and l.get("text")]
    allx = [l["text"] for l in links if l.get("section") in ALL_EDITORIAL_SECTIONS and l.get("text")]
    return subject, main, allx


INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
OWN_DOMAINS = {"thingelstad.com", "weekly.thingelstad.com", "buttondown.com",
               "buttondown.email", "micro.thingelstad.com"}


def extract_inline_link_titles(fp, limit=20):
    """Fallback: pull inline markdown link titles from the body. Used for
    early pre-structured issues where the pipeline found no editorial
    sections. Filters out utility/own-domain links."""
    c = fp.read_text()
    fm_m = re.match(r"^---\n.+?\n---\n", c, re.DOTALL)
    body = c[fm_m.end():]
    raw = re.match(r"^\{%\s*raw\s*%\}\n(.*?)\n\{%\s*endraw\s*%\}\n?$", body, re.DOTALL)
    inner = raw.group(1) if raw else body
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.DOTALL)

    titles = []
    seen_urls = set()
    for title, url in INLINE_LINK_RE.findall(inner):
        url = url.strip()
        title = title.strip()
        if not url or not title:
            continue
        if url.startswith(("mailto:", "#", "{{", "cid:")):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        # Skip own-site / micro.blog / Buttondown links
        low = url.lower()
        if any(dom in low for dom in OWN_DOMAINS):
            continue
        # Skip links whose visible text is a date/timestamp (journal micropost format)
        if re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+@\s+", title):
            continue
        titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def extract_body_text(fp, limit_chars=4000):
    """Return cleaned body text for body-fallback mode. Strips Buttondown
    template cruft, editor comments, HTML, subscribe/share boilerplate."""
    c = fp.read_text()
    fm_m = re.match(r"^---\n.+?\n---\n", c, re.DOTALL)
    body = c[fm_m.end():]
    raw = re.match(r"^\{%\s*raw\s*%\}\n(.*?)\n\{%\s*endraw\s*%\}\n?$", body, re.DOTALL)
    inner = raw.group(1) if raw else body
    # Strip editor comment
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.DOTALL)
    # Strip Buttondown template tags and {% %} blocks
    inner = re.sub(r"\{\{[^}]*\}\}", "", inner)
    inner = re.sub(r"\{%[^%]*%\}", "", inner)
    # Strip HTML tags
    inner = re.sub(r"<[^>]+>", "", inner)
    # Strip image markdown
    inner = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", inner)
    # Collapse whitespace
    inner = re.sub(r"\n{3,}", "\n\n", inner).strip()
    return inner[:limit_chars]


def pick_titles(main, allx, min_main=3, force_all=False):
    """Choose which title set to feed the model. Returns (titles, source_tag).
    If force_all is set, always prefer the broader all-editorial set when it
    has more titles than main — useful for re-running issues whose main-only
    set was too small to produce a 110+ char description."""
    if force_all and len(allx) > len(main):
        return allx, "all-editorial"
    if len(main) >= min_main:
        return main, "main"
    if len(allx) >= min_main:
        return allx, "all-editorial"
    return allx, "sparse"


def generate(client, titles, max_retries=2, source="titles"):
    """Call Claude with the prompt; return the description text (stripped).
    Retries up to `max_retries` times if the result exceeds 160 chars."""
    if source == "body":
        system = BODY_SYSTEM_PROMPT
        user = "Body:\n" + titles  # titles is the body text for body mode
    else:
        system = SYSTEM_PROMPT
        user = "Titles:\n" + "\n".join(f"- {t}" for t in titles)
    messages = [{"role": "user", "content": user}]

    for attempt in range(max_retries + 1):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )
        text = resp.content[0].text.strip()
        if len(text) <= 160:
            return text
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": RETRY_PROMPT.format(
                over=len(text) - 160, length=len(text))},
        ]
    return text


def update_description(fp, new_desc):
    """Replace the `description:` line in front matter with new_desc.
    Uses YAML to re-serialize just the description field to keep quoting
    correct, but preserves everything else byte-exact."""
    content = fp.read_text()
    m = re.match(r"^(---\n)(.+?)(\n---\n)(.*)$", content, re.DOTALL)
    fm_text = m.group(2)
    # Replace only the description line; YAML-quote if needed.
    # Use yaml.dump on just {'description': new_desc} to get proper escaping,
    # then extract its serialized form.
    serialized = yaml.dump({"description": new_desc}, default_flow_style=False,
                           allow_unicode=True, width=2000).rstrip("\n")
    # serialized is like: "description: '...'" or "description: ..."
    new_fm = re.sub(r"^description:.*$", serialized, fm_text, count=1, flags=re.MULTILINE)
    if new_fm == fm_text:
        raise RuntimeError(f"description line not found in {fp.name}")
    fp.write_text(m.group(1) + new_fm + m.group(3) + m.group(4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int, help="Issue numbers")
    ap.add_argument("--write", action="store_true", help="Write new descriptions to front matter")
    ap.add_argument("--all-empty", action="store_true", help="Operate on every issue (ignore issue args)")
    ap.add_argument("--inline-fallback", action="store_true",
                    help="For issues with no editorial-section links, extract inline markdown links from the body instead")
    ap.add_argument("--body-fallback", action="store_true",
                    help="For themed-essay issues, generate from body text instead of link titles")
    ap.add_argument("--force-all", action="store_true",
                    help="Prefer all-editorial titles over main-only when all has more entries (for re-running short outputs)")
    args = ap.parse_args()

    client = Anthropic()

    if args.all_empty:
        files = sorted(ARCHIVE_DIR.glob("*.md"))
    elif args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        print("Provide issue numbers or --all-empty")
        return

    for fp in files:
        if not fp.exists() or not fp.stem.isdigit():
            continue
        subject, main, allx = load_links(fp)
        titles, source = pick_titles(main, allx, force_all=args.force_all)
        if not titles and args.inline_fallback:
            inline = extract_inline_link_titles(fp)
            if len(inline) >= 3:
                titles = inline
                source = "inline-fallback"
        body_mode = False
        if not titles and args.body_fallback:
            body_text = extract_body_text(fp)
            if body_text:
                titles = body_text
                source = "body-fallback"
                body_mode = True
        if not titles:
            print(f"#{fp.stem}: SKIP — no editorial link titles found.")
            continue

        desc = generate(client, titles, source="body" if body_mode else "titles")
        cc = len(desc)
        flag = "OK" if 110 <= cc <= 160 else "OUT_OF_RANGE"
        print(f"\n#{fp.stem} [{source}, {len(titles)} titles]  {cc} chars [{flag}]")
        print(f"  subject: {subject}")
        print(f"  desc:    {desc}")

        if args.write:
            update_description(fp, desc)
            print(f"  -> written to {fp.name}")


if __name__ == "__main__":
    main()
