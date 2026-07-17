"""LLM-based faithfulness review of generated audio scripts.

Stage 4 of the audio pipeline (after build/validate/audio). Compares each
issue's body markdown to the generated script and asks Haiku to flag
*objective* transformation problems — content that's missing or distorted,
not subjective prose judgments.

Output is written to data/audio/script_review.json. Errors gate
`audio build --all` the same way validate errors do.
"""

from __future__ import annotations

import os
import time

import anthropic
from pydantic import BaseModel, Field

REVIEWER_VERSION = "v2"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_INPUT_CHARS = 32_000  # cap per side; longest body+script under this comfortably

# Haiku 4.5 pricing as of 2026-05.
_HAIKU_INPUT_PER_MTOK = 1.0
_HAIKU_OUTPUT_PER_MTOK = 5.0
_HAIKU_CACHE_READ_PER_MTOK = 0.10
_HAIKU_CACHE_WRITE_PER_MTOK = 1.25


class ReviewFinding(BaseModel):
    severity: str = Field(description="Either 'error' or 'warning'.")
    where: str = Field(
        description="A short quoted phrase from the script (or 'preamble', 'closing') showing the location."
    )
    what: str = Field(
        description="One concise sentence describing the objective problem. No suggestions."
    )


class ReviewResult(BaseModel):
    findings: list[ReviewFinding] = Field(
        description="Empty list if no transformation issues were found."
    )


SYSTEM_PROMPT = """You audit transformation faithfulness between a newsletter body (Markdown) and the audio script generated from it.

Your only job: list specific transformation bugs. You are not judging prose, voice, listenability, pacing, or quality. You are not suggesting improvements.

Acceptable transformations — DO NOT flag any of these:
- Images, image alt text, image captions removed
- Link URLs removed (link titles preserved as plain text)
- Bare URLs removed
- Markdown formatting stripped (asterisks, brackets, backticks, underscores, italics, bold)
- Section intros added by the transform like "Now, the X section."
- Section closings added by the transform like "That's the end of X."
- Numbered cues added like "Link one.", "Link two.", "Journal entry three."
- Date stamps removed from journal entries (e.g. "Jul 12, 2024 at 8:13 PM")
- Liquid / Buttondown template tags removed (`{{ ... }}`, `{% ... %}`)
- HTML tags and HTML comments removed
- Inline emoji removed (☕️, 🎉, 🇮🇪, etc.)
- Unicode arrows removed (→, ⟶, ⇒)
- Reddit-discuss closing line removed (`_You can discuss... r/WeeklyThing..._`)
- "Would you like to discuss..." CTA removed
- Issue preamble added at the start ("The Weekly Thing, issue N. ...")
- Issue closing added at the end ("That brings us to the end of...")
- Date strings normalized to spoken form ("April 26, twenty twenty six")
- Years 2000–2029 normalized ("twenty twenty four" instead of "2024")
- Ordinals normalized ("21st" → "twenty first")
- Dollar amounts normalized ("$5.50" → "5 dollars and 50 cents", "$2.5 billion" → "2.5 billion dollars")
- "&" replaced with " and "
- "e.g.", "i.e.", "vs." replaced with their spoken forms
- Blockquotes wrapped with "Quote." / "End quote." cues
- Horizontal rules (`---`) removed
- Code fences and code blocks removed
- Cover-photo blocks (the "---" delimited block at the start of an issue containing an image and dateline) removed
- Decorative emoji-only lines removed
- Empty section blocks (header followed immediately by closing with no content) removed entirely
- Paragraphs reflowed onto single lines
- Multiple blank lines collapsed
- Headings rephrased into "Now, the X section." form
- Subject line emojis removed from the preamble
- Year normalization applied even inside link titles or proper-noun phrases ("2017 Internet Trends" → "twenty seventeen Internet Trends" is fine)
- Ordinal normalization applied anywhere ("1st" → "first", "26th" → "twenty sixth", "31st" → "thirty first" — all fine)
- Heart emoji (❤️, ♥️, 💙, 💚, 💛, 🧡, 💜, 🖤) replaced with the word "love" (it's used as a verb in micro-posts: "I ❤️ X" → "I love X")
- Decorative leading characters in titles being removed (★, ☆, ◉, ✪, etc. at the start of a link title)
- Source typos that exist in BOTH the body and the script (e.g. "your" instead of "you", "droped" instead of "dropped", "Wintegreen") — these are not transformation bugs, they are pre-existing in the source
- Author names or other text that contains spaced letters in the SOURCE body (e.g. "a n n i e m u e l l e r" — if the body has it spaced that way, the script preserving it spaced is correct)
- Section headings of the form "## by <name>" appearing as plain text instead of section cues
- "## The end" / "## End" / "## Fin" sign-off H2s removed
- A microblog/journal entry losing its trailing emoji that doesn't represent a verb (e.g. "great match! ⚽️" → "great match!" is fine)
- Stylistic emoji separators or page breaks removed

Flag (these ARE bugs):
- A substantive sentence or paragraph from the body that has no equivalent content in the script (excluding everything in the acceptable list above)
- Sentences in the script that are garbled, missing words, have broken syntax, or look corrupted
- Numbers/dates/dollar amounts/years that look transformed wrong (e.g. "2 dollars.5 billion" instead of "2.5 billion dollars")
- Names or proper nouns that look corrupted or cut off mid-token
- Leftover formatting cruft that should have been stripped (template tags, HTML tags, raw markdown syntax, bare URLs)
- Two paragraphs that got fused together with no separator
- A link title that's clearly truncated or has stray characters

Output: a JSON object with a `findings` array. Each finding has `severity` ("error" or "warning"), `where` (short quoted phrase locating the issue), and `what` (one sentence describing the objective problem). If nothing's wrong, return `{"findings": []}`.

Severity:
- error: the script has a real bug that affects audio fidelity (corrupted text, mangled numbers, dropped substantive content, leftover formatting cruft)
- warning: borderline / context-dependent (e.g. a paragraph dropped that COULD be intentional, ambiguous truncation)

Be conservative. If you're not sure something is a bug, don't flag it."""


