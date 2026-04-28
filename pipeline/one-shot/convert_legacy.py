"""One-time conversion of legacy newsletter issues from HTML/MailChimp plaintext to clean markdown.

Three format eras:
  - TinyLetter HTML (issues 1, 3-22): well-structured HTML with <h2>, <h3><a>, <p>, <img>
  - MailChimp old (issues 23-52): ** Section\\n---- headers, ** Title (url)\\n---- articles
  - MailChimp new (issues 53-130): plain section names, Title (url)\\ndomain.com articles
  - Issue 2 and 131+ are already clean markdown — skipped.

Usage:
  python pipeline/one-shot/convert_legacy.py                # Convert all legacy issues
  python pipeline/one-shot/convert_legacy.py --issue 30     # Convert a single issue
  python pipeline/one-shot/convert_legacy.py --dry-run      # Preview without writing
"""

import html
import re
import sys
from pathlib import Path

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "site" / "archive"

# Issues that are already markdown and should be skipped
SKIP_ISSUES = {2}  # Issue 2 is an early markdown experiment


def parse_md_file(path):
    """Parse a .md file into (front_matter_raw, body).

    Returns the raw YAML string (preserving formatting) and the body text
    between {% raw %} and {% endraw %}.
    """
    text = path.read_text()

    # Split at the second --- to get front matter
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None, None
    front_matter_raw = parts[1]
    remainder = parts[2]

    # Extract body between {% raw %} and {% endraw %}
    raw_match = re.search(r"\{% raw %\}\n(.*?)\n\{% endraw %\}", remainder, re.DOTALL)
    if not raw_match:
        return front_matter_raw, None
    body = raw_match.group(1)

    return front_matter_raw, body


# Profile headshot URL fragment — not a real featured image for any issue
PROFILE_PHOTO_ID = "cb692d4b-a464-4126-aaac-e352b7edd7a5"


def write_md_file(path, front_matter_raw, body):
    """Write the .md file back with the converted body."""
    # Clear the image field if it's just Jamie's profile headshot
    if PROFILE_PHOTO_ID in front_matter_raw:
        front_matter_raw = re.sub(
            r"^image: .*" + re.escape(PROFILE_PHOTO_ID) + r".*$",
            "image: ''",
            front_matter_raw,
            flags=re.MULTILINE,
        )
    content = f"---\n{front_matter_raw}---\n{{% raw %}}\n{body}\n{{% endraw %}}\n"
    path.write_text(content)


def detect_format(body, issue_number):
    """Detect which format era this issue belongs to."""
    if issue_number in SKIP_ISSUES:
        return "skip"
    if issue_number >= 131:
        return "skip"
    if '<div class="message-body">' in body or (
        "<h2>" in body and "<h3>" in body and issue_number <= 22
    ):
        return "tinyletter"
    if "*|MC_PREVIEW_TEXT|*" in body and "** " in body:
        return "mailchimp_old"
    if "** " in body and "----" in body and issue_number <= 52:
        return "mailchimp_old"
    # Everything else in the 23-130 range is mailchimp_new
    return "mailchimp_new"


# ---------------------------------------------------------------------------
# TinyLetter HTML converter
# ---------------------------------------------------------------------------

