"""Anthropic client + prompt loading for workshop bot personas.

The agent loop (`tools/agent_loop.py`) drives the actual completion calls;
this module owns the singleton client, the model registry, and the
on-disk prompt loader. Prompts live in `prompts/{name}.md`.
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
# Generous bound on a single tool-using turn (a long Eddy critique with several
# tool calls can run 20-40s). Well below discord.py's gateway heartbeat needs
# now that the LLM call runs in a worker thread.
DEFAULT_API_TIMEOUT_SECS = 90.0


def default_model() -> str:
    raw = (os.environ.get("WORKSHOP_DEFAULT_MODEL") or FALLBACK_MODEL).lower()
    return raw if raw in MODELS else FALLBACK_MODEL

logger = logging.getLogger("workshop.anthropic")

# Prompts are cached in-process at first read. Edits to prompts/*.md require a
# bot restart to take effect.
_prompt_cache: dict[str, str] = {}
_client: Optional[anthropic.Anthropic] = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=DEFAULT_API_TIMEOUT_SECS)
    return _client


def _resolve_prompt_path(name: str) -> Path:
    """Map a prompt name to its on-disk path under prompts/.

    - ``"team"`` → ``prompts/shared/team.md``
    - ``"<persona>"`` → ``prompts/<persona>/prompt.md``
    - ``"<persona>-heartbeat"`` → ``prompts/<persona>/heartbeat.md``
    """
    if name == "team":
        return PROMPTS_DIR / "shared" / "team.md"
    if name.endswith("-heartbeat"):
        persona = name[: -len("-heartbeat")]
        return PROMPTS_DIR / persona / "heartbeat.md"
    return PROMPTS_DIR / name / "prompt.md"


def load_prompt(name: str) -> str:
    if name not in _prompt_cache:
        _prompt_cache[name] = _resolve_prompt_path(name).read_text(encoding="utf-8").strip()
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


