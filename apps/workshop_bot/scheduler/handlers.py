"""Scheduled-job handlers — the cron → ``jobs/`` bridge.

The scheduled surface is the content-loop pipeline in
``apps/workshop_bot/jobs/``. ``content_job`` bridges a cron ``JobSpec``
(``functools.partial(content_job, job=<name>)``) to a job module's async
``run(ctx, **kwargs)``, translating the scheduler's ``JobContext`` (which
carries ``team`` and ``deps``) to the jobs package's own ``JobContext``.
The job does whatever posting it needs via ``ctx.post(...)``; this handler
just logs the outcome.

(Sharing is **phase-driven**, not polled: an issue enters the Share phase at
``put-to-bed``, which posts the Share card and auto-fires ``promotion-prep``.
There is no RSS feed monitoring.)

(There are no per-persona heartbeats anymore — everything an agent does on
a cadence is a job: ``update-draft``, ``pinboard-scan``, ``daily-metrics``,
``promotion-prep``.)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import JobContext

logger = logging.getLogger("workshop.scheduler.handlers")


# Maps a job name to its async ``run(ctx, **kwargs)`` entrypoint. Imports
# are lazy so loading scheduler.handlers doesn't pull the whole jobs graph.
def _content_job_runner(name: str):
    from ..jobs import (
        daily_metrics, feedbin_ingest, follow_up, garden_checkin, pinboard_scan,
        promotion_prep, scout_checkin, update_draft,
    )

    return {
        "update-draft": update_draft.run,
        "pinboard-scan": pinboard_scan.run,
        "promotion-prep": promotion_prep.run,
        "daily-metrics": daily_metrics.run,
        "follow-up-sweep": follow_up.sweep,
        "feedbin-ingest": feedbin_ingest.run,
        "scout-checkin": scout_checkin.run,
        "garden-checkin": garden_checkin.run,
    }.get(name)


async def content_job(ctx: "JobContext", *, job: str, **kwargs) -> str:
    """Run a content-loop job (``apps/workshop_bot/jobs/<job>.py``) on the
    scheduler. Wired via ``functools.partial(content_job, job="<name>")``."""
    from ..jobs import _base as jobs_base

    runner = _content_job_runner(job)
    if runner is None:
        logger.warning("content_job: no runner registered for %r", job)
        return "skipped"
    job_ctx = jobs_base.JobContext(deps=getattr(ctx, "deps", None), trigger="scheduled")
    result = await runner(job_ctx, **kwargs)
    logger.info("content_job %s -> ok=%s: %s", job, getattr(result, "ok", "?"), getattr(result, "message", ""))
    return "ok" if getattr(result, "ok", False) else "noop"
