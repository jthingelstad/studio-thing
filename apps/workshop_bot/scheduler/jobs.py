"""Declarative scheduled jobs.

Each ``JobSpec`` is just a cron string and a Python function. The function
runs at the scheduled time and does whatever it needs to: pull data,
format a report, post to a channel, write S3, save memory. Most jobs
are pure code (engagement reports, popular-feed scans, subscriber
deltas) — fetch + format + post, no LLM tokens spent.

A few jobs *do* benefit from LLM judgment — composing a fresh CTA,
doing a real curation pass, picking out which preferences are worth
surfacing on Saturday morning. Those handlers call ``bot.core(...)``
explicitly. The split is deliberate: the LLM is a tool the handler
reaches for when judgment is needed, not the default execution path
for every cron tick.

To add a job: write a new handler function in ``handlers.py``, add a
``JobSpec`` here, restart the bot.
"""

from __future__ import annotations

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
    # ---------- Linky ----------
    # Three jobs: a Wednesday queue check (pure code), a Friday curation
    # pass (LLM — needs judgment), and a popular-feed scan (pure code).
    JobSpec(
        id="linky-wednesday-check",
        cron="30 10 * * 3",
        func=handlers.linky_wednesday_check,
    ),
    JobSpec(
        id="linky-friday-curation",
        cron="0 16 * * 5",
        func=handlers.linky_friday_curation,
    ),
    JobSpec(
        id="linky-popular-scan",
        cron="0 12 * * 1,4",  # Mon + Thu noon Central
        func=handlers.linky_popular_scan,
    ),

    # ---------- Marky ----------
    # Daily and weekly reports are pure data. Thursday's member.json
    # write is composition — uses the LLM.
    JobSpec(
        id="marky-daily-engagement",
        cron="0 9 * * *",
        func=handlers.marky_daily_engagement,
    ),
    JobSpec(
        id="marky-weekly-subscriber-report",
        cron="0 11 * * 1",
        func=handlers.marky_weekly_subscriber_report,
    ),
    JobSpec(
        id="marky-thursday-member-json",
        cron="0 18 * * 4",
        func=handlers.marky_thursday_member_json,
    ),

    # ---------- Eddy ----------
    # Saturday prep is light and benefits from LLM judgment ("which of
    # these preferences are still relevant?"), but the handler can also
    # run as pure recall + post if the LLM call fails.
    JobSpec(
        id="eddy-saturday-prep",
        cron="0 8 * * 6",
        func=handlers.eddy_saturday_prep,
    ),
)


def by_id(job_id: str) -> JobSpec | None:
    for job in JOBS:
        if job.id == job_id:
            return job
    return None
