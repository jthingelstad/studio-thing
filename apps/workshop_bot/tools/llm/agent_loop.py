"""Multi-turn tool-using agent loop.

Each persona's ``core()`` calls ``run()`` here. The loop:
1. Calls Claude with team + persona system prompts + tools + conversation.
2. If Claude returns a final text response, returns it.
3. If Claude returns ``tool_use`` blocks, runs each tool synchronously in
   the calling thread (tools are local, fast, sync) and appends a
   ``tool_result`` block per call as the next user message.
4. Repeats until either we get a final text response or hit max_iterations.

    Cache control: the shared team prompt is the largest stable block and gets
    the first ephemeral mark (cached across all five personas via prefix-match);
the issue index gets a second mark so persona-prompt edits don't bust the
issue-index cache. The tool list also gets an ephemeral mark on its last
entry.

Tool names use the ``<system>__<action>`` shape natively (e.g.
``archive__search``, ``buttondown__list_subscribers``). The Anthropic
API enforces ``^[a-zA-Z0-9_-]{1,128}$`` on custom tool names — the
double-underscore separator is API-safe and round-trips without any
boundary translation.

The Anthropic call is synchronous, so ``run_async`` wraps the loop in a
worker thread to keep each persona's discord.py event loop free for
gateway heartbeats.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional, Union

from . import agent_tools, anthropic_client

logger = logging.getLogger("workshop.agent_loop")

DEFAULT_MAX_ITERATIONS = 8
MAX_TOOL_RESULT_CHARS = 50_000
MAX_OUTPUT_TOKENS = 4096
TEAM_PROMPT = "team"


def _owner_mention_block() -> Optional[str]:
    """Tell agents how to @-mention Jamie directly when they need to."""
    raw = (os.environ.get("DISCORD_OWNER_USER_ID") or "").strip()
    if not raw:
        return None
    return (
        "## Mentioning Jamie\n\n"
        f"Jamie's Discord user ID is `{raw}`. When you need to @-mention him "
        f"directly (e.g., a scheduled job firing in `#chatter` that needs his "
        f"eyes), render the literal string `<@{raw}>` — Discord turns that "
        "into a ping. Don't @-mention him in normal replies; he's already "
        "the one talking to you."
    )


def _build_system_blocks(persona: str) -> list[dict[str, Any]]:
    """[team] [owner?] [persona] — cache marker on team AND persona.

    Two cache markers cover two breakpoints: the team prompt alone (the
    floor — shared across all personas) and team+owner+persona together
    (the typical hit — re-use across consecutive calls from the same
    persona). Anthropic returns a hit on the longest prefix it can match,
    so when the persona's prompt is also stable, callers pay cache_read
    rates on the whole system block instead of input rates on the
    persona portion. The persona prompt is ~1.5-2.7K tokens; this is
    a meaningful win for Eddy/Marky who run Opus/Sonnet. Linky on
    Haiku may not benefit — Haiku's cache minimum is ~2K tokens and
    Linky's prompt is just under, so the longer prefix may not cache.
    The team prompt (~4K tokens) caches regardless.

    Note: an earlier version of this function also accepted an
    ``issue_index`` block — a pre-rendered one-line-per-issue cheat
    sheet of every Weekly Thing ever published (~47.5k tokens for
    348 issues) injected as a cached system block. It was Linky's
    biggest single cost driver. Personas can answer the same
    "what issues exist around X?" question via ``archive__search``
    (with ``archive__get_issue`` / ``archive__quote_search`` for
    deeper retrieval), so the cheat sheet was retired — the tool
    surface replaces it on demand. See ``prompts/shared/team.md``."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": anthropic_client.load_prompt(TEAM_PROMPT),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    owner = _owner_mention_block()
    if owner:
        blocks.append({"type": "text", "text": owner})
    blocks.append({
        "type": "text",
        "text": anthropic_client.load_prompt(persona),
        "cache_control": {"type": "ephemeral"},
    })
    return blocks