def convert_tinyletter(body):
    """Convert TinyLetter HTML to clean markdown."""
    # Strip the editor mode comment and wrapper div
    body = re.sub(r"<!-- buttondown-editor-mode: plaintext -->", "", body)
    body = re.sub(r'<div class="message-body">\s*', "", body)
    body = re.sub(r"\s*</div>\s*$", "", body)
    body = re.sub(r"<!-- Section break -->", "", body)

    # Remove the boilerplate header (Weekly Thing title + date + headshot)
    body = re.sub(r"<h1>\s*Weekly Thing\s*</h1>", "", body)

    # Remove the profile headshot image (round, float-right photo of Jamie)
    body = re.sub(r"<img[^>]*border-top-left-radius:\s*50%[^>]*/?>", "", body)

    # Convert images (before other tag conversions)
    # Extract src from <img> tags, strip all other attributes
    def convert_img(m):
        tag = m.group(0)
        src_match = re.search(r'src="([^"]+)"', tag)
        if not src_match:
            return ""
        src = html.unescape(src_match.group(1))
        return f"![image]({src})"

    body = re.sub(r"<img[^>]+/?>", convert_img, body)

    # Convert linked images: <a href="url"><img...></a> patterns are already handled
    # since img was converted first

    # Mark article excerpts BEFORE converting headings — <p><em> after </h3>
    # are article quotes (→ blockquote), all others are just italic captions.
    body = re.sub(
        r"(</h3>\s*)<p>\s*<em>(.*?)</em>\s*</p>",
        lambda m: m.group(1) + "<BLOCKQUOTE>" + m.group(2) + "</BLOCKQUOTE>",
        body,
        flags=re.DOTALL,
    )

    # Convert headings with links: <h3><a href="url">text</a></h3>
    body = re.sub(
        r"<h3>\s*<a\s+href=\"([^\"]+)\"[^>]*>(.*?)</a>\s*</h3>",
        lambda m: f"### [{html.unescape(m.group(2).strip())}]({html.unescape(m.group(1))})",
        body,
    )

    # Convert plain headings
    body = re.sub(r"<h1[^>]*>(.*?)</h1>", lambda m: f"# {m.group(1).strip()}", body)
    body = re.sub(
        r"<h2[^>]*>(.*?)</h2>", lambda m: f"## {m.group(1).strip()}", body
    )
    body = re.sub(
        r"<h3[^>]*>(.*?)</h3>", lambda m: f"### {m.group(1).strip()}", body
    )

    # Convert links: <a href="url" ...>text</a>
    def convert_link(m):
        url = html.unescape(m.group(1))
        url = url.replace("jthingelstad.micro.blog", "www.thingelstad.com")
        url = url.replace("micro.thingelstad.com", "www.thingelstad.com")
        text = m.group(2).strip()
        if text in ("→", ""):
            return f"[→]({url})"
        if text.startswith("!["):
            return f"[{text}]({url})"
        return f"[{html.unescape(text)}]({url})"

    body = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', convert_link, body)

    # Now convert the marked blockquotes
    def convert_marked_quote(m):
        inner = m.group(1)
        inner = re.sub(r"<br\s*/?>", " ", inner)
        inner = re.sub(r"\s*\n\s*", " ", inner)
        inner = inner.strip()
        return f"\n> {inner}\n" if inner else ""

    body = re.sub(r"<BLOCKQUOTE>(.*?)</BLOCKQUOTE>", convert_marked_quote, body, flags=re.DOTALL)

    # Convert commentary: <p>💬 text</p> → plain text (drop the emoji convention)
    body = re.sub(
        r"<p>\s*💬\s*(.*?)\s*</p>",
        lambda m: f"\n{m.group(1).strip()}\n",
        body,
        flags=re.DOTALL,
    )

    # Convert remaining emphasis (inline, not full-paragraph quotes)
    def convert_em(m):
        inner = m.group(1)
        inner = re.sub(r"<br\s*/?>", " ", inner)
        inner = re.sub(r"\s*\n\s*", " ", inner)
        inner = inner.strip()
        if not inner:
            return ""
        return f"*{inner}*"

    body = re.sub(r"<em>(.*?)</em>", convert_em, body, flags=re.DOTALL)
    body = re.sub(r"<strong>(.*?)</strong>", r"**\1**", body, flags=re.DOTALL)

    # Convert blockquotes
    body = re.sub(
        r"<blockquote>\s*(.*?)\s*</blockquote>",
        lambda m: "\n".join(f"> {line}" for line in m.group(1).strip().split("\n")),
        body,
        flags=re.DOTALL,
    )

    # Convert list items
    body = re.sub(r"<ul>\s*", "", body)
    body = re.sub(r"\s*</ul>", "", body)
    body = re.sub(r"<li>(.*?)</li>", lambda m: f"- {m.group(1).strip()}", body)

    # Convert paragraphs — unwrap <p> tags
    body = re.sub(r"<p>(.*?)</p>", lambda m: f"\n{m.group(1).strip()}\n", body, flags=re.DOTALL)

    # Convert line breaks
    body = re.sub(r"<br\s*/?>", "\n", body)

    # Strip any remaining HTML tags
    body = re.sub(r"<[^>]+>", "", body)

    # Decode HTML entities
    body = html.unescape(body)

    # Clean up whitespace
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = body.strip()

    return body


