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

HEADING_CUES = {
    "Featured": "Featured.",
    "Featured Links": "Featured links.",
    "Notable": "Notable.",
    "Notable Links": "Notable links.",
    "Links": "Links.",
    "Must Read": "Must read.",
    "Briefly": "Briefly.",
    "Recommended Links": "Recommended links.",
    "FYI": "For your information.",
    "Yet More Links": "Yet more links.",
    "Journal": "Journal.",
}


def strip_emoji(text: str) -> str:
    return "".join(
        char
        for char in text
        if not (
            0x1F000 <= ord(char) <= 0x1FAFF
            or 0x2600 <= ord(char) <= 0x27BF
            or ord(char) == 0xFE0F
        )
    )


def clean_inline(text: str) -> str:
    text = IMAGE_RE.sub("", text)
    text = LINK_RE.sub(r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = BARE_URL_RE.sub("", text)
    text = text.replace("\\|", "|")
    text = text.replace("\\", "")
    return normalize_text(text)


def normalize_text(text: str) -> str:
    for pattern, replacement in NORMALIZER_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\$(\d[\d,]*)(?:\.(\d{2}))?", _replace_dollars, text)
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


def _replace_dollars(match: re.Match[str]) -> str:
    dollars = match.group(1)
    cents = match.group(2)
    amount = f"{dollars} dollar" + ("" if dollars == "1" else "s")
    if cents and cents != "00":
        amount += f" and {int(cents)} cents"
    return amount


def heading_text(raw: str) -> str:
    text = clean_inline(raw)
    text = strip_emoji(text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text


def heading_cue(raw: str) -> str:
    text = heading_text(raw)
    return HEADING_CUES.get(text, f"{text}.")


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
    subject = frontmatter.get("subject", "")
    date = published_date(frontmatter.get("publish_date", ""))
    return normalize_text(
        f"The Weekly Thing, issue {number}. {subject}. Published {date}. By Jamie Thingelstad."
    )


def body_to_audio_script(body: str, frontmatter: dict[str, Any]) -> str:
    body = HTML_COMMENT_RE.sub("", body)
    body = FENCED_CODE_RE.sub("", body)
    body = IMAGE_RE.sub("", body)

    output: list[str] = [preamble(frontmatter), ""]
    quote_lines: list[str] = []

    def flush_quote() -> None:
        if not quote_lines:
            return
        quote = clean_inline(" ".join(quote_lines))
        quote_lines.clear()
        if quote:
            output.extend(["", quote, ""])

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
            cue = heading_cue(h2.group(1))
            if cue:
                output.extend(["", cue, ""])
            continue

        h3_link = re.match(r"^###\s+\[([^\]]+)]\([^)]+\)\s*$", line)
        if h3_link:
            title = clean_inline(h3_link.group(1))
            if title:
                output.extend([title, ""])
            continue

        heading = re.match(r"^#{3,6}\s+(.+)$", line)
        if heading:
            text = clean_inline(heading.group(1))
            if text:
                output.extend([text, ""])
            continue

        text = clean_inline(line)
        if text:
            output.append(text)

    flush_quote()
    script = "\n".join(output)
    script = re.sub(r"\n{3,}", "\n\n", script)
    return script.strip() + "\n"
