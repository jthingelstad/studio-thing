"""Runtime bookkeeping: agent-run telemetry (moved from store.py).

(The ``draft_digests`` helpers that lived here died with the retired
``update-draft`` projection — the DB is the draft; there is no snapshot
to diff against.)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .connection import connect


def recent_agent_runs(limit: int = 8) -> list[dict[str, Any]]:
    """Most recent agent_runs rows, newest first — for the ``/eddy
    status`` snapshot ("what's the bot done lately / did anything fail")."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, agent_name, trigger, status, duration_ms, error, "
            "       records_written, model, input_tokens, output_tokens, "
            "       cache_read_tokens, cache_create_tokens, "
            "       started_at, ended_at "
            "FROM agent_runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


class AgentRun:
    """Context manager that opens an agent_runs row and closes it with the result.

    Trigger label convention
    ------------------------

    ``trigger`` is the string written to the ``trigger`` column. A single
    ``agent_runs`` row covers one logical unit of work (one cron fire,
    one slash invocation), regardless of how many internal LLM calls it
    makes — open one ``AgentRun`` per job, not per ``bot.core``.

    The label shape is:

      - **Bare job name** for jobs that make one LLM call (or one
        logical batch under a single context manager):
        ``compose-haiku``, ``compose-echoes``, ``review-text``,
        ``reorder``, ``follow-up``.
      - **``<job>:<sub>``** when a *single job module* opens multiple
        ``AgentRun`` blocks for distinguishable LLM passes that you
        want to query independently in ``agent_runs``:
        ``update-draft:html-review`` + ``update-draft:editorial-card``
        (Eddy's two separate review passes inside ``update-draft``);
        ``compose-meta:subject`` + ``compose-meta:description``
        (the two passes inside ``compose-meta``).
      - **``scheduled:<job-id>``** is added by the scheduler runner
        for the outer cron context (not by job code itself).
      - **``mention``** by ``PersonaBot.on_message`` for an
        @-mention-driven turn outside the job pipeline.

    Adding a new sub-label is the right move only when you'd actually
    query ``agent_runs`` for the distinction (cost analysis,
    latency-bucketing one pass vs another). Otherwise the bare job
    name is enough and the JobResult / logs carry the rest.
    """

    def __init__(self, agent_name: str, trigger: str) -> None:
        self.agent_name = agent_name
        self.trigger = trigger
        self.run_id: Optional[int] = None
        self._t0 = 0.0
        self.records_written = 0
        self.error: Optional[str] = None
        # LLM accounting — set via `record_meta(meta)` from agent_loop's
        # return dict (or any equivalent {"model": …, "usage": {…}} shape).
        # Stored on __exit__. Accumulates across multiple record_meta calls
        # so a single AgentRun covering many internal LLM calls (e.g.,
        # pinboard-scan's per-link loop) sums correctly.
        self.model: Optional[str] = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_create_tokens = 0
        self._has_usage = False

    def record_meta(self, meta: Optional[dict[str, Any]]) -> None:
        """Capture model + accumulate token usage from agent_loop's response.

        ``meta`` is the second element of the ``(reply, meta)`` tuple that
        ``bot.core(...)`` / ``agent_loop.run_async(...)`` returns:

            {"model": "claude-sonnet-4-6",
             "usage": {"input": int, "output": int,
                       "cache_read": int, "cache_create": int},
             "iterations": int, "tool_calls": [...]}

        Safe to call zero, one, or many times within a single AgentRun
        block. Last non-None model wins; usage adds. Tolerates a
        ``None`` meta or a meta without the usage / model keys (logs
        but doesn't raise).
        """
        if not meta:
            return
        model = meta.get("model")
        if model:
            self.model = model
        usage = meta.get("usage") or {}
        self.input_tokens += int(usage.get("input", 0) or 0)
        self.output_tokens += int(usage.get("output", 0) or 0)
        self.cache_read_tokens += int(usage.get("cache_read", 0) or 0)
        self.cache_create_tokens += int(usage.get("cache_create", 0) or 0)
        if usage:
            self._has_usage = True

    def __enter__(self) -> "AgentRun":
        self._t0 = time.monotonic()
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs (agent_name, trigger, status) VALUES (?, ?, 'pending')",
                (self.agent_name, self.trigger),
            )
            self.run_id = int(cur.lastrowid or 0)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = int((time.monotonic() - self._t0) * 1000)
        if exc is not None:
            status = "error"
            self.error = f"{exc_type.__name__}: {exc}" if self.error is None else self.error
        else:
            status = "success"
        # NULL the token columns when no LLM call was recorded — keeps
        # SUM() reports clean (untracked rows don't dilute the avg).
        in_t = self.input_tokens if self._has_usage else None
        out_t = self.output_tokens if self._has_usage else None
        cr_t = self.cache_read_tokens if self._has_usage else None
        cc_t = self.cache_create_tokens if self._has_usage else None
        with connect() as conn:
            conn.execute(
                "UPDATE agent_runs SET status=?, duration_ms=?, error=?, "
                "records_written=?, model=?, input_tokens=?, output_tokens=?, "
                "cache_read_tokens=?, cache_create_tokens=?, "
                "ended_at=datetime('now') WHERE id=?",
                (
                    status,
                    duration_ms,
                    self.error,
                    self.records_written,
                    self.model,
                    in_t,
                    out_t,
                    cr_t,
                    cc_t,
                    self.run_id,
                ),
            )
        # Don't suppress exceptions