def _truncate(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[truncated]"


def review_issue(
    client: anthropic.Anthropic, issue: str, body: str, script: str
) -> tuple[ReviewResult, dict]:
    """Run the Haiku faithfulness review for one issue. Returns (result, usage_dict)."""
    user_content = (
        f"Issue #{issue}.\n\n"
        f"--- BODY (Markdown source) ---\n"
        f"{_truncate(body)}\n\n"
        f"--- SCRIPT (generated audio script) ---\n"
        f"{_truncate(script)}\n\n"
        f"Return your findings."
    )

    t0 = time.monotonic()
    resp = client.messages.parse(
        model=HAIKU_MODEL,
        max_tokens=2000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
        output_format=ReviewResult,
    )
    duration = round(time.monotonic() - t0, 2)
    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        "duration_s": duration,
    }
    usage["est_cost_usd"] = _estimate_cost(usage)
    return resp.parsed_output, usage


def _estimate_cost(usage: dict) -> float:
    fresh = (
        usage["input_tokens"]
        - usage.get("cache_read_input_tokens", 0)
        - usage.get("cache_creation_input_tokens", 0)
    )
    cost = (
        fresh * _HAIKU_INPUT_PER_MTOK
        + usage["output_tokens"] * _HAIKU_OUTPUT_PER_MTOK
        + usage.get("cache_read_input_tokens", 0) * _HAIKU_CACHE_READ_PER_MTOK
        + usage.get("cache_creation_input_tokens", 0) * _HAIKU_CACHE_WRITE_PER_MTOK
    ) / 1_000_000
    return round(cost, 6)


def make_client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_GENERAL_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_GENERAL_API_KEY is required for `scripts review`. Add it to .env or the environment."
        )
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_GENERAL_API_KEY"])
