"""Scheduled-job handlers — the cron → ``jobs/`` bridge.

The scheduler is intentionally small in the newsletter-only Studio: daily
source sync plus Eddy follow-ups. Publishing and review work is web-driven.
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
    from ..jobs import eddy_review, follow_up, sync_issue

    return {
        "sync-issue": sync_issue.run,
        "eddy-review": eddy_review.run,
        "follow-up-sweep": follow_up.sweep,
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
    logger.info(
        "content_job %s -> ok=%s: %s",
        job,
        getattr(result, "ok", "?"),
        getattr(result, "message", ""),
    )
    return "ok" if getattr(result, "ok", False) else "noop"
