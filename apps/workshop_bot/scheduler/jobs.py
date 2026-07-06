"""Declarative scheduled jobs.

Studio is now the newsletter publishing website. The scheduled surface is
deliberately small: keep the issue's inbound source mirror fresh, and keep
Eddy's explicit follow-ups alive. Everything else belongs behind a web action.
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
    JobSpec(
        id="sync-issue-daily",
        cron="0 17 * * *",                               # Daily 17:00 Central — refreshes issue_items
                                                         # from Pinboard + micro.blog (the DB is the
                                                         # draft; this is its inbound mirror). PASSes
                                                         # cleanly if no issue is in flight.
        func=functools.partial(handlers.content_job, job="sync-issue"),
    ),
    JobSpec(
        id="follow-up-sweep",
        cron="23 * * * *",                               # Hourly at :23. Fires due follow-ups —
                                                         # Eddy commitments ("I'll check in
                                                         # tomorrow evening", "when we hit 387"):
                                                         # runs Eddy's agent loop with the
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