# ---------------------------------------------------------------------------
# MailChimp Old format converter (issues 23-52)
# ---------------------------------------------------------------------------

def convert_mailchimp_old(body):
    """Convert MailChimp old format (** Section\\n---- headers) to markdown."""
    body = re.sub(r"<!-- buttondown-editor-mode: plaintext -->", "", body)

    lines = body.split("\n")
    result = []
    i = 0

    # Strip header boilerplate
    header_done = False
    while i < len(lines):
        line = lines[i].strip()
        # Skip merge tags and boilerplate at the top
        if not header_done:
            if line.startswith("*|") or line == "" or line.startswith("View this email"):
                i += 1
                continue
            if line == "** Weekly Thing" or line == "** by Jamie Thingelstad":
                i += 1
                # Skip the ---- line after it
                if i < len(lines) and "----" in lines[i]:
                    i += 1
                continue
            # Date line (e.g., "December 2, 2017" or "October 14, 2017")
            if re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$", line):
                i += 1
                continue
            # Issue number line like "#30 | Dec 2, 2017 | Permalink (*|ARCHIVE|*)"
            if re.match(r"^#\d+\s*\|", line):
                i += 1
                continue
            header_done = True
        break

    # Process remaining lines
    in_microblog = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check for footer markers — stop processing
        if stripped.startswith("============"):
            break
        if stripped == "🎈🎈🎈":
            break
        if "*|FORWARD|*" in stripped:
            break
        if "Copyright ©" in stripped or "*|CURRENT_YEAR|*" in stripped:
            break
        if "*|IF:REWARDS|*" in stripped:
            break
        if "Want to change how you receive these emails?" in stripped:
            break

        # Strip remaining merge tags
        if "*|" in stripped and stripped.startswith("*|"):
            i += 1
            continue

        # ** Section or Article header
        if stripped.startswith("** "):
            title_text = stripped[3:].strip()

            # Check if next line is a ---- divider
            is_header = i + 1 < len(lines) and "----" in lines[i + 1]

            if is_header:
                # Skip the ---- line
                i += 2

                # Check if this is an article with URL: ** Title (url)
                url_match = re.match(r"^(.*?)\s*\((https?://[^\s)]+)\)\s*$", title_text)
                if url_match:
                    title = url_match.group(1).strip()
                    url = url_match.group(2)
                    result.append(f"### [{title}]({url})")
                    result.append("")
                else:
                    # It's a section heading
                    result.append(f"## {title_text}")
                    result.append("")
                    in_microblog = "microblog" in title_text.lower() or "microposts" in title_text.lower()
                continue

        # Bare URL on its own line (not in a paragraph)
        if re.match(r"^https?://\S+$", stripped):
            # Check if it's a standalone URL (like an image or link) — keep it
            result.append(stripped)
            i += 1
            continue

        # Bullet items: * text (url)
        if stripped.startswith("* "):
            item_text = stripped[2:]
            item_text = convert_bullet_item(item_text, in_microblog)
            result.append(f"- {item_text}")
            i += 1
            continue

        # Regular line — convert inline links and strip 💬 prefix
        if stripped.startswith("💬"):
            stripped = stripped.lstrip("💬").strip()
        converted = convert_inline_links(stripped) if stripped else ""
        result.append(converted)
        i += 1

    body = "\n".join(result)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


# ---------------------------------------------------------------------------
# MailChimp New format converter (issues 53-130)
# ---------------------------------------------------------------------------

# Known section names (with emoji) that should become ## headings
KNOWN_SECTIONS = [
    "Featured Links 🏅",
    "Featured Link 🏅",
    "Notable Links 📌",
    "Notable 📌",
    "My Weekly Photo 📷",
    "Photo 📷",
    "Photog 📷",
    "Yet More Links 🍞",
    "More Links 🍞",
    "Microposts 🎈",
    "Microblog updates 🎈",
    "Fortune 🥠",
    "Give Back 🎁",
    "Promotion 🎁",
    "Blog posts 📬",
    "Blog 📬",
    "Links 📌",
    "Featured App 📱",
    "The end 🎬",
    "Thanks 🎬",
    "Currently 📺",
    "Currently",
    "Straw Poll 🎯",
    "Straw Poll",
    "Reply All 📧",
    "Signature 🎨",
    "Local 📍",
    "Status Updates 📡",
]