def _build_tool_specs(
    tool_names: list[str], deps: Any
) -> list[dict[str, Any]]:
    """Build Anthropic tool specs for ``tool_names`` from ``deps.registry``.

    Tool names use the API-safe ``<system>__<action>`` shape natively
    (registered that way at boot), so no name translation happens at
    the API boundary.
    """
    registry = deps.registry
    specs: list[dict[str, Any]] = []
    for name in tool_names:
        tool = registry.get(name)
        if tool is None:
            raise KeyError(f"unknown tool {name!r}")
        spec = dict(tool.spec)  # shallow copy so we can add cache_control
        specs.append(spec)
    if specs:
        # Cache the tool list — last entry gets the marker.
        specs[-1] = {**specs[-1], "cache_control": {"type": "ephemeral"}}
    return specs


def _execute_tool(
    name: str,
    deps: Any,
    raw_input: dict[str, Any],
    *,
    persona: Optional[str] = None,
) -> str:
    tool = deps.registry.get(name)
    if tool is None:
        return json.dumps({"error": f"unknown tool {name!r}"})
    # Enforce per-persona scoping at execution time, even though
    # ``names_for(persona)`` already filters the model's tool list. If a
    # model invents a name for a restricted tool (prompt injection,
    # cross-persona context bleed, hallucination), refuse here so donor
    # data and other privacy-scoped surfaces never reach the wrong
    # persona's transcript.
    if (
        persona is not None
        and tool.restricted_to is not None
        and persona not in tool.restricted_to
    ):
        logger.warning(
            "tool %s refused: persona %r not in %s",
            name, persona, sorted(tool.restricted_to),
        )
        return json.dumps(
            {"error": f"tool {name!r} is not available to persona {persona!r}"}
        )
    func = tool.func
    t0 = time.monotonic()
    token = None
    if persona is not None:
        token = agent_tools.active_persona.set(persona)
    try:
        try:
            result = func(deps, **(raw_input or {}))
        except TypeError as exc:
            return json.dumps({"error": f"bad arguments to {name}: {exc}"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("tool %s raised", name)
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    finally:
        if token is not None:
            agent_tools.active_persona.reset(token)
    dt_ms = int((time.monotonic() - t0) * 1000)
    logger.info("tool %s ok (%dms, args=%s)", name, dt_ms, _short_args(raw_input))
    payload = json.dumps(result, ensure_ascii=False, default=str)
    if len(payload) > MAX_TOOL_RESULT_CHARS:
        original_len = len(payload)
        payload = (
            payload[:MAX_TOOL_RESULT_CHARS]
            + f"\n\n[truncated; tool result was {original_len:,} chars, "
            f"showing first {MAX_TOOL_RESULT_CHARS:,}]"
        )
    return payload


def _short_args(args: dict[str, Any]) -> str:
    parts = []
    for k, v in (args or {}).items():
        s = str(v)
        if len(s) > 60:
            s = s[:60] + "…"
        parts.append(f"{k}={s}")
    return " ".join(parts)


def _accumulate_usage(total: dict[str, int], usage: Any) -> None:
    total["input"] += int(getattr(usage, "input_tokens", 0) or 0)
    total["output"] += int(getattr(usage, "output_tokens", 0) or 0)
    total["cache_read"] += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    total["cache_create"] += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)


def run(
    *,
    persona: str,
    user_message: Union[str, list[dict[str, Any]]],
    history: Optional[list[dict[str, Any]]] = None,
    tools: list[str],
    deps: Any,
    model: Optional[str] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    first_turn_tool_choice: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    """Run a tool-using turn. Returns (final_text, metadata).

    ``user_message`` accepts either a plain string (the common case) or a
    list of Anthropic content blocks (``[{"type": "text", "text": "...",
    "cache_control": {"type": "ephemeral"}}, ...]``) when a caller wants
    to place a per-call cache breakpoint on a stable leading block (e.g.
    ``_draft_review`` parks its multi-KB review prompt in a cached block
    so the daily run benefits from prompt caching too).

    ``first_turn_tool_choice`` (e.g. ``{"type": "any"}``) forces the model to
    open with a tool call instead of prose on the *first* iteration only —
    later turns revert to ``auto`` so the model can still finish with a text
    report. Use it for work-not-chat jobs where the model otherwise narrates
    a plan and burns the output budget before calling a tool (the garden
    tending pass hit exactly that: 4096 tokens of prose, zero tool calls)."""
    history = list(history or [])
    chosen_model = anthropic_client.MODELS[
        model or anthropic_client.default_model()
    ]
    system_blocks = _build_system_blocks(persona)
    tool_specs = _build_tool_specs(tools, deps=deps)

    # Coerce history `content` strings to the assistant message format Anthropic
    # expects — we kept history as list[{role, content (str)}] to date, and
    # that's still valid here.
    messages: list[dict[str, Any]] = list(history)
    messages.append({"role": "user", "content": user_message})

    client = anthropic_client.client(purpose=persona)

    usage_total = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
    tool_calls: list[dict[str, Any]] = []
    last_text = ""

    for iteration in range(max_iterations):
        create_kwargs: dict[str, Any] = dict(
            model=chosen_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system_blocks,
            tools=tool_specs,
            messages=messages,
        )
        # Force a tool call on the opening turn only (then let it converge to
        # a text report). Guarded on tools being present — tool_choice with an
        # empty tool list is a 400.
        if first_turn_tool_choice and iteration == 0 and tool_specs:
            create_kwargs["tool_choice"] = first_turn_tool_choice
        response = client.messages.create(**create_kwargs)
        _accumulate_usage(usage_total, response.usage)

        # Pull text + tool_use from this turn.
        text_chunks: list[str] = []
        tool_uses: list[Any] = []
        for block in response.content:
            if block.type == "text":
                text_chunks.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
        if text_chunks:
            last_text = "".join(text_chunks).strip()

        if response.stop_reason != "tool_use" or not tool_uses:
            logger.info(
                "%s loop done in %d iter(s); stop=%s; tools=%s",
                persona,
                iteration + 1,
                response.stop_reason,
                [c["name"] for c in tool_calls],
            )
            return (
                last_text or "(no text returned)",
                {
                    "model": chosen_model,
                    "usage": usage_total,
                    "iterations": iteration + 1,
                    "tool_calls": tool_calls,
                    "stop_reason": response.stop_reason,
                },
            )

        # Persist assistant turn including tool_use blocks.
        messages.append({"role": "assistant", "content": response.content})

        # Execute tools and assemble a single user message of
        # tool_results. Tool names round-trip unchanged — the registry
        # stores them in API-safe ``<system>__<action>`` form natively.
        tool_result_blocks: list[dict[str, Any]] = []
        for tu in tool_uses:
            payload = _execute_tool(
                tu.name, deps, dict(tu.input or {}), persona=persona
            )
            tool_result_blocks.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": payload}
            )
            tool_calls.append(
                {"name": tu.name, "input": dict(tu.input or {})}
            )
        messages.append({"role": "user", "content": tool_result_blocks})

    # Hit max iterations without a stop_reason != tool_use.
    logger.warning(
        "%s loop hit max_iterations=%d; tools=%s",
        persona,
        max_iterations,
        [c["name"] for c in tool_calls],
    )
    return (
        last_text
        or "I went around in circles on this one — give me a more specific ask?",
        {
            "model": chosen_model,
            "usage": usage_total,
            "iterations": max_iterations,
            "tool_calls": tool_calls,
            "stop_reason": "max_iterations",
        },
    )


async def run_async(
    *,
    persona: str,
    user_message: Union[str, list[dict[str, Any]]],
    history: Optional[list[dict[str, Any]]] = None,
    tools: list[str],
    deps: Any,
    model: Optional[str] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    first_turn_tool_choice: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    """Async wrapper around ``run`` so the calling Discord client's event loop
    keeps running (gateway heartbeats, other messages) during the LLM turn."""
    return await asyncio.to_thread(
        run,
        persona=persona,
        user_message=user_message,
        history=history,
        tools=tools,
        deps=deps,
        model=model,
        max_iterations=max_iterations,
        first_turn_tool_choice=first_turn_tool_choice,
    )
