"""Summarize Briefly-style link sections for audio."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from manifest import hash_text
from script import clean_inline, strip_emoji

REPO = Path(__file__).resolve().parents[2]
CONTENT_PIPELINE = REPO / "pipeline" / "content"
if str(CONTENT_PIPELINE) not in sys.path:
    sys.path.insert(0, str(CONTENT_PIPELINE))

import process_emails  # noqa: E402

load_dotenv(REPO / ".env")

MODEL = "claude-sonnet-4-6"
POINTER = "All of these are linked in the web archive."
DRY_RUN_PLACEHOLDER = (
    "This Briefly section would be summarized for the final audio render. "
    "All of these are linked in the web archive."
)


@dataclass(frozen=True)
class BrieflySection:
    heading: str
    source: str
    start: int
    end: int

    @property
    def source_hash(self) -> str:
        return hash_text(self.source)


def normalize_section_name(value: str) -> str:
    value = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", value).strip()
    return re.sub(r"\s+", " ", value)


def spoken_heading(value: str) -> str:
    value = strip_emoji(clean_inline(value)).strip(" .")
    if value == "FYI":
        return "FYI"
    return value


_HRULE_RE = re.compile(r"^[ \t]*-{3,}[ \t]*$", re.MULTILINE)


def find_briefly_sections(markdown_body: str) -> list[BrieflySection]:
    sections: list[BrieflySection] = []
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown_body))
    for index, match in enumerate(matches):
        heading = normalize_section_name(match.group(1))
        if heading not in process_emails.BRIEFLY_SECTIONS:
            continue
        next_h2 = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_body)
        # Also stop at the first horizontal rule after the heading. This
        # prevents the trailing haiku / closing block from being swallowed
        # into the Briefly summary when no further H2 follows.
        rule = _HRULE_RE.search(markdown_body, match.end())
        end = rule.start() if rule and rule.start() < next_h2 else next_h2
        sections.append(
            BrieflySection(
                heading=spoken_heading(heading),
                source=markdown_body[match.start():end].strip(),
                start=match.start(),
                end=end,
            )
        )
    return sections


def source_hash_for_sections(sections: list[BrieflySection]) -> str:
    return hash_text("\n\n".join(section.source_hash for section in sections))


def section_cache(entry: dict[str, Any]) -> dict[str, str]:
    cache = entry.get("briefly_syntheses")
    if isinstance(cache, dict):
        return {str(key): str(value) for key, value in cache.items()}
    if entry.get("briefly_synthesis_hash") and entry.get("briefly_synthesis_text"):
        return {str(entry["briefly_synthesis_hash"]): str(entry["briefly_synthesis_text"])}
    return {}


def section_prompt(section: BrieflySection) -> str:
    section_text = re.sub(r"\*\*\[([^\]]+)]\([^)]+\)\*\*", r"\1", section.source)
    section_text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", section_text)
    section_text = re.sub(r"https?://\S+", "", section_text)
    section_text = clean_inline(section_text)
    return section_text


def creative_brief() -> str:
    path = REPO / "docs" / "creative" / "brief.md"
    if not path.exists():
        return "Plain, warm, editorial. Avoid hype."
    return path.read_text(encoding="utf-8")


def sanitize_summary(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\bclick here\b", "look in the archive", text, flags=re.IGNORECASE)
    text = re.sub(r"\bin this section\b", "here", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if not text.endswith(POINTER):
        text = text.rstrip(".") + f". {POINTER}"
    return text


def call_claude(section: BrieflySection) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("The anthropic package is required for Briefly audio synthesis.") from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is required for Briefly audio synthesis.")

    system = (
        "You write spoken summaries for The Weekly Thing audio archive. "
        "Produce a 30-60 second spoken overview in Jamie Thingelstad's voice. "
        "Make it a brief tour of themes, not a list. Do not read URLs. "
        "Do not say click here. Do not say in this section. "
        f"End exactly with: {POINTER}\n\n"
        f"Voice context:\n{creative_brief()}"
    )
    user = (
        f"Summarize this {section.heading} link section for audio. "
        "Preserve the editorial, warm, observational tone.\n\n"
        f"{section_prompt(section)}"
    )
    client = anthropic.Anthropic(timeout=60.0, max_retries=1)
    response = client.messages.create(
        model=MODEL,
        max_tokens=450,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    return sanitize_summary(text)


def apply_briefly_synthesis(
    markdown_body: str,
    manifest_entry: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> tuple[str, dict[str, Any]]:
    entry = manifest_entry or {}
    sections = find_briefly_sections(markdown_body)
    if not sections:
        return markdown_body, {}

    cache = section_cache(entry)
    replacements: list[tuple[BrieflySection, str]] = []
    new_cache = dict(cache)

    for section in sections:
        cached = cache.get(section.source_hash)
        if cached:
            summary = cached
        elif dry_run:
            summary = DRY_RUN_PLACEHOLDER
        else:
            summary = call_claude(section)
            new_cache[section.source_hash] = summary
        replacements.append((section, summary))

    updated = markdown_body
    for section, summary in reversed(replacements):
        replacement = f"## {section.heading}\n\n{summary}\n\n"
        updated = updated[:section.start] + replacement + updated[section.end:]

    combined_hash = source_hash_for_sections(sections)
    metadata: dict[str, Any] = {
        "briefly_synthesis_hash": combined_hash,
        "briefly_syntheses": new_cache,
    }
    if len(sections) == 1:
        metadata["briefly_synthesis_text"] = replacements[0][1]
    return updated, metadata
