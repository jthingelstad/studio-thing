"""Declarative scheduled jobs.

Each ``JobSpec`` is just a cron string and a Python function. The function
runs at the scheduled time and does whatever it needs to: pull data,
format a report, post to a channel, write S3, save memory.

The scheduled surface is the ``apps/workshop_bot/jobs/`` content-loop
pipeline, fired from cron via ``functools.partial(handlers.content_job,
job=…)``. Today:

- ``update-draft`` — daily 17:00 CT. Projects upstream content into
  ``draft.md``; PASSes if no issue is in flight; runs Eddy's Opus review
  into the draft.html drawer during the Build phase.
- ``pinboard-scan`` — every 3h 07:00–22:00 CT, year-round (07/10/13/16/19/22).
  Linky's per-link research pass over Jamie's public toread bookmarks.
  Discovery feeds are currently paused, so the scheduled scan does not
  pull Pinboard Popular; each toread card posts to ``#research``. PASSes
  silently on empty scans.
- ``daily-metrics`` — daily 19:00 CT. Polls active campaigns, checks
  subscriber growth + engagement; PASSes silently when nothing material
  moved, else posts a report.
- ``follow-up-sweep`` — hourly. Fires due follow-ups (agent commitments —
  time-based or "when the issue hits N"): runs the persona's agent loop
  with the note + context and posts a check-in; PASSes when nothing's due.
  The deliberate, targeted replacement for per-persona heartbeats.

The per-persona heartbeats were all retired as these jobs took over (see
the JOBS comment). ``handlers.heartbeat`` still exists for ad-hoc / eval
use but isn't scheduled. To add a job: write/extend a handler in
``handlers.py`` (or a job module under ``jobs/``), add a ``JobSpec``
here, restart the bot.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Awaitable, Callable, TYPE_CHECKING

from . import handlers

if TYPE_CHECKING:
    from .runner import JobContext

DEFAULT_TZ = "America/Chicago"


@dataclass(frozen=True)
class JobSpec:
    id: str
    cron: str                                            # 5-field cron (M H DOM MON DOW)
    func: "Callable[[JobContext], Awaitable[None]]"      # async (ctx) -> None
    enabled: bool = True
    timezone: str = DEFAULT_TZ


JOBS: tuple[JobSpec, ...] = (
    # All per-persona heartbeats have been retired in favor of the
    # content-loop jobs below: Linky → pinboard-scan (Step 5), Eddy
    # job-triggered via update-draft / reorder / compose-* (Step 6),
    # Patty's only job is compose-cta (Step 6), Marky → promotion-prep +
    # daily-metrics (Steps 7–8). handlers.heartbeat still exists for
    # ad-hoc / eval use but isn't scheduled.
    # ---------- Content-loop jobs ----------
    JobSpec(
        id="update-draft-daily",
        cron="0 17 * * *",                               # Daily 17:00 Central — projects the day's
                                                         # upstream content into draft.md. PASSes
                                                         # cleanly if no issue is in flight; Eddy's
                                                         # Opus review runs during the Build phase.
        func=functools.partial(handlers.content_job, job="update-draft"),
    ),
    JobSpec(
        id="linky-pinboard-scan",
        cron="5 7-22/3 * * *",                           # Every 3h at :05 from 07:00–22:00 Central
                                                         # (07/10/13/16/19/22), year-round. Per-link
                                                         # research pass over the toread lane. Discovery
                                                         # feeds are currently paused, so no Pinboard
                                                         # Popular pull runs; each card posts as its own
                                                         # #research message. PASSes silently when all
                                                         # source lists come back empty.
        func=functools.partial(handlers.content_job, job="pinboard-scan"),
    ),
    JobSpec(
        id="linky-feedbin-ingest",
        cron="35 * * * *",                               # Hourly at :35 — offset from the pinboard-scan
                                                         # :05 firings so new starred items have ~30 min
                                                         # of lead time to land in Pinboard before the
                                                         # next toread-lane scan picks them up.
                                                         # Quiet by default (PASSes silently when no new
                                                         # stars); posts a brief #research message only
                                                         # when actually new bookmarks were filed.
        func=functools.partial(handlers.content_job, job="feedbin-ingest"),
    ),
    # Note: there's no RSS-poll job. Sharing is phase-driven — an issue
    # enters the Share phase at put-to-bed, which posts the Share card and
    # auto-fires promotion-prep. promotion-prep is otherwise manual
    # (/marky prep or the Share-card button).
    JobSpec(
        id="marky-daily-metrics",
        cron="0 19 * * *",                               # Daily 19:00 Central. Polls active
                                                         # campaigns (appends a metrics row each
                                                         # run), checks subscriber growth +
                                                         # engagement; PASSes silently when nothing
                                                         # material moved.
        func=functools.partial(handlers.content_job, job="daily-metrics"),
    ),
    JobSpec(
        id="follow-up-sweep",
        cron="23 * * * *",                               # Hourly at :23. Fires due follow-ups —
                                                         # agent commitments ("I'll check in
                                                         # tomorrow evening", "when we hit 387"):
                                                         # runs the persona's agent loop with the
                                                         # note + context, posts a check-in.
                                                         # PASSes silently when nothing's due.
        func=functools.partial(handlers.content_job, job="follow-up-sweep"),
    ),
    JobSpec(
        id="scout-slate-checkin",
        cron="30 17 * * *",                              # Daily 17:30 Central, just after the 17:00
                                                         # update-draft projection. Scout reviews the
                                                         # slate and posts a brief note to #production
                                                         # only if something's worth flagging; else
                                                         # PASSes. Replaces the mechanical phase-card
                                                         # refresh — the web page is the scoreboard.
        func=functools.partial(handlers.content_job, job="scout-checkin"),
    ),
    JobSpec(
        id="garden-checkin",
        cron="0 9 * * 1",                                # Monday 09:00 Central. Eddy tends the idea
                                                         # garden and, if a cluster is ripe or a
                                                         # pattern is worth naming, posts one note to
                                                         # #editorial; else PASSes. Proactive idea
                                                         # development — the slow-rhythm counterpart
                                                         # to the daily slate check-in.
        func=functools.partial(handlers.content_job, job="garden-checkin"),
    ),
)


def by_id(job_id: str) -> JobSpec | None:
    for job in JOBS:
        if job.id == job_id:
            return job
    return None
