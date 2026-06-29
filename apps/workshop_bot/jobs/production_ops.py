"""Headless production lifecycle transitions — phase flips and the compose
fires that accompany them. No Discord, no cards.

These are the real logic lifted out of the phase-card modules so the web
project page (and, until they're retired, the cards) call one place:
- `mark_built`  — Build → Publish: gate on build-ready, flip phase, then fire
  compose-thesis → compose-echoes → compose-cta (in that order so each picks up
  the prior's output as its anchor).
- `reopen`      — Publish → Build.
- `recompose`   — retry whichever of thesis/echoes failed to auto-fire.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..tools import db
from . import _base, production_state

logger = logging.getLogger("workshop.jobs.production_ops")


async def mark_built(ctx: "_base.JobContext", n: Optional[int] = None) -> "_base.JobResult":
    """Build → Publish. Flips phase and fires compose-thesis → echoes → cta.
    Refuses if content isn't complete. Card-free — callers handle any surface
    refresh. Order matters: thesis lands before cta so the CTA prompt anchors
    on the freshly-written thesis."""
    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    n = int(window["issue_number"])
    if window.get("phase") == "publish":
        return _base.JobResult(True, f"WT{n} is already in **Publish**.",
                               data={"issue_number": n, "phase": "publish"})

    import asyncio
    state = await asyncio.to_thread(production_state.build_state, n, window=window)
    if not state.get("build_ready"):
        return _base.JobResult(
            False,
            f"⚠️ WT{n} isn't built yet — needs the three sections + intro + cover.",
            data={"issue_number": n},
        )

    db.set_issue_phase(n, "publish")

    from . import compose_cta, compose_echoes, compose_thesis
    for name, job in (("compose-thesis", compose_thesis),
                      ("compose-echoes", compose_echoes),
                      ("compose-cta", compose_cta)):
        try:
            await job.run(_base.JobContext(deps=ctx.deps, trigger="mark-built"))
        except Exception:  # noqa: BLE001
            logger.exception("mark-built: %s failed for #%d", name, n)

    return _base.JobResult(
        True,
        f"✅ **WT{n}** marked built — now in **Publish**. Thesis + Echoes written; "
        f"CTA requested from Patty.",
        data={"issue_number": n, "phase": "publish"},
    )


async def reopen(ctx: "_base.JobContext", n: Optional[int] = None) -> "_base.JobResult":
    """Publish → Build, to fix content. Card-free."""
    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    n = int(window["issue_number"])
    db.set_issue_phase(n, "build")
    return _base.JobResult(True, f"↩️ WT{n} reopened for edits — back in **Build**.",
                           data={"issue_number": n, "phase": "build"})


async def recompose(ctx: "_base.JobContext", n: Optional[int] = None) -> "_base.JobResult":
    """Re-fire compose-thesis and/or compose-echoes for whichever is missing in
    Publish phase. Idempotent: a no-op when both are present."""
    import asyncio
    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    state = await asyncio.to_thread(production_state.publish_state, window=window)
    if not state.get("recompose_needed"):
        return _base.JobResult(True, "✅ Nothing to recompose — thesis + echoes are both present.",
                               data={"thesis_failed": False, "echoes_failed": False})

    from . import compose_echoes, compose_thesis
    fired: list[str] = []
    errors: list[str] = []
    for failed_key, name, job in (("thesis_failed", "thesis", compose_thesis),
                                  ("echoes_failed", "echoes", compose_echoes)):
        if not state.get(failed_key):
            continue
        try:
            res = await job.run(_base.JobContext(deps=ctx.deps, trigger="recompose"))
            fired.append(name)
            if not res.ok:
                errors.append(f"{name}: {res.message}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("recompose: compose-%s raised", name)
            errors.append(f"{name}: {exc!r}")

    if errors:
        return _base.JobResult(False, "⚠️ Recompose hit errors: " + " · ".join(errors),
                               data={"fired": fired, "errors": errors})
    return _base.JobResult(True, f"✅ Recompose ran — refreshed {', '.join(fired)}.",
                           data={"fired": fired, "errors": []})
