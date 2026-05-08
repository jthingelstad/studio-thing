"""Declarative scheduled jobs.

Each ``JobSpec`` is just a cron string and a Python function. The function
runs at the scheduled time and does whatever it needs to: pull data,
format a report, post to a channel, write S3, save memory.

The four personas each get a **heartbeat** — a scheduled agent turn
firing on a cadence with that persona's ``heartbeat.md`` prompt. The
default is ``PASS``; heartbeats only post when the persona has
something concrete to surface. Heartbeats use ``handlers.heartbeat``
via ``functools.partial`` so the dispatcher signature stays the same.

A few high-care **rituals** still run as bespoke jobs (Friday curation,
Monday subscriber report, Thursday member.json) — those are deliberate
weekly artifacts that benefit from a tight prompt rather than a
default-PASS heartbeat.

To add a job: write a new handler function in ``handlers.py``, add a
``JobSpec`` here, restart the bot.
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
    # surface. Folded the lighter previous jobs (linky-wednesday-check,
    # linky-popular-scan, linky-research-unread, marky-daily-engagement,
    # eddy-saturday-prep) into these.
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

    # ---------- Rituals (preserved) ----------
    # High-care, deliberately preserved scheduled jobs. Each has its own
    # bespoke prompt under handlers.<name> rather than a generic
    # heartbeat — these produce specific weekly artifacts that benefit
    # from tight, fixed instructions.
    JobSpec(
        id="linky-friday-curation",
        cron="0 16 * * 5",                               # Friday 16:00 Central.
        func=handlers.linky_friday_curation,
    ),
    JobSpec(
        id="marky-weekly-subscriber-report",
        cron="0 11 * * 1",                               # Monday 11:00 Central.
        func=handlers.marky_weekly_subscriber_report,
    ),
    JobSpec(
        id="patty-thursday-member-json",
        cron="0 18 * * 4",                               # Thursday 18:00 Central — member.json write.
        func=handlers.patty_thursday_member_json,
    ),
)


def by_id(job_id: str) -> JobSpec | None:
    for job in JOBS:
        if job.id == job_id:
            return job
    return None
