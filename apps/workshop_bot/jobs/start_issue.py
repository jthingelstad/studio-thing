"""``start-issue`` — bootstrap a new in-flight issue.

Records the issue window in workshop.db, seeds ``draft.md`` from the
starter template (which creates the per-issue S3 prefix), schedules the
week's Currently nudges (Mon + Wed evenings via ``follow_ups``), and
fires ``update-draft`` synchronously so the first draft has real
content. The only job that takes the issue number explicitly.

Note: ``start-issue`` does not hold the ``draft.md`` lock — the issue is
brand new, nothing else is in flight for it, and the chained
``update-draft`` needs to acquire that lock itself.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..tools import db
from ..tools.content import issue
from . import _base, sync_issue

logger = logging.getLogger("workshop.jobs.start_issue")

NAME = "start-issue"

# The published archive lives here — used in the workshop.json pointer so
# Shortcuts have the eventual `archive_url` for the issue handy.
_ARCHIVE_BASE = "https://weekly.thingelstad.com/archive/"

# Currently-nudge schedule: Mon + Wed of the issue cycle, 17:00 local
# Chicago. pub_date is the publishing Saturday; the ship target is
# Thursday night (pub_date - 2 days), so:
#   Mon = pub_date - 5 days
#   Wed = pub_date - 3 days
# Times are stored as naive-ISO strings matching follow_up._parse_when's
# convention (``datetime.now()`` comparison is naive-local).
_CURRENTLY_LOCAL_TZ = ZoneInfo("America/Chicago")
_CURRENTLY_NUDGE_HOUR = 17
_CURRENTLY_NUDGES: tuple[tuple[str, int, str], ...] = (
    (
        "mon",
        5,
        (
            "Currently opener for WT{n}. Call `currently__list_entries` to see what's "
            "filled and `currently__suggest_stale(k=3)` for ideas. Pick one stale (or "
            "never-used) type and ask Jamie a short, specific question about it in "
            "#editorial. When he replies, call `currently__set` with his words "
            "(values may include markdown links — pass them through verbatim)."
        ),
    ),
    (
        "wed",
        3,
        (
            "Currently mid-week check for WT{n}. Publish target is Thursday night. "
            "Look at `currently__list_entries`; if it's still sparse, pick another "
            "stale type and prompt. If Jamie's already been responsive, thank him + "
            "ask if anything else feels relevant. Don't repeat the type you asked "
            "about on Monday — check his recent #editorial replies."
        ),
    ),
)


def _currently_nudge_due_at(pub_date_iso: str, days_before: int) -> Optional[str]:
    """Compute the ISO naive-local datetime for one nudge — None when
    the date can't be parsed."""
    try:
        pub = date.fromisoformat(pub_date_iso)
    except (TypeError, ValueError):
        return None
    target_date = pub - timedelta(days=int(days_before))
    aware = datetime.combine(
        target_date, time(_CURRENTLY_NUDGE_HOUR, 0, 0), _CURRENTLY_LOCAL_TZ,
    )
    # follow_ups.due_at uses naive-local ISO; strip tzinfo so the
    # sweep's ``datetime.now()`` comparison matches.
    return aware.replace(tzinfo=None).isoformat(timespec="seconds")


def _schedule_currently_nudges(
    *, issue_number: int, pub_date_iso: str, set_by: Optional[str],
) -> list[dict]:
    """Insert the Mon + Wed Currently nudges into ``follow_ups``. Skips
    any whose computed time is already in the past (a late start-issue
    invocation gets only the remaining ones). Returns the inserted rows."""
    inserted: list[dict] = []
    now_iso = datetime.now().isoformat(timespec="seconds")
    for label, days_before, note_tpl in _CURRENTLY_NUDGES:
        due_at = _currently_nudge_due_at(pub_date_iso, days_before)
        if due_at is None or due_at <= now_iso:
            logger.info(
                "start-issue: skipping %s currently nudge for WT%d — due_at %r already passed",
                label, issue_number, due_at,
            )
            continue
        try:
            fid = db.insert_follow_up(
                persona="eddy",
                trigger_kind="time",
                note=note_tpl.format(n=issue_number),
                due_at=due_at,
                channel_env=None,  # defaults to eddy's #editorial
                created_by=(set_by or "start-issue"),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "start-issue: couldn't insert %s currently nudge for WT%d", label, issue_number,
            )
            continue
        row = db.get_follow_up(int(fid))
        if row is not None:
            inserted.append(row)
    return inserted


