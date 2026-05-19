"""Process raw Buttondown email data: assign issue numbers from subject lines.

The link-extraction primitives (``extract_links``, ``extract_domains``,
``count_words``, ``NOTABLE_SECTIONS``, ``BRIEFLY_SECTIONS``) moved to
``librarian_core.links`` so workshop_bot's compose-archive job and the website
build can share them. They're re-exported here for the existing callers in
``pipeline/content/content.py``.
"""

import re

# Re-exports — keep the existing import surface for content.py while the link
# logic lives in the shared module.
from librarian_core.links import (  # noqa: F401
    BRIEFLY_SECTIONS,
    NOTABLE_SECTIONS,
    count_words,
    extract_domains,
    extract_links,
)


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