def convert_mailchimp_new(body):
    """Convert MailChimp new format (issues 53-130) to markdown."""
    body = re.sub(r"<!-- buttondown-editor-mode: plaintext -->", "", body)

    lines = body.split("\n")
    result = []
    i = 0

    # Strip header boilerplate
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("View this email") or "*|ARCHIVE|*" in stripped:
            i += 1
            continue
        if stripped == "https://weekly.thingelstad.com/":
            i += 1
            continue
        if stripped == "Weekly Newsletter from" or stripped == "Jamie Thingelstad":
            i += 1
            continue
        if re.match(r"^Issue #\d+\s*/", stripped):
            i += 1
            continue
        if stripped.startswith("*|") and stripped.endswith("|*"):
            i += 1
            continue
        if stripped == "":
            i += 1
            continue
        # First real content line — stop stripping
        break

    # Process remaining lines
    in_microblog = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Footer detection
        if stripped == "🎈🎈🎈":
            break
        if "You received this email at" in stripped:
            break
        if stripped.startswith("Unsubscribe (*|UNSUB|*)"):
            break
        if "*|IF:REWARDS|*" in stripped:
            break
        if "*|LIST:ADDRESS|*" in stripped:
            break
        if "Want to change how you receive these emails?" in stripped:
            break
        if "Copyright ©" in stripped:
            break

        # Strip any stray merge tags
        if re.match(r"^\*\|[A-Z_:]+\|\*$", stripped):
            i += 1
            continue

        # Check for known section names — must come before article title detection
        is_section = False
        for section_name in KNOWN_SECTIONS:
            # Match exactly or with trailing whitespace, or the name without emoji
            section_base = section_name.split()[0] if " " in section_name else section_name
            if stripped == section_name or stripped.rstrip() == section_name.rstrip():
                result.append(f"## {stripped}")
                result.append("")
                is_section = True
                break
            # Also match if the line is just the section name (case-insensitive, ignoring trailing spaces)
            if stripped.lower() == section_name.lower():
                result.append(f"## {stripped}")
                result.append("")
                is_section = True
                break
        # Also match lines that look like section names: short text with emoji, no URLs
        if not is_section and len(stripped) < 40 and not "(" in stripped and not stripped.startswith("*"):
            # Check if it's a known section name pattern (text + emoji)
            if re.match(r"^[A-Z][\w\s]+[^\w\s]$", stripped) and any(
                ord(c) > 0x2000 for c in stripped
            ):
                result.append(f"## {stripped}")
                result.append("")
                is_section = True
        if is_section:
            in_microblog = "microblog" in stripped.lower() or "microposts" in stripped.lower()
            i += 1
            continue

        # Check for ** Section\n---- pattern (some new-format issues still have these)
        if stripped.startswith("** "):
            title_text = stripped[3:].strip()
            if i + 1 < len(lines) and "----" in lines[i + 1]:
                i += 2
                url_match = re.match(r"^(.*?)\s*\((https?://[^\s)]+)\)\s*$", title_text)
                if url_match:
                    result.append(f"### [{url_match.group(1).strip()}]({url_match.group(2)})")
                else:
                    result.append(f"## {title_text}")
                result.append("")
                continue

        # Check for article title: "Title (url)" followed by "domain.com" on next line
        # Only match if the line ends with a URL in parens and is short enough to be a title
        url_match = re.match(r"^(.+?)\s+\((https?://[^\s)]+)\)\s*$", stripped)
        if url_match and len(stripped) < 300:
            title = url_match.group(1).strip()
            url = url_match.group(2)

            # Check if next non-blank line is a bare domain
            next_i = i + 1
            while next_i < len(lines) and lines[next_i].strip() == "":
                next_i += 1

            is_article = False
            if next_i < len(lines):
                next_line = lines[next_i].strip()
                # Is this a bare domain? (e.g., "steveblank.com")
                if re.match(r"^[a-z0-9][a-z0-9._-]*\.[a-z]{2,}$", next_line):
                    is_article = True
                    result.append(f"### [{title}]({url})")
                    result.append("")
                    i = next_i + 1
                    continue

            # If no domain follows but line looks like a standalone title (short, no
            # sentence punctuation), treat as article title
            if not is_article and len(title) < 120 and not re.search(r"[.!?]$", title):
                result.append(f"### [{title}]({url})")
                result.append("")
                i += 1
                continue

            # Otherwise it's inline links in a paragraph
            converted = convert_inline_links(stripped)
            result.append(converted)
            i += 1
            continue

        # Bullet items
        if stripped.startswith("* "):
            item_text = stripped[2:]
            item_text = convert_bullet_item(item_text, in_microblog)
            result.append(f"- {item_text}")
            i += 1
            continue

        # Regular line
        converted = convert_inline_links(stripped) if stripped else ""
        result.append(converted)
        i += 1

    body = "\n".join(result)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


