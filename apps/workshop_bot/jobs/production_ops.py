"""Headless issue lifecycle transitions.

The web issue page calls one place for phase flips and related compose work:
- `mark_built`  — Build → Publish: gate on build-ready, flip phase, then fire
  Eddy's compose-envelope and compose-echoes jobs. Each anchors directly on
  the runtime-assembled draft (the DB is the draft), so order is independent.
- `reopen`      — Publish → Build.
- `recompose`   — retry compose-echoes if it failed to auto-fire.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..tools import db
from . import _base, production_state

logger = logging.getLogger("workshop.jobs.production_ops")


async def mark_built(ctx: "_base.JobContext", n: Optional[int] = None) -> "_base.JobResult":
    """Build → Publish. Flip phase and fire Eddy's publish-package composes.
    Refuses if content isn't complete. Card-free — callers handle any surface
    refresh. The composes each anchor on the runtime-assembled draft directly,
    so their order is independent."""
    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    n = int(window["issue_number"])
    if window.get("phase") == "publish":
        return _base.JobResult(
            True, f"WT{n} is already in **Publish**.", data={"issue_number": n, "phase": "publish"}
        )

    import asyncio

    state = await asyncio.to_thread(production_state.build_state, n, window=window)
    if not state.get("build_ready"):
        return _base.JobResult(
            False,
            f"⚠️ WT{n} isn't built yet — needs the three sections + intro + cover.",
            data={"issue_number": n},
        )

    db.set_issue_phase(n, "publish")

    from . import compose_echoes, compose_envelope

    for name, job in (("compose-envelope", compose_envelope), ("compose-echoes", compose_echoes)):
        try:
            await job.run(_base.JobContext(deps=ctx.deps, trigger="mark-built"))
        except Exception:  # noqa: BLE001
            logger.exception("mark-built: %s failed for #%d", name, n)

    return _base.JobResult(
        True,
        f"✅ **WT{n}** marked built — now in **Publish**. Envelope "
        f"(subject/description/haiku) + Echoes composed.",
        data={"issue_number": n, "phase": "publish"},
    )


async def reopen(ctx: "_base.JobContext", n: Optional[int] = None) -> "_base.JobResult":
    """Publish → Build, to fix content. Card-free."""
    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    n = int(window["issue_number"])
    db.set_issue_phase(n, "build")
    return _base.JobResult(
        True,
        f"↩️ WT{n} reopened for edits — back in **Build**.",
        data={"issue_number": n, "phase": "build"},
    )


async def recompose(ctx: "_base.JobContext", n: Optional[int] = None) -> "_base.JobResult":
    """Re-fire compose-echoes if it failed to auto-fire at mark-built.
    Idempotent: a no-op when echoes is present. (The envelope —
    subject/description/haiku — is interactive and re-run via
    ``/eddy issue subject`` / ``haiku`` or ``compose-envelope``, not here.)"""
    import asyncio

    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, "No active issue window.")
    state = await asyncio.to_thread(production_state.publish_state, window=window)
    if not state.get("recompose_needed"):
        return _base.JobResult(
            True, "✅ Nothing to recompose — Echoes is present.", data={"echoes_failed": False}
        )

    from . import compose_echoes

    try:
        res = await compose_echoes.run(_base.JobContext(deps=ctx.deps, trigger="recompose"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("recompose: compose-echoes raised")
        return _base.JobResult(
            False,
            f"⚠️ Recompose hit an error: echoes: {exc!r}",
            data={"fired": [], "errors": [f"echoes: {exc!r}"]},
        )
    if not res.ok:
        return _base.JobResult(
            False,
            f"⚠️ Recompose hit an error: echoes: {res.message}",
            data={"fired": ["echoes"], "errors": [f"echoes: {res.message}"]},
        )
    return _base.JobResult(
        True, "✅ Recompose ran — refreshed echoes.", data={"fired": ["echoes"], "errors": []}
    )
