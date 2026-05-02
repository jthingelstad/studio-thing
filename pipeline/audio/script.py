"""Transform archive markdown into plain text suitable for TTS."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
FENCED_CODE_RE = re.compile(r"^(```|~~~)[\s\S]*?^\1\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)]\(([^)]+)\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
BARE_URL_RE = re.compile(r"https?://\S+")

# Cover/photo block: an `---`/`---` separator pair that opens with an
# image. The block holds a caption + dateline + location and has no value
# in audio. Required shape:
#   ---
#   ![alt](src)        <- image must be the first non-blank line
#   <up to ~8 lines of caption/metadata>
#   ---
COVER_BLOCK_RE = re.compile(
    r"^-{3,}[ \t]*\n"
    r"(?:[ \t]*\n)*"
    r"[ \t]*!\[[^\]]*]\([^)]+\)[ \t]*\n"
    r"(?:[^\n]*\n){0,12}"
    r"-{3,}[ \t]*$",
    re.MULTILINE,
)

# Journal-style date-time stamp on its own line, optionally wrapped as
# a markdown link to a permalink. Examples:
#   [Apr 17, 2026 at 7:47 PM](https://...)
#   Apr 20, 2026 at 7:52 PM
_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
JOURNAL_DATE_RE = re.compile(
    rf"^\s*(?:\[)?(?:{_MONTHS})[a-z]*\s+\d{{1,2}},?\s+\d{{4}}"
    r"\s+at\s+\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)\s*\]?(?:\([^)]+\))?\s*$"
)

NORMALIZER_REPLACEMENTS = [
    (re.compile(r"\be\.g\.", re.IGNORECASE), "for example"),
    (re.compile(r"\bi\.e\.", re.IGNORECASE), "that is"),
    (re.compile(r"\bvs\.", re.IGNORECASE), "versus"),
    (re.compile(r"\bvs\b", re.IGNORECASE), "versus"),
    (re.compile(r"&"), " and "),
]

ORDINALS = {
    "1st": "first",
    "2nd": "second",
    "3rd": "third",
    "4th": "fourth",
    "5th": "fifth",
    "6th": "sixth",
    "7th": "seventh",
    "8th": "eighth",
    "9th": "ninth",
    "10th": "tenth",
    "11th": "eleventh",
    "12th": "twelfth",
    "13th": "thirteenth",
    "14th": "fourteenth",
    "15th": "fifteenth",
    "16th": "sixteenth",
    "17th": "seventeenth",
    "18th": "eighteenth",
    "19th": "nineteenth",
    "20th": "twentieth",
    "21st": "twenty first",
    "22nd": "twenty second",
    "23rd": "twenty third",
    "24th": "twenty fourth",
    "25th": "twenty fifth",
    "26th": "twenty sixth",
    "27th": "twenty seventh",
    "28th": "twenty eighth",
    "29th": "twenty ninth",
    "30th": "thirtieth",
    "31st": "thirty first",
}

YEAR_WORDS = {
    2000: "two thousand",
    2001: "two thousand one",
    2002: "two thousand two",
    2003: "two thousand three",
    2004: "two thousand four",
    2005: "two thousand five",
    2006: "two thousand six",
    2007: "two thousand seven",
    2008: "two thousand eight",
    2009: "two thousand nine",
    2010: "twenty ten",
    2011: "twenty eleven",
    2012: "twenty twelve",
    2013: "twenty thirteen",
    2014: "twenty fourteen",
    2015: "twenty fifteen",
    2016: "twenty sixteen",
    2017: "twenty seventeen",
    2018: "twenty eighteen",
    2019: "twenty nineteen",
    2020: "twenty twenty",
    2021: "twenty twenty one",
    2022: "twenty twenty two",
    2023: "twenty twenty three",
    2024: "twenty twenty four",
    2025: "twenty twenty five",
    2026: "twenty twenty six",
    2027: "twenty twenty seven",
    2028: "twenty twenty eight",
    2029: "twenty twenty nine",
}

HEADING_INTROS = {
    "Featured": "Now, the Featured section.",
    "Featured Links": "Now, the Featured Links section.",
    "Notable": "Now, the Notable section.",
    "Notable Links": "Now, the Notable Links section.",
    "Links": "Now, the Links section.",
    "Must Read": "Now, the Must Read section.",
    "Briefly": "Now, the Briefly section.",
    "Recommended Links": "Now, the Recommended Links section.",
    "FYI": "Now, for your information.",
    "Yet More Links": "Now, more links.",
    "Journal": "Now, the Journal section.",
}

# Short label used in the closing cue ("That's the end of {label}.")
HEADING_LABELS = {
    "Featured": "Featured",
    "Featured Links": "Featured Links",
    "Notable": "Notable",
    "Notable Links": "Notable Links",
    "Links": "Links",
    "Must Read": "Must Read",
    "Briefly": "Briefly",
    "Recommended Links": "Recommended Links",
    "FYI": "the FYI section",
    "Yet More Links": "More Links",
    "Journal": "the Journal",
}

# Sections whose H3 entries are individual links worth signposting.
LINK_SECTION_HEADINGS = {
    "Featured",
    "Featured Links",
    "Notable",
    "Notable Links",
    "Links",
    "Must Read",
}

# Sections whose paragraphs use the inline `<commentary> → **[title](url)**`
# form. We announce each as `Link N. "title"` and then read the commentary,
# matching the cadence of LINK_SECTION_HEADINGS.
BRIEFLY_SECTION_HEADINGS = {
    "Briefly",
    "Recommended Links",
    "FYI",
    "Yet More Links",
}

# Sections whose H3 entries are personal journal posts.
JOURNAL_SECTION_HEADINGS = {"Journal"}

BRIEFLY_LINK_RE = re.compile(r"\*\*\[([^\]]+)]\([^)]+\)\*\*")
REDDIT_DISCUSS_RE = re.compile(
    r"^[ \t]*_You can discuss any of these links at the "
    r"\[[^\]]*r/WeeklyThing[^\]]*]\([^)]+\)\._[ \t]*$",
    re.MULTILINE,
)

# Signing receipts in newer issues — `Signed by name.eth: 0x...` followed by
# a long hex hash. Useless in audio (TTS would spell every hex digit).
SIGNED_BY_RE = re.compile(
    r"^[ \t]*Signed by [^:\n]+:\s*0x[0-9a-fA-F]+[ \t]*$",
    re.MULTILINE,
)


def strip_emoji(text: str) -> str:
    return "".join(
        char
        for char in text
        if not (
            0x1F000 <= ord(char) <= 0x1FAFF
            or 0x2600 <= ord(char) <= 0x27BF
            or ord(char) == 0xFE0F  # variation selector
            or ord(char) == 0x200D  # zero-width joiner (used in compound emoji)
            or ord(char) == 0x2060  # word joiner
        )
    )


def clean_inline(text: str) -> str:
    text = IMAGE_RE.sub("", text)
    text = LINK_RE.sub(r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Asterisk emphasis: *text*, **text**, ***text***.
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Underscore emphasis: only treat `_` as a delimiter when it's NOT part of
    # an identifier (e.g. `schema_version`, `group_concat`). Word characters
    # on either side mean the underscore is intra-word.
    text = re.sub(r"(?<![A-Za-z0-9_])_{1,3}([^_\n]+?)_{1,3}(?![A-Za-z0-9_])", r"\1", text)
    # Strip leftover bold markers from multi-line spans (e.g. a haiku wrapped
    # in **...** across three lines).
    text = re.sub(r"\*{2,3}", "", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = BARE_URL_RE.sub("", text)
    text = text.replace("\\|", "|")
    text = text.replace("\\", "")
    # Strip inline emoji — TTS would otherwise speak the unicode names
    # ("smiling face with smiling eyes"), which is jarring in prose.
    text = strip_emoji(text)
    # Strip unicode arrows — used in old micro-posts as link separators
    # ("commentary. → title") and in Tinyletter-era end-of-bullet markers.
    text = re.sub(r"\s*[→⟶⇒]\s*", " ", text)
    return normalize_text(text)


def normalize_text(text: str) -> str:
    for pattern, replacement in NORMALIZER_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = DOLLAR_AMOUNT_RE.sub(_replace_dollars, text)
    text = re.sub(
        r"\b([1-9]|[12]\d|3[01])(st|nd|rd|th)\b",
        lambda m: ORDINALS.get(m.group(0).lower(), m.group(0)),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(20[0-2]\d)\b", lambda m: YEAR_WORDS.get(int(m.group(1)), m.group(1)), text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *([,.;:!?])", r"\1", text)
    return text.strip()


# Match `$<int>(.<frac>)?` optionally followed by a magnitude word or
# letter (K/M/B/T or thousand/million/billion/trillion). Captures groups:
#   1 = whole dollars (may include commas)
#   2 = fractional digits (1+ digits) or None
#   3 = magnitude word/letter or None
DOLLAR_AMOUNT_RE = re.compile(
    r"\$(\d[\d,]*)(?:\.(\d+))?(?:\s*(thousand|million|billion|trillion|trn|bn|tn|mn|[KMBT]))?\b",
    re.IGNORECASE,
)

_MAGNITUDE_WORDS = {
    "k": "thousand",
    "m": "million",
    "b": "billion",
    "t": "trillion",
    "bn": "billion",
    "mn": "million",
    "tn": "trillion",
    "trn": "trillion",
    "thousand": "thousand",
    "million": "million",
    "billion": "billion",
    "trillion": "trillion",
}


def _replace_dollars(match: re.Match[str]) -> str:
    dollars = match.group(1)
    frac = match.group(2)
    magnitude_raw = (match.group(3) or "").strip().lower()
    magnitude = _MAGNITUDE_WORDS.get(magnitude_raw) if magnitude_raw else None

    if magnitude:
        # "$2.5 billion" → "2.5 billion dollars"; "$9M" → "9 million dollars".
        number = dollars + (f".{frac}" if frac else "")
        return f"{number} {magnitude} dollars"

    if frac is not None:
        if len(frac) == 2:
            # "$50.25" → "50 dollars and 25 cents"; "$50.00" → "50 dollars".
            amount = f"{dollars} dollar" + ("" if dollars == "1" else "s")
            if frac != "00":
                amount += f" and {int(frac)} cents"
            return amount
        # Single-decimal or odd-length fractional with no magnitude word —
        # rare in prose but read it as "<n> point <frac> dollars".
        return f"{dollars} point {frac} dollars"

    return f"{dollars} dollar" + ("" if dollars == "1" else "s")


def heading_text(raw: str) -> str:
    text = clean_inline(raw)
    text = strip_emoji(text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text


def heading_intro(raw: str) -> str:
    text = heading_text(raw)
    return HEADING_INTROS.get(text, f"Now, the {text} section.")


def heading_label(raw: str) -> str:
    text = heading_text(raw)
    return HEADING_LABELS.get(text, text)


def published_date(value: Any) -> str:
    if not value:
        return ""
    raw = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return str(value)
    return parsed.strftime("%B %-d, %Y")


def preamble(frontmatter: dict[str, Any]) -> str:
    number = frontmatter.get("number", "")
    subject = strip_emoji((frontmatter.get("subject") or "").strip()).strip()
    # The subject typically reads "Weekly Thing 345 / Codex, Headless,
    # Wikiwise". Drop the prefix duplicate and keep only the topical
    # tail so the audio doesn't say the issue number twice.
    if " / " in subject:
        subject = subject.rsplit(" / ", 1)[1].strip()
    date = published_date(frontmatter.get("publish_date", ""))
    description = strip_emoji((frontmatter.get("description") or "").strip()).strip()
    parts = [f"The Weekly Thing, issue {number}."]
    if subject:
        parts.append(subject.rstrip(".") + ".")
    parts.extend([f"Published {date}.", "By Jamie Thingelstad."])
    if description:
        intro = description.rstrip(".") + "."
        parts.extend(["In this issue:", intro])
    return normalize_text(" ".join(parts))


def closing(frontmatter: dict[str, Any]) -> str:
    number = frontmatter.get("number", "")
    return normalize_text(
        f"That brings us to the end of the Weekly Thing, issue {number}. "
        "Thanks for listening, and I'll see you next time."
    )


def _strip_cover_blocks(body: str) -> str:
    return COVER_BLOCK_RE.sub("", body)


def body_to_audio_script(body: str, frontmatter: dict[str, Any]) -> str:
    body = HTML_COMMENT_RE.sub("", body)
    body = FENCED_CODE_RE.sub("", body)
    body = _strip_cover_blocks(body)
    body = IMAGE_RE.sub("", body)
    # Strip remaining standalone horizontal rules so TTS doesn't read "dash
    # dash dash". Cover blocks above are already removed.
    body = re.sub(r"^[ \t]*-{3,}[ \t]*$", "", body, flags=re.MULTILINE)
    # Strip the templated "Would you like to discuss..." closing CTA. The
    # audio's own closing line takes its place.
    body = re.sub(r"^Would you like to discuss[^\n]*$", "", body, flags=re.MULTILINE)
    # Strip the italicized "_You can discuss... r/WeeklyThing..._" line that
    # opens the Notable section in recent issues. Audio shouldn't push readers
    # off to Reddit.
    body = REDDIT_DISCUSS_RE.sub("", body)
    body = SIGNED_BY_RE.sub("", body)

    output: list[str] = [preamble(frontmatter), ""]
    quote_lines: list[str] = []
    current_section: str | None = None
    current_section_label: str | None = None
    link_index: int = 0
    skip_next_date: bool = False

    def flush_quote() -> None:
        if not quote_lines:
            return
        quote = clean_inline(" ".join(quote_lines))
        quote_lines.clear()
        if quote:
            output.extend(["", "Quote.", quote, "End quote.", ""])

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*>", line):
            quote_lines.append(re.sub(r"^\s*>\s?", "", line).strip())
            continue

        flush_quote()

        if not line.strip():
            if output and output[-1] != "":
                output.append("")
            continue

        h2 = re.match(r"^##\s+(.+)$", line)
        if h2:
            new_section = heading_text(h2.group(1))
            new_label = heading_label(h2.group(1))
            if current_section_label:
                output.extend(["", f"That's the end of {current_section_label}.", ""])
            intro = heading_intro(h2.group(1))
            if intro:
                output.extend(["", intro, ""])
            current_section = new_section
            current_section_label = new_label
            link_index = 0
            skip_next_date = False
            continue

        # Journal-style date stamps: drop the line, and in micro-entry case
        # use the stamp as the entry boundary so it gets a numbered cue.
        if current_section in JOURNAL_SECTION_HEADINGS and JOURNAL_DATE_RE.match(line):
            if skip_next_date:
                skip_next_date = False
                continue
            link_index += 1
            output.extend([f"Journal entry {_number_word(link_index)}.", ""])
            continue

        h3_link = re.match(r"^###\s+\[([^\]]+)]\([^)]+\)\s*$", line)
        if h3_link:
            title = clean_inline(h3_link.group(1))
            if title:
                if current_section in LINK_SECTION_HEADINGS:
                    link_index += 1
                    output.extend([f"Link {_number_word(link_index)}. \"{title}\"", ""])
                elif current_section in JOURNAL_SECTION_HEADINGS:
                    link_index += 1
                    output.extend([f"Journal entry {_number_word(link_index)}. {title}", ""])
                    skip_next_date = True
                else:
                    output.extend([title, ""])
            continue

        heading = re.match(r"^#{3,6}\s+(.+)$", line)
        if heading:
            text = clean_inline(heading.group(1))
            if text:
                output.extend([text, ""])
            continue

        # Briefly-style line: `<commentary> → **[Title](url)**`. Announce
        # `Link N. "Title"` then read the commentary, matching Notable.
        if current_section in BRIEFLY_SECTION_HEADINGS:
            briefly_match = BRIEFLY_LINK_RE.search(line)
            if briefly_match:
                title = clean_inline(briefly_match.group(1)).rstrip(" .")
                commentary_raw = line[: briefly_match.start()]
                commentary_raw = re.sub(r"\s*[→][ \t]*$", "", commentary_raw)
                commentary = clean_inline(commentary_raw)
                if title:
                    link_index += 1
                    output.extend([f"Link {_number_word(link_index)}. \"{title}\"", ""])
                if commentary:
                    output.extend([commentary, ""])
                continue

        text = clean_inline(line)
        if text:
            output.append(text)
            skip_next_date = False

    flush_quote()
    output.extend(["", closing(frontmatter)])
    output = _drop_empty_sections(output)
    # Drop any line that, after emoji stripping, is empty — these are
    # decorative lone-emoji lines (e.g. "👋", "👨‍💻") that TTS would otherwise
    # read as their unicode names.
    cleaned: list[str] = []
    for entry in output:
        if entry and not strip_emoji(entry).strip():
            continue
        cleaned.append(entry)
    script = "\n".join(cleaned)
    script = re.sub(r"\n{3,}", "\n\n", script)
    return script.strip() + "\n"


_INTRO_LINE_RE = re.compile(r"^Now, the .+? section\.$|^Now, more links\.$|^Now, for your information\.$")
_END_LINE_RE = re.compile(r"^That's the end of .+\.$")


def _drop_empty_sections(lines: list[str]) -> list[str]:
    """Remove `Now, the X section.` followed only by blanks then `That's the end of X.`.

    These appear when an H2 section has no entries we keep — e.g. early MailChimp
    `## Links` dividers above sub-section H2s, or modern `## Supporting Membership`
    blocks where the content (Liquid templates + HTML CTAs) strips to nothing."""
    result = list(lines)
    i = 0
    while i < len(result):
        if result[i].strip() and _INTRO_LINE_RE.match(result[i].strip()):
            j = i + 1
            while j < len(result) and not result[j].strip():
                j += 1
            if j < len(result) and _END_LINE_RE.match(result[j].strip()):
                # Also consume one trailing blank if present so we don't leave
                # a double blank in its place.
                end = j + 1
                if end < len(result) and not result[end].strip():
                    end += 1
                del result[i:end]
                continue
        i += 1
    return result


_NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty",
]


def _number_word(n: int) -> str:
    if 0 <= n < len(_NUMBER_WORDS):
        return _NUMBER_WORDS[n]
    return str(n)