async def define(
    ctx: "_base.JobContext",
    *,
    number,
    pub_date: str,
    day_count: int = 7,
    set_by: Optional[str] = None,
) -> "_base.JobResult":
    """Define a newsletter as *planned* — a DB row only, no workspace seeding.
    The web "create newsletter" path. Validates the number + Saturday pub_date."""
    try:
        n = int(number)
    except (TypeError, ValueError):
        return _base.JobResult(False, f"❌ issue number must be an integer; got {number!r}")
    if n <= 0:
        return _base.JobResult(False, f"❌ issue number must be positive; got {n}")
    try:
        window = issue.compute_window(pub_date, int(day_count))
    except issue.IssueWindowError as exc:
        return _base.JobResult(False, f"❌ {exc}")
    try:
        db.plan_issue_window(
            issue_number=n,
            pub_date=window["pub_date"],
            end_date=window["end_date"],
            start_date=window["start_date"],
            day_count=window["day_count"],
            set_by=set_by or "define",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("define: db write failed for #%d", n)
        return _base.JobResult(
            False, f"❌ couldn't save the issue: `{type(exc).__name__}: {exc}`"
        )
    return _base.JobResult(
        True,
        f"🗓️ Issue **WT{n}** defined (planned) — pub {window['pub_date']}. "
        f"Start working on it to open the workspace.",
        data={"issue_number": n, "window": window, "phase": "planned"},
    )


async def start_working(
    ctx: "_base.JobContext", n: int, *, set_by: Optional[str] = None
) -> "_base.JobResult":
    """Move a planned newsletter into **build**: set the phase, schedule the
    Currently nudges, and run the first upstream sync. The DB is the draft —
    there is no workspace seeding, no draft.md, and no Shortcuts pointer
    (the iOS-Shortcuts pipeline is retired; the web app is the work
    surface)."""
    n = int(n)
    window = db.get_active_issue_window(n)
    if window is None:
        return _base.JobResult(False, f"❌ no issue window for WT{n} — define it first.")
    db.set_issue_phase(n, "build")
    window = db.get_active_issue_window(n)

    nudges = _schedule_currently_nudges(
        issue_number=n, pub_date_iso=window["pub_date"], set_by=set_by,
    )

    sub = await sync_issue.run(_base.JobContext(deps=ctx.deps, trigger="chained"))

    days_word = "day" if window["day_count"] == 1 else "days"
    lines = [
        f"✅ Issue **WT{n}** is now in flight (build).",
        f"- Publish: **{window['pub_date']}** (Sat)",
        f"- Content cutoff (end_date): **{window['end_date']}**",
        f"- Window start (prior cutoff): **{window['start_date']}**",
        f"- Span: **{window['day_count']} {days_word}**",
    ]
    if nudges:
        when_summary = " · ".join(
            f"`#{row['id']}` {(row.get('due_at') or '')[:16].replace('T', ' ')}"
            for row in nudges
        )
        lines.append(f"- Currently nudges scheduled: {when_summary}")
    lines.append(f"- `sync-issue`: {sub.message}")
    return _base.JobResult(
        True, "\n".join(lines),
        data={"issue_number": n, "window": window, "sync_issue": sub.data,
              "currently_nudges": [row["id"] for row in nudges]},
    )


async def run(
    ctx: "_base.JobContext",
    *,
    number,
    pub_date: str,
    day_count: int = 7,
    set_by: Optional[str] = None,
) -> "_base.JobResult":
    """One-shot define + start_working (the legacy `/scout issue start`)."""
    res = await define(ctx, number=number, pub_date=pub_date, day_count=day_count, set_by=set_by)
    if not res.ok:
        return res
    n = int(res.data["issue_number"])
    return await start_working(ctx, n, set_by=set_by)
