"""Anthropic client + prompt loading for workshop bot personas.

The agent loop (`tools/agent_loop.py`) drives the actual completion calls;
this module owns the singleton client, the model registry, and the
on-disk prompt loader. Prompts live in `prompts/{name}.md`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Optional

import anthropic

REPO = Path(__file__).resolve().parents[4]
PROMPTS_DIR = REPO / "apps" / "workshop_bot" / "prompts"

MODELS = {
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-4-7",
    "haiku": "claude-haiku-4-5-20251001",
}

# Anthropic API pricing — USD per million tokens. Kept here (rather than
# only in the workshop-bot-llm-usage SKILL.md) so any in-process tool —
# AgentRun, the exercise harness, ad-hoc scripts — can compute cost
# without duplicating the table. Update both this and SKILL.md when
# Anthropic changes rates. The claude-sonnet-4-6 row is retained so cost
# lookups on historical agent_runs (pre-Sonnet-5) still resolve.
# NOTE: the claude-sonnet-5 rates mirror 4.6 as a provisional placeholder —
# confirm against Anthropic's pricing page and correct if they differ.
RATES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-5":           {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_create":  3.75},
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

_KNOWN_PERSONAS = ("eddy",)

# Each call purpose bills to its own Anthropic key so the console Usage view
# attributes spend for Eddy vs. one-off project work ("general": pipeline
# scripts, archive/API support tasks). Keys share one workspace, so this is
# visibility — not spend-cap isolation.
_KEY_ENV_BY_PURPOSE = {
    "eddy":    "ANTHROPIC_EDDY_API_KEY",
    "general": "ANTHROPIC_GENERAL_API_KEY",
}

# One client per purpose, built lazily and cached (each holds its own api_key).
_clients: dict[str, anthropic.Anthropic] = {}


def client(purpose: str = "general") -> anthropic.Anthropic:
    """Anthropic client whose key bills the given purpose.

    ``purpose`` is one of the persona names or ``"general"``. Fails fast
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


def validate_keys(purposes: Optional[Iterable[str]] = None) -> None:
    """Raise if any required Anthropic key is missing.

    ``purposes`` lets callers validate only the enabled runtime surface. For
    example, bot startup validates the persona keys for configured Discord
    tokens, while the offline eval harness validates the selected persona set.
    Omitting it preserves the stricter "all known purposes" check.
    """
    if purposes is None:
        required = list(_KEY_ENV_BY_PURPOSE)
    else:
        required = []
        for purpose in purposes:
            if purpose not in required:
                required.append(purpose)
    unknown = [purpose for purpose in required if purpose not in _KEY_ENV_BY_PURPOSE]
    if unknown:
        raise RuntimeError(
            "unknown Anthropic client purpose(s): "
            + ", ".join(sorted(unknown))
            + f"; expected one of {sorted(_KEY_ENV_BY_PURPOSE)}"
        )
    missing = [
        _KEY_ENV_BY_PURPOSE[purpose]
        for purpose in required
        if not os.environ.get(_KEY_ENV_BY_PURPOSE[purpose])
    ]
    if missing:
        raise RuntimeError(
            "missing required Anthropic API keys: " + ", ".join(sorted(missing))
        )


def _resolve_prompt_path(name: str) -> Path:
    """Map a prompt name to its on-disk path under prompts/.

    - ``"team"`` → ``prompts/shared/team.md``
    - ``"<persona>"`` → ``prompts/<persona>/prompt.md``
    - ``"<persona>-<file>"`` → ``prompts/<persona>/<file>.md`` (e.g.
      ``"eddy-draft-review"`` → ``prompts/eddy/draft-review.md``)
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


# ``format_issue_index`` was deleted in the cost-reduction pass. Agents now
# answer "what issues exist around X?" via archive tools on demand instead of
# carrying a huge one-line-per-issue cheat sheet in every prompt.
