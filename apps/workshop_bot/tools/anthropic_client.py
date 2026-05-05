"""Anthropic API wrapper for workshop bot personas.

Loads persona system prompts from prompts/{name}.md, builds system blocks
with cache_control on shared/static content, and exposes a single
``complete()`` entrypoint. Mirrors the pattern in apps/archive-chat/archive_chat.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import anthropic

REPO = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO / "apps" / "workshop_bot" / "prompts"

MODELS = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
    "haiku": "claude-haiku-4-5-20251001",
}


FALLBACK_MODEL = "haiku"
MAX_OUTPUT_TOKENS = 4096


def default_model() -> str:
    raw = (os.environ.get("WORKSHOP_DEFAULT_MODEL") or FALLBACK_MODEL).lower()
    return raw if raw in MODELS else FALLBACK_MODEL

logger = logging.getLogger("workshop.anthropic")

_prompt_cache: dict[str, str] = {}
_client: Optional[anthropic.Anthropic] = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def load_prompt(name: str) -> str:
    if name not in _prompt_cache:
        path = PROMPTS_DIR / f"{name}.md"
        _prompt_cache[name] = path.read_text(encoding="utf-8").strip()
    return _prompt_cache[name]


def format_issue_index(issues: list[dict[str, Any]]) -> str:
    """Compact one-line-per-issue index, used as a cached system block."""
    lines = ["# Archive issue index", ""]
    for issue in issues:
        number = issue.get("number", "?")
        date = (issue.get("publish_date") or "")[:10]
        subject = issue.get("subject", "")
        topics = ", ".join(issue.get("topics", []) or [])
        abstract = (issue.get("summary") or {}).get("abstract", "") or ""
        bits = [f"#{number} ({date}) - {subject}"]
        if topics:
            bits.append(f"Topics: {topics}.")
        if abstract:
            bits.append(f"Abstract: {abstract}")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def format_retrieved(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(no archive excerpts retrieved for this query)"
    parts = ["# Retrieved archive excerpts", ""]
    for chunk in chunks:
        number = chunk.get("issue_number", "?")
        date = (chunk.get("publish_date") or "")[:10]
        subject = chunk.get("subject", "")
        section = chunk.get("section") or "Issue"
        parts.append(f'[#{number} - {date} - "{subject}" - section: {section}]')
        parts.append(chunk["text"].strip())
        parts.append("")
    return "\n".join(parts).rstrip()


def build_system_blocks(
    persona: str,
    *,
    issue_index: Optional[str] = None,
    extras: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Persona prompt first (small, may evolve), then cached static blocks."""
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": load_prompt(persona)},
    ]
    if issue_index:
        blocks.append({
            "type": "text",
            "text": issue_index,
            "cache_control": {"type": "ephemeral"},
        })
    for extra in extras or []:
        blocks.append({
            "type": "text",
            "text": extra,
            "cache_control": {"type": "ephemeral"},
        })
    return blocks


def complete(
    *,
    persona: str,
    user_message: Optional[str] = None,
    history: Optional[list[dict[str, str]]] = None,
    issue_index: Optional[str] = None,
    extras: Optional[list[str]] = None,
    model: Optional[str] = None,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> tuple[str, dict[str, int]]:
    """Run a single completion turn.

    `history` is the prior conversation as Anthropic-shaped messages.
    `user_message` is the new turn appended to that history. If only one of
    them is given, this still works.
    """
    system_blocks = build_system_blocks(persona, issue_index=issue_index, extras=extras)
    messages: list[dict[str, str]] = list(history or [])
    if user_message is not None:
        messages.append({"role": "user", "content": user_message})
    if not messages:
        raise ValueError("complete() needs either history or user_message")
    chosen_model = model or default_model()
    response = client().messages.create(
        model=MODELS[chosen_model],
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    usage = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
        "cache_read": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        "cache_create": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
    }
    logger.info(
        "%s complete (%s): in=%d out=%d cache_r=%d cache_c=%d",
        persona,
        chosen_model,
        usage["input"],
        usage["output"],
        usage["cache_read"],
        usage["cache_create"],
    )
    return text.strip(), usage
