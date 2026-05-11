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
  flight or it's locked; Eddy reviews Tue–Fri), ``pinboard-scan`` Mon–Fri
  06:30 & 18:30 CT (Linky's twice-daily Pinboard pass), and ``rss-check``
  on a weekend cadence (``handlers.rss_check`` — detects a newly-published
  issue and auto-fires ``promotion-prep``).

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
    # ---------- Heartbeats (being retired as content-loop jobs land) ----------
    # Linky's heartbeat became the `pinboard-scan` job (Step 5); Eddy's
    # and Patty's were retired in Step 6 (Eddy is job-triggered via
    # update-draft / create-final / compose-*; Patty has no heartbeat
    # surface — compose-cta is her only job). Marky's heartbeat goes away
    # in Step 8. The one remaining heartbeat guards on the active issue
    # window — see prompts/marky/heartbeat.md.
    JobSpec(
        id="marky-heartbeat",
        cron="0 7-22/3 * * *",                           # Every 3h within 07:00–22:00 Central.
        func=functools.partial(handlers.heartbeat, persona="marky"),
    ),
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
)


def by_id(job_id: str) -> JobSpec | None:
    for job in JOBS:
        if job.id == job_id:
            return job
    return None
