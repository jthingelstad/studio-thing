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

REPO = Path(__file__).resolve().parents[4]
PROMPTS_DIR = REPO / "apps" / "workshop_bot" / "prompts"

MODELS = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
    "haiku": "claude-haiku-4-5-20251001",
}

# Anthropic API pricing — USD per million tokens. Kept here (rather than
# only in the workshop-bot-llm-usage SKILL.md) so any in-process tool —
# AgentRun, the exercise harness, ad-hoc scripts — can compute cost
# without duplicating the table. Update both this and SKILL.md when
# Anthropic changes rates.
RATES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":         {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_create":  3.75},
    "claude-opus-4-7":           {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_create": 18.75},
    "claude-haiku-4-5-20251001": {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_create":  1.25},
}


def cost_usd(
    model: Optional[str],
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_create_tokens: int = 0,
) -> Optional[float]:
    """Cost of one LLM call (or sum of calls) in USD.

    Returns ``None`` when ``model`` is missing from :data:`RATES_USD_PER_MTOK`
    so callers can distinguish "untracked" from "free". Pass token counts
    that already aggregate across an AgentRun if you're pricing a row;
    pass per-call counts otherwise.
    """
    rates = RATES_USD_PER_MTOK.get(model or "")
    if rates is None:
        return None
    return (
        (input_tokens or 0)        * rates["input"]
        + (output_tokens or 0)       * rates["output"]
        + (cache_read_tokens or 0)   * rates["cache_read"]
        + (cache_create_tokens or 0) * rates["cache_create"]
    ) / 1_000_000


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

_KNOWN_PERSONAS = ("eddy", "linky", "marky", "patty")

# Each call purpose bills to its own Anthropic key so the console Usage view
# attributes spend per agent (the four personas) vs. per one-off project work
# ("general": the blog alt-text backfill and the pipeline scripts). Keys share
# one workspace, so this is visibility — not spend-cap isolation.
_KEY_ENV_BY_PURPOSE = {
    "eddy":    "ANTHROPIC_EDDY_API_KEY",
    "linky":   "ANTHROPIC_LINKY_API_KEY",
    "marky":   "ANTHROPIC_MARKY_API_KEY",
    "patty":   "ANTHROPIC_PATTY_API_KEY",
    "general": "ANTHROPIC_GENERAL_API_KEY",
}

# One client per purpose, built lazily and cached (each holds its own api_key).
_clients: dict[str, anthropic.Anthropic] = {}


def client(purpose: str = "general") -> anthropic.Anthropic:
    """Anthropic client whose key bills the given purpose.

    ``purpose`` is one of the four persona names or ``"general"``. Fails fast
    on an unknown purpose or a missing/empty key env var rather than silently
    falling back to a shared key (which would mis-attribute spend).
    """
    env = _KEY_ENV_BY_PURPOSE.get(purpose)
    if env is None:
        raise RuntimeError(
            f"unknown Anthropic client purpose {purpose!r}; "
            f"expected one of {sorted(_KEY_ENV_BY_PURPOSE)}"
        )
    if purpose not in _clients:
        key = os.environ.get(env)
        if not key:
            raise RuntimeError(f"{env} is not set (required for purpose {purpose!r})")
        _clients[purpose] = anthropic.Anthropic(api_key=key, timeout=DEFAULT_API_TIMEOUT_SECS)
    return _clients[purpose]


def validate_keys() -> None:
    """Raise if any required Anthropic key is missing. Called at bot startup so
    a misconfigured key fails fast instead of mis-billing or crashing mid-run."""
    missing = [env for env in _KEY_ENV_BY_PURPOSE.values() if not os.environ.get(env)]
    if missing:
        raise RuntimeError(
            "missing required Anthropic API keys: " + ", ".join(sorted(missing))
        )


def _resolve_prompt_path(name: str) -> Path:
    """Map a prompt name to its on-disk path under prompts/.

    - ``"team"`` → ``prompts/shared/team.md``
    - ``"<persona>"`` → ``prompts/<persona>/prompt.md``
    - ``"<persona>-<file>"`` → ``prompts/<persona>/<file>.md`` (e.g.
      ``"eddy-draft-review"`` → ``prompts/eddy/draft-review.md``,
      ``"linky-research-card"`` → ``prompts/linky/research-card.md``)
    """
    if name == "team":
        return PROMPTS_DIR / "shared" / "team.md"
    head, sep, rest = name.partition("-")
    if sep and head in _KNOWN_PERSONAS and rest:
        return PROMPTS_DIR / head / f"{rest}.md"
    return PROMPTS_DIR / name / "prompt.md"


def load_prompt(name: str) -> str:
    if name not in _prompt_cache:
        _prompt_cache[name] = _resolve_prompt_path(name).read_text(encoding="utf-8").strip()
    return _prompt_cache[name]


# ``format_issue_index`` was deleted in the cost-reduction pass — the
# one-line-per-issue cheat sheet (~47.5k tokens for 348 issues) was
# injected into every persona's system prompt and dominated Linky's
# per-link cost. Personas now answer "what issues exist around X?"
# via ``archive__search`` (BM25), with ``archive__get_issue`` /
# ``archive__quote_search`` for deeper retrieval.


