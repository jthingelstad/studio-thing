"""Static validation of generated audio scripts.

Reads a script string and emits findings (errors/warnings) for transformation
residue and structural anomalies. The validator deliberately does not judge
prose, voice, or "listenability" — it flags pattern problems that mean the
transform leaked something it shouldn't have.

Adding a rule:
1. Implement `def rule_<name>(text, lines) -> list[Finding]`.
2. Add to ERROR_RULES or WARNING_RULES below.
3. Bump VALIDATOR_VERSION so re-running validate refreshes every issue.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

VALIDATOR_VERSION = "v2"

# Errors block `audio build --all`. Warnings always print but never gate.
Severity = str  # "error" | "warning"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    line: int
    snippet: str
    message: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "line": self.line,
            "snippet": self.snippet,
            "message": self.message,
        }


def _truncate(text: str, length: int = 120) -> str:
    text = text.strip()
    if len(text) <= length:
        return text
    return text[: length - 1] + "…"


def _line_findings(
    rule: str, severity: str, message: str, pattern: re.Pattern[str], lines: list[str]
) -> list[Finding]:
    findings: list[Finding] = []
    for index, raw in enumerate(lines, start=1):
        match = pattern.search(raw)
        if match:
            findings.append(Finding(rule, severity, index, _truncate(raw), message))
    return findings


# ---------------------------------------------------------------------------
# Transformation residue rules
# ---------------------------------------------------------------------------

_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+]\([^)\n]+\)")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*]\([^)\n]+\)")
_MARKDOWN_EMPHASIS_RE = re.compile(r"(\*{1,3}[^\s*][^*\n]*\*{1,3})|(__[^_\n]+__)")
_MARKDOWN_CODE_RE = re.compile(r"`[^`\n]*`|^(```|~~~)", re.MULTILINE)
_MARKDOWN_HR_RE = re.compile(r"^[ \t]*-{3,}[ \t]*$")
_HTML_TAG_RE = re.compile(r"<[A-Za-z/][^>]*>")
_HTML_COMMENT_RE = re.compile(r"<!--|-->")
_TEMPLATE_TAG_RE = re.compile(r"\{\{[^}\n]+\}\}|\{%[^%\n]+%\}")
_BARE_URL_RE = re.compile(r"https?://\S+")
_EDITOR_MODE_RE = re.compile(r"buttondown-editor-mode", re.IGNORECASE)
_MAILCHIMP_TEMPLATE_RE = re.compile(r"\*\|[A-Z_]+\|\*|Permalink \(\*\|")
_UNICODE_ARROW_RE = re.compile(r"[→⟶⇒]| => ")
_BOTCHED_DOLLAR_RE = re.compile(
    r"\bdollars?\.\d|\bdollars?\s*[KMBT]\b|\bdollars?\s+(?:thousand|million|billion|trillion)\b",
    re.IGNORECASE,
)


def rule_markdown_link(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "markdown_link",
        "error",
        "Markdown link survived the transform",
        _MARKDOWN_LINK_RE,
        lines,
    )


def rule_markdown_image(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "markdown_image",
        "error",
        "Markdown image survived the transform",
        _MARKDOWN_IMAGE_RE,
        lines,
    )


def rule_markdown_emphasis(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "markdown_emphasis",
        "error",
        "Markdown emphasis (* or _) survived the transform",
        _MARKDOWN_EMPHASIS_RE,
        lines,
    )


def rule_markdown_code(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "markdown_code",
        "error",
        "Backticks or fenced code block survived the transform",
        _MARKDOWN_CODE_RE,
        lines,
    )


def rule_markdown_hr(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "markdown_hr",
        "error",
        "Horizontal rule (---) survived the transform",
        _MARKDOWN_HR_RE,
        lines,
    )


def rule_html_tag(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "html_tag",
        "error",
        "HTML tag survived the transform",
        _HTML_TAG_RE,
        lines,
    )


def rule_html_comment(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "html_comment",
        "error",
        "HTML comment marker survived the transform",
        _HTML_COMMENT_RE,
        lines,
    )


def rule_template_tag(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "template_tag",
        "error",
        "Buttondown / Liquid template tag leaked into the script",
        _TEMPLATE_TAG_RE,
        lines,
    )


def rule_bare_url(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "bare_url",
        "error",
        "Bare URL would be read character-by-character by TTS",
        _BARE_URL_RE,
        lines,
    )


def rule_editor_mode_marker(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "editor_mode_marker",
        "error",
        "Buttondown editor-mode marker leaked into the script",
        _EDITOR_MODE_RE,
        lines,
    )


def rule_inline_emoji(text: str, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for index, raw in enumerate(lines, start=1):
        for char in raw:
            code = ord(char)
            if 0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF:
                findings.append(
                    Finding(
                        "inline_emoji",
                        "warning",
                        index,
                        _truncate(raw),
                        "Inline emoji in body text — TTS may speak the unicode name",
                    )
                )
                break
    return findings


def rule_unicode_arrow(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "unicode_arrow",
        "warning",
        "Arrow glyph survived — briefly-section separator may not have been consumed",
        _UNICODE_ARROW_RE,
        lines,
    )


def rule_mailchimp_template_artifacts(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "mailchimp_template_artifacts",
        "warning",
        "Looks like a leftover MailChimp template token",
        _MAILCHIMP_TEMPLATE_RE,
        lines,
    )


def rule_botched_dollar(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "botched_dollar",
        "error",
        "Dollar amount normalization left behind a magnitude or decimal that won't speak well",
        _BOTCHED_DOLLAR_RE,
        lines,
    )


# ---------------------------------------------------------------------------
# Structural rules
# ---------------------------------------------------------------------------

# Keep in sync with synthesize.MAX_CHARS without creating an import cycle.
_MAX_CHUNK_CHARS = 3800
_MIN_SCRIPT_CHARS = 200
_LONG_SCRIPT_CHARS = 60_000
_LONG_DIGIT_RUN_RE = re.compile(r"\d{8,}")
_SECTION_INTRO_RE = re.compile(
    r"^Now, the (.+?) section\.|^Now, more links\.|^Now, for your information\."
)
_SECTION_END_RE = re.compile(r"^That's the end of (.+)\.$")


def rule_chunk_too_long(text: str, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    # Mirror synthesize.split_sentences semantics for the worst-case sentence length.
    for paragraph_index, paragraph in enumerate(re.split(r"\n{2,}", text)):
        sentences = re.split(r"(?<=[.!?])\s+", paragraph) or [paragraph]
        for sentence in sentences:
            if len(sentence) > _MAX_CHUNK_CHARS:
                # Map back to a line number — best effort: find the first line that contains
                # the start of the sentence.
                first_words = sentence.strip()[:60]
                line_no = 1
                if first_words:
                    for index, raw in enumerate(lines, start=1):
                        if first_words[:30] in raw:
                            line_no = index
                            break
                findings.append(
                    Finding(
                        "chunk_too_long",
                        "error",
                        line_no,
                        _truncate(sentence),
                        f"Sentence is {len(sentence)} chars, exceeds TTS request limit of {_MAX_CHUNK_CHARS}",
                    )
                )
    return findings


def rule_script_too_short(text: str, lines: list[str]) -> list[Finding]:
    if len(text) < _MIN_SCRIPT_CHARS:
        return [
            Finding(
                "script_too_short",
                "error",
                1,
                _truncate(text),
                f"Script is only {len(text)} chars — likely a transform failure",
            )
        ]
    return []


def rule_script_too_long(text: str, lines: list[str]) -> list[Finding]:
    if len(text) > _LONG_SCRIPT_CHARS:
        return [
            Finding(
                "script_too_long",
                "warning",
                1,
                f"{len(text)} chars",
                f"Script is {len(text)} chars — over {_LONG_SCRIPT_CHARS} threshold",
            )
        ]
    return []


def rule_empty_section(text: str, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for index, raw in enumerate(lines):
        intro_match = _SECTION_INTRO_RE.match(raw.strip())
        if not intro_match:
            continue
        # Walk forward looking for content before the next section-end / section-intro.
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor < len(lines):
            following = lines[cursor].strip()
            end_match = _SECTION_END_RE.match(following)
            if end_match:
                findings.append(
                    Finding(
                        "empty_section",
                        "error",
                        index + 1,
                        _truncate(raw),
                        "Section intro followed immediately by closing — no entries",
                    )
                )
    return findings


def rule_unbalanced_quote(text: str, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    depth = 0
    for index, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped == "Quote.":
            depth += 1
        elif stripped == "End quote.":
            if depth == 0:
                findings.append(
                    Finding(
                        "unbalanced_quote",
                        "error",
                        index,
                        stripped,
                        "End quote. without a preceding Quote.",
                    )
                )
            else:
                depth -= 1
    if depth > 0:
        findings.append(
            Finding(
                "unbalanced_quote",
                "error",
                len(lines),
                "Quote.",
                f"{depth} unclosed Quote. block(s) at end of script",
            )
        )
    return findings


def rule_long_digit_run(text: str, lines: list[str]) -> list[Finding]:
    return _line_findings(
        "long_digit_run",
        "warning",
        "Long digit run — TTS will read each digit",
        _LONG_DIGIT_RUN_RE,
        lines,
    )


def rule_repeated_paragraph(text: str, lines: list[str]) -> list[Finding]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    counter = Counter(p for p in paragraphs if len(p) > 80)
    findings: list[Finding] = []
    for paragraph, count in counter.items():
        if count >= 3:
            line_no = 1
            for index, raw in enumerate(lines, start=1):
                if raw.strip().startswith(paragraph[:60]):
                    line_no = index
                    break
            findings.append(
                Finding(
                    "repeated_paragraph",
                    "warning",
                    line_no,
                    _truncate(paragraph),
                    f"Paragraph appears {count} times — possible transform loop",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

ERROR_RULES = (
    rule_markdown_link,
    rule_markdown_image,
    rule_markdown_emphasis,
    rule_markdown_code,
    rule_markdown_hr,
    rule_html_tag,
    rule_html_comment,
    rule_template_tag,
    rule_bare_url,
    rule_editor_mode_marker,
    rule_botched_dollar,
    rule_chunk_too_long,
    rule_script_too_short,
    rule_empty_section,
    rule_unbalanced_quote,
)

WARNING_RULES = (
    rule_inline_emoji,
    rule_unicode_arrow,
    rule_mailchimp_template_artifacts,
    rule_script_too_long,
    rule_long_digit_run,
    rule_repeated_paragraph,
)


def run_validators(script_text: str) -> tuple[list[Finding], list[Finding]]:
    """Run every rule against the script. Returns (errors, warnings)."""
    lines = script_text.splitlines()
    errors: list[Finding] = []
    warnings: list[Finding] = []
    for rule in ERROR_RULES:
        errors.extend(rule(script_text, lines))
    for rule in WARNING_RULES:
        warnings.extend(rule(script_text, lines))
    return errors, warnings
