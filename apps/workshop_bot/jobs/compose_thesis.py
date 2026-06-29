"""``compose-thesis`` — Eddy's 1–3 sentence editorial framing for the
issue. Fires at ``mark-built`` (the Build → Publish phase transition),
after the issue's content is frozen.

Reads the assembled ``draft.md`` (intro + sections in their post-reorder
sequence + outro) and asks Eddy for the editorial anchor. Writes the
result to ``atoms/thesis.md``. Downstream prompts —
``compose-meta:subject`` / ``compose-meta:description`` /
``compose-haiku`` / ``compose-cta`` — read this file as a ``## Thesis``
prefix in their LLM prompts so the four shipping jobs land coherently
on the same framing.

One-shot, no picker UX — runs in the background as part of the phase
transition. Jamie can edit via ``/eddy edit thesis`` to refine.

Best-effort: a failed write or empty Eddy response logs and leaves the
job result unsuccessful; ``mark-built`` keeps going (the phase
transition isn't gated on a successful thesis — better to ship without
a thesis than to wedge the Publish phase). Subject/description/haiku/CTA
prompts already degrade gracefully on a missing thesis.md.
"""

from __future__ import annotations

import asyncio
import logging

from ..tools import content_store, db
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_thesis")

NAME = "compose-thesis"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])

    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return _base.JobResult(False, "(compose-thesis skipped — no team registry)")
    eddy = team.bots.get("eddy")
    if eddy is None or getattr(eddy, "user", None) is None:
        return _base.JobResult(False, "(compose-thesis skipped — Eddy unavailable)")

    try:
        prompt = anthropic_client.load_prompt("eddy-compose-thesis")
    except OSError as exc:
        logger.warning("compose-thesis: prompt missing: %s", exc)
        return _base.JobResult(False, f"prompt missing: {exc}")

    # Read the assembled draft (intro + sections + outro). Reorder may
    # have just landed; this picks up whatever shape the issue is in now.
    body = await asyncio.to_thread(_llm_job.draft_body, n)
    if not body.strip():
        return _base.JobResult(False, f"❌ no draft body for WT{n}.")

    user_msg = (
        f"{prompt}\n\n---\n\nThe assembled draft for WT{n}:\n\n"
        f"```markdown\n{body[: _llm_job.ISSUE_BODY_CAP]}\n```"
    )

    asset = f"{n}/thesis.md"
    try:
        with _base.job_lock([asset], NAME):
            with db.AgentRun("eddy", trigger="compose-thesis") as agent_run:
                answer, meta = await eddy.core(latest=user_msg, history=[], model=None)
                agent_run.record_meta(meta)
                agent_run.records_written = 1 if (answer and answer.strip()) else 0
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"compose-thesis already running ({exc.holder_desc})")

    if not answer or not answer.strip():
        return _base.JobResult(
            False, f"❌ Eddy returned an empty thesis for WT{n}.",
        )

    thesis = answer.strip()
    try:
        await asyncio.to_thread(content_store.write_issue, n, "thesis.md", thesis + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.exception("compose-thesis: S3 write failed for WT%d", n)
        return _base.JobResult(
            False, f"❌ thesis S3 write failed: `{type(exc).__name__}: {exc}`",
        )

    logger.info(
        "compose-thesis: wrote thesis.md for WT%d (%d chars)", n, len(thesis),
    )
    return _base.JobResult(
        True,
        f"📐 Thesis written for WT{n}.",
        data={"issue_number": n, "thesis": thesis},
    )
