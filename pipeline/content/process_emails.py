"""Process raw Buttondown email data: extract links, assign issue numbers, write output files."""

import re
from urllib.parse import urlparse

from domain_exclusions import is_excluded

# Sections that contain curated links (the editorial content).
# Earlier issues used different names for similar sections — including
# emoji-suffixed variants from the 2019–2020 era (~#100–#130).
# "Featured" is merged with Notable per editorial intent.
NOTABLE_SECTIONS = {
    "Notable",
    "Must Read",
    "Featured",
    "Notable Links 📌",
    "Featured Links 🏅",
    "Links 📌",
}
BRIEFLY_SECTIONS = {
    "Briefly",
    "Recommended Links",
    "FYI",
    "Yet More Links 🍞",
}


def _parse_sections(markdown_body):
    """Split markdown body into named sections based on H2 headings.

    Returns list of (section_name, section_text) tuples.
    Content before the first H2 is returned with section_name=None.
    """
    parts = re.split(r"^(## .+)$", markdown_body, flags=re.MULTILINE)
    sections = []
    current_name = None

    for part in parts:
        h2_match = re.match(r"^## (.+)$", part.strip())
        if h2_match:
            raw = h2_match.group(1).strip()
            # Strip markdown links from heading (e.g., ## [Notable](url) → Notable)
            current_name = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", raw).strip()
        else:
            sections.append((current_name, part))

    return sections


def _add_link(links, text, url, heading_context, section):
    """Helper to validate and add a link to the list."""
    if not url or url.startswith("#") or url.startswith("mailto:"):
        return
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        domain = domain.lower()
    except Exception:
        return
    if domain:
        links.append(
            {
                "text": text,
                "url": url,
                "domain": domain,
                "heading_context": heading_context,
                "section": section,
            }
        )


def _extract_notable_links(text, section_name):
    """Extract only the primary curated links from Notable-style sections.

    In Notable, each curated link is an H3 heading: ### [Title](url)
    Only these heading links are editorial picks. Inline links in the
    commentary below each heading are incidental references, not curated content.
    """
    links = []
    seen_urls = set()

    for line in text.split("\n"):
        # Only extract links from H3 headings (the editorial picks)
        heading_match = re.match(r"^###\s+(.+)", line)
        if not heading_match:
            continue

        heading_text = heading_match.group(1).strip()
        # Extract the first markdown link from the heading
        link_match = re.search(r"\[([^\]]*)\]\(([^)]+)\)", heading_text)
        if link_match:
            link_text = link_match.group(1).strip()
            url = link_match.group(2).strip()
            if url not in seen_urls:
                seen_urls.add(url)
                _add_link(links, link_text, url, heading_text, section_name)

    return links


def _extract_briefly_links(text, section_name):
    """Extract only the primary curated link from each Briefly item.

    In Briefly, each item is a paragraph with one bolded link:
      Commentary text → **[Title](url)**
    Only the bolded link is the editorial pick.
    Falls back to extracting the first link per paragraph if no bold links found.
    """
    links = []
    seen_urls = set()

    for line in text.split("\n"):
        if not line.strip():
            continue

        # Look for bolded markdown links: **[text](url)**
        bold_match = re.search(r"\*\*\[([^\]]*)\]\(([^)]+)\)\*\*", line)
        if bold_match:
            link_text = bold_match.group(1).strip()
            url = bold_match.group(2).strip()
            if url not in seen_urls:
                seen_urls.add(url)
                _add_link(links, link_text, url, None, section_name)
            continue

        # Fallback: H3 heading link (older format)
        heading_match = re.match(r"^###\s+(.+)", line)
        if heading_match:
            link_match = re.search(
                r"\[([^\]]*)\]\(([^)]+)\)", heading_match.group(1)
            )
            if link_match:
                link_text = link_match.group(1).strip()
                url = link_match.group(2).strip()
                if url not in seen_urls:
                    seen_urls.add(url)
                    _add_link(links, link_text, url, None, section_name)

    return links


def _extract_all_links(text, section_name):
    """Extract all links from text. Used only for very early issues
    that have no H2 section structure at all."""
    links = []
    current_heading = None
    seen_urls = set()

    for line in text.split("\n"):
        heading_match = re.match(r"^#{1,6}\s+(.+)", line)
        if heading_match:
            current_heading = heading_match.group(1).strip()

        for match in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", line):
            link_text = match.group(1).strip()
            url = match.group(2).strip()
            if url not in seen_urls:
                seen_urls.add(url)
                _add_link(links, link_text, url, current_heading, section_name)

        for match in re.finditer(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            line,
            re.IGNORECASE,
        ):
            url = match.group(1).strip()
            link_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if url not in seen_urls:
                seen_urls.add(url)
                _add_link(links, link_text, url, current_heading, section_name)

    return links


