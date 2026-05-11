"""Declarative scheduled jobs.

Each ``JobSpec`` is just a cron string and a Python function. The function
runs at the scheduled time and does whatever it needs to: pull data,
format a report, post to a channel, write S3, save memory.

Two shapes today:

- **Heartbeats** — a scheduled agent turn per persona, firing on a
  cadence with that persona's ``heartbeat.md`` prompt. Default ``PASS``;
  posts only when there's something concrete to surface. They guard on
  the active issue window (see the heartbeat prompts) and are being
  retired as the content-loop jobs take over (Step 5/6/8 of the
  redesign). Wired via ``functools.partial(handlers.heartbeat, persona=…)``.
- **Content-loop jobs** — the ``apps/workshop_bot/jobs/`` pipeline,
  fired from cron via ``functools.partial(handlers.content_job, job=…)``.
  Today: ``update-draft`` daily at 17:00 CT (PASSes if no issue is in
  flight or it's locked; Eddy reviews Tue–Fri).

To add a job: write/extend a handler in ``handlers.py`` (or a job module
under ``jobs/``), add a ``JobSpec`` here, restart the bot.
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
    # ---------- Heartbeats ----------
    # One scheduled wake-up per persona. Default response is PASS;
    # the persona only posts when there's something concrete to
    # surface. The earlier-era specialized jobs (linky-wednesday-check,
    # linky-popular-scan, linky-research-unread, marky-daily-engagement,
    # eddy-saturday-prep, linky-friday-curation, marky-weekly-subscriber-
    # report, patty-thursday-member-json) were folded into these
    # heartbeats — the team-redesign work on how to actually help Jamie
    # assemble each issue is pending, and until then heartbeats plus
    # on-demand `/workshop` commands carry the load.
    JobSpec(
        id="eddy-heartbeat",
        cron="30 8 * * *",                               # Daily 08:30 Central — before Jamie's writing window.
        func=functools.partial(handlers.heartbeat, persona="eddy"),
    ),
    JobSpec(
        id="linky-heartbeat",
        cron="0 6-22/6 * * *",                           # Every 6h within 06:00–22:00 Central.
        func=functools.partial(handlers.heartbeat, persona="linky"),
    ),
    JobSpec(
        id="marky-heartbeat",
        cron="0 7-22/3 * * *",                           # Every 3h within 07:00–22:00 Central.
        func=functools.partial(handlers.heartbeat, persona="marky"),
    ),
    JobSpec(
        id="patty-heartbeat",
        cron="0 9 * * *",                                # Daily 09:00 Central.
        func=functools.partial(handlers.heartbeat, persona="patty"),
    ),
    # ---------- Content-loop jobs ----------
    JobSpec(
        id="update-draft-daily",
        cron="0 17 * * *",                               # Daily 17:00 Central — projects the day's
                                                         # upstream content into draft.md. The job
                                                         # PASSes cleanly if no issue is in flight
                                                         # or the issue is locked (final.md exists);
                                                         # Eddy posts a review only Tue–Fri.
        func=functools.partial(handlers.content_job, job="update-draft"),
    ),
)


def by_id(job_id: str) -> JobSpec | None:
    for job in JOBS:
        if job.id == job_id:
            return job
    return None