# ---------------------------------------------------------------------------
# Shared utility: inline link conversion
# ---------------------------------------------------------------------------

def convert_bullet_item(text, in_microblog):
    """Convert a bullet item, handling microblog items specially.

    Microblog items are 'post text (permalink)' — the URL is just a permalink
    to the original micro.blog post. Convert to 'post text [→](url)'.
    Regular bullet items get normal inline link conversion.
    """
    if in_microblog:
        # Pattern: text (url) at the end
        m = re.match(r"^(.*?)\s*\((https?://[^\s)]+)\)\s*$", text)
        if m:
            post_text = m.group(1).strip()
            url = m.group(2)
            url = url.replace("jthingelstad.micro.blog", "www.thingelstad.com")
            url = url.replace("micro.thingelstad.com", "www.thingelstad.com")
            return f"{post_text} [→]({url})"
    return convert_inline_links(text)


def convert_inline_links(text):
    """Convert inline links like 'word (url)' to markdown '[word](url)'.

    The MailChimp plaintext export puts URLs in parens after the link text.
    We capture only the last few words before the URL parenthetical.
    """

    def replace_link(m):
        preceding = m.group(1).strip()
        url = m.group(2)
        # Rewrite old micro.blog domain
        url = url.replace("jthingelstad.micro.blog", "www.thingelstad.com")
        url = url.replace("micro.thingelstad.com", "www.thingelstad.com")
        return f"[{preceding}]({url})"

    text = re.sub(
        r"(\S+(?:\s+\S+){0,5}?) \((https?://[^\s)]+)\)",
        replace_link,
        text,
    )
    return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def convert_issue(issue_number, dry_run=False):
    """Convert a single issue. Returns (success, message)."""
    path = ARCHIVE_DIR / f"{issue_number}.md"
    if not path.exists():
        return False, f"File not found: {path}"

    front_matter, body = parse_md_file(path)
    if body is None:
        return False, f"Could not parse body from {path}"

    fmt = detect_format(body, issue_number)
    if fmt == "skip":
        return True, f"#{issue_number}: already markdown, skipped"

    original_body = body

    if fmt == "tinyletter":
        converted = convert_tinyletter(body)
    elif fmt == "mailchimp_old":
        converted = convert_mailchimp_old(body)
    elif fmt == "mailchimp_new":
        converted = convert_mailchimp_new(body)
    else:
        return False, f"#{issue_number}: unknown format '{fmt}'"

    if dry_run:
        print(f"\n{'='*60}")
        print(f"ISSUE #{issue_number} ({fmt})")
        print(f"{'='*60}")
        print(converted[:2000])
        if len(converted) > 2000:
            print(f"\n... ({len(converted) - 2000} more chars)")
        return True, f"#{issue_number}: would convert ({fmt}, {len(original_body)} → {len(converted)} bytes)"

    write_md_file(path, front_matter, converted)
    return True, f"#{issue_number}: converted ({fmt}, {len(original_body)} → {len(converted)} bytes)"


def main():
    dry_run = "--dry-run" in sys.argv
    single_issue = None

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--issue" and i < len(sys.argv) - 1:
            single_issue = int(sys.argv[i + 1])

    if single_issue:
        ok, msg = convert_issue(single_issue, dry_run=dry_run)
        print(msg)
    else:
        converted = 0
        skipped = 0
        errors = 0
        for num in range(1, 131):
            path = ARCHIVE_DIR / f"{num}.md"
            if not path.exists():
                continue
            ok, msg = convert_issue(num, dry_run=dry_run)
            if "skipped" in msg:
                skipped += 1
            elif ok:
                converted += 1
                print(msg)
            else:
                errors += 1
                print(f"ERROR: {msg}")

        print(f"\nDone: {converted} converted, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
