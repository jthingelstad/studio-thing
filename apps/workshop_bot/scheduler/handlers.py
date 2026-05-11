"""Scheduled-job handlers — the cron → ``jobs/`` bridge.

The scheduled surface is the content-loop pipeline in
``apps/workshop_bot/jobs/``. ``content_job`` bridges a cron ``JobSpec``
(``functools.partial(content_job, job=<name>)``) to a job module's async
``run(ctx, **kwargs)``; ``rss_check`` polls the RSS feed and auto-fires
``promotion-prep`` on a newly-published issue. Both translate the
scheduler's ``JobContext`` (which carries ``team`` and ``deps``) to the
jobs package's own ``JobContext``. The job does whatever posting it needs
via ``ctx.post(...)``; these handlers just log the outcome.

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
    from ..jobs import daily_metrics, pinboard_scan, promotion_prep, update_draft

    return {
        "update-draft": update_draft.run,
        "pinboard-scan": pinboard_scan.run,
        "promotion-prep": promotion_prep.run,
        "daily-metrics": daily_metrics.run,
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


# ============================================================
# RSS detection — sees a new published issue, fires promotion-prep
# ============================================================

_MARKY_LAST_DETECTED_KEY = "marky:last-detected-issue"


async def rss_check(ctx: "JobContext") -> str:
    """Poll ``weekly.thingelstad.com/feed.xml`` for a newly-published
    issue. If the latest issue number is higher than the one we last saw
    (recorded in ``agent_notes``), record it and auto-fire
    ``promotion-prep`` for it. Scheduled on a weekend cadence."""
    from ..jobs import _base as jobs_base
    from ..jobs import promotion_prep
    from ..tools import db, rss

    try:
        latest = rss.latest_published_issue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("rss_check: feed fetch/parse failed: %s", exc)
        return "noop"
    if not latest or not latest.get("number"):
        return "noop"
    n = int(latest["number"])

    prior = db.query_agent_notes(
        agent_name="marky", kind="context", query=_MARKY_LAST_DETECTED_KEY,
        include_resolved=True, limit=1,
    )
    last_seen = 0
    if prior:
        try:
            last_seen = int(str(prior[0].get("content") or "0"))
        except (TypeError, ValueError):
            last_seen = 0
    if n <= last_seen:
        return "noop"

    db.insert_agent_note(
        agent_name="marky", kind="context", key=_MARKY_LAST_DETECTED_KEY, content=str(n),
        related_issue=n,
    )
    logger.info("rss_check: new issue detected (#%d, was #%d) — firing promotion-prep", n, last_seen)
    job_ctx = jobs_base.JobContext(deps=getattr(ctx, "deps", None), trigger="rss-detected")
    result = await promotion_prep.run(job_ctx, issue_number=n)
    logger.info("rss_check -> promotion-prep #%d: ok=%s: %s", n, getattr(result, "ok", "?"), getattr(result, "message", ""))
    return "fired" if getattr(result, "ok", False) else "fired-noop"
