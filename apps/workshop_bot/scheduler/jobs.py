"""Declarative scheduled jobs.

Each ``JobSpec`` is just a cron string and a Python function. The function
runs at the scheduled time and does whatever it needs to: pull data,
format a report, post to a channel, write S3, save memory.

The scheduled surface is the ``apps/workshop_bot/jobs/`` content-loop
pipeline, fired from cron via ``functools.partial(handlers.content_job,
job=…)`` (or, for ``rss-check``, the bare ``handlers.rss_check``). Today:

- ``update-draft`` — daily 17:00 CT. Projects upstream content into
  ``draft.md``; PASSes if no issue is in flight or it's locked
  (``final.md`` exists); Eddy posts a review Tue–Fri.
- ``pinboard-scan`` — Mon–Fri 06:30 & 18:30 CT. Linky's Pinboard pass;
  PASSes when no issue is in flight or today is outside the window.
- ``rss-check`` — Sat & Sun, every 4h 09:00–21:00 CT. Detects a
  newly-published issue and auto-fires ``promotion-prep``.
- ``daily-metrics`` — daily 19:00 CT. Polls active campaigns, checks
  subscriber growth + engagement; PASSes silently when nothing material
  moved, else posts a report.
- ``thingy-watch`` — hourly. Pulls newly-logged Thingy conversations from
  the Lambda, has Eddy assess each, mirrors it locally, and posts a card
  to ``#chatter``; PASSes silently when nothing new.
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
    # job-triggered via update-draft / create-final / compose-* (Step 6),
    # Patty's only job is compose-cta (Step 6), Marky → promotion-prep +
    # daily-metrics (Steps 7–8). handlers.heartbeat still exists for
    # ad-hoc / eval use but isn't scheduled.
    # ---------- Content-loop jobs ----------
    JobSpec(
        id="update-draft-daily",
        cron="0 17 * * *",                               # Daily 17:00 Central — projects the day's
                                                         # upstream content into draft.md. PASSes
                                                         # cleanly if no issue is in flight or the
                                                         # issue is locked (final.md exists); Eddy
                                                         # posts a review only Tue–Fri.
        func=functools.partial(handlers.content_job, job="update-draft"),
    ),
    JobSpec(
        id="linky-pinboard-scan",
        cron="30 6,18 * * 1-5",                          # Mon–Fri 06:30 & 18:30 Central. PASSes
                                                         # when no issue is in flight or today is
                                                         # outside the window; Linky's prompt does
                                                         # the finer "nothing to do" judgment.
        func=functools.partial(handlers.content_job, job="pinboard-scan"),
    ),
    JobSpec(
        id="marky-rss-check",
        cron="0 9-21/4 * * 6,0",                         # Sat & Sun, every 4h 09:00–21:00 Central.
                                                         # Detects a newly-published issue in the
                                                         # RSS feed; on a new number, fires
                                                         # promotion-prep for it (deduped via
                                                         # agent_notes).
        func=handlers.rss_check,
    ),
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
        id="thingy-watch",
        cron="7 * * * *",                                # Hourly at :07. Pulls newly-logged Thingy
                                                         # conversations from the Lambda, has Eddy
                                                         # assess each one, mirrors it locally, and
                                                         # posts a card to #chatter. PASSes silently
                                                         # when nothing new.
        func=functools.partial(handlers.content_job, job="thingy-watch"),
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
)


def by_id(job_id: str) -> JobSpec | None:
    for job in JOBS:
        if job.id == job_id:
            return job
    return None