def extract_links(markdown_body):
    """Extract curated links from Notable and Briefly sections only.

    Notable: only H3 heading links (the editorial picks).
    Briefly: only bolded links (the primary link per item).
    Inline/incidental links in commentary are excluded.

    For issues that predate the Notable/Briefly format, the equivalent
    sections (Must Read, Featured, Recommended Links, FYI) are included.
    """
    sections = _parse_sections(markdown_body)

    notable_links = []
    briefly_links = []

    for section_name, section_text in sections:
        if section_name in NOTABLE_SECTIONS:
            notable_links.extend(
                _extract_notable_links(section_text, section_name)
            )
        elif section_name in BRIEFLY_SECTIONS:
            briefly_links.extend(
                _extract_briefly_links(section_text, section_name)
            )

    # For issues with no H2 sections at all (very early issues),
    # treat the entire body as curated content
    has_h2 = any(name is not None for name, _ in sections)
    if not has_h2:
        notable_links = _extract_all_links(markdown_body, None)

    return {
        "notable": notable_links,
        "briefly": briefly_links,
        "all_curated": notable_links + briefly_links,
    }


def extract_domains(links):
    """Extract unique, non-excluded FQDNs from a list of link dicts."""
    domains = set()
    for link in links:
        domain = link.get("domain", "")
        if domain and not is_excluded(domain):
            domains.add(domain)
    return sorted(domains)


def count_words(markdown_body):
    """Count words in the markdown body, excluding YAML front matter and HTML tags."""
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", markdown_body)
    # Strip markdown image syntax
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    # Strip URLs
    text = re.sub(r"https?://\S+", " ", text)
    # Strip Buttondown template tags
    text = re.sub(r"\{\{[^}]*\}\}", " ", text)
    text = re.sub(r"\{%[^%]*%\}", " ", text)
    # Strip the editor mode comment
    text = re.sub(r"<!--.*?-->", " ", text)
    # Count words
    words = text.split()
    return len(words)


def extract_subject_number(subject):
    """Extract the issue number from the email subject line.

    Matches patterns like:
      "Weekly Thing #42 / ..."
      "Weekly Thing 343 / ..."
      "Special Thing #140 / ..."
      "Weekly Thing #2^8 / ..." → 256
      "WT347 — ..."   (the current short-form convention)
    """
    # Handle exponential notation (e.g., #2^8 = 256)
    m_exp = re.search(r"(?:Weekly|Special)\s+Thing\s*#?\s*(\d+)\^(\d+)", subject)
    if m_exp:
        return int(m_exp.group(1)) ** int(m_exp.group(2))

    m = re.search(r"(?:Weekly|Special)\s+Thing\s*#?\s*(\d+)", subject)
    if m:
        return int(m.group(1))

    # Short form: "WT347 — Theme" (workshop_bot's compose-meta convention).
    m_wt = re.search(r"\bWT\s*#?\s*(\d+)\b", subject)
    if m_wt:
        return int(m_wt.group(1))
    return None


def is_special_issue(subject):
    """Check if this is a 'Special Thing' bonus issue (not a regular weekly issue)."""
    return subject.strip().lower().startswith("special thing")


def assign_issue_numbers(emails):
    """Assign issue numbers to emails.

    Sort by publish_date ascending (oldest first).
    Extract issue number from subject line when available.
    For early issues without numbers in subjects, auto-number sequentially by date.
    Special issues (e.g., "Special Thing #140") get a string suffix to avoid collision.
    """
    sorted_emails = sorted(emails, key=lambda e: e.get("publish_date", ""))

    # First pass: extract subject numbers
    numbered = []
    for email in sorted_emails:
        subject = email.get("subject", "")
        subj_num = extract_subject_number(subject)
        special = is_special_issue(subject)
        numbered.append((subj_num, special, email))

    # Collect all regular issue numbers to detect collisions
    regular_numbers = set()
    for subj_num, special, email in numbered:
        if subj_num is not None and not special:
            regular_numbers.add(subj_num)

    # Second pass: assign final numbers
    auto_number = 1
    result = []
    for subj_num, special, email in numbered:
        if subj_num is not None:
            if special and subj_num in regular_numbers:
                # Special issue collides with a regular issue — use string suffix
                result.append((f"{subj_num}-special", email))
            else:
                result.append((subj_num, email))
        else:
            result.append((auto_number, email))
            auto_number += 1

    return result


def process(emails):
    """Process raw email data into structured issue data.

    Returns list of dicts ready for output, sorted by number ascending.
    """
    numbered_emails = assign_issue_numbers(emails)
    issues = []

    for number, email in numbered_emails:
        body = email.get("body", "")
        link_data = extract_links(body)
        all_curated = link_data["all_curated"]
        domains = extract_domains(all_curated)
        words = count_words(body)

        issue = {
            "id": email.get("id", ""),
            "number": number,
            "subject": email.get("subject", ""),
            "publish_date": email.get("publish_date", ""),
            "slug": email.get("slug", ""),
            "description": email.get("description", ""),
            "image": email.get("image"),
            "absolute_url": email.get("absolute_url", ""),
            "body": body,
            "domains": domains,
            "links": all_curated,
            "notable_links": link_data["notable"],
            "briefly_links": link_data["briefly"],
            "word_count": words,
        }
        issues.append(issue)

    # Sort by number ascending (special issues like "140-special" sort after their base number)
    def sort_key(issue):
        n = issue["number"]
        if isinstance(n, int):
            return (n, "")
        # String like "140-special" — sort after the base number
        base = int(re.match(r"(\d+)", str(n)).group(1))
        return (base, str(n))

    issues.sort(key=sort_key)
    return issues
