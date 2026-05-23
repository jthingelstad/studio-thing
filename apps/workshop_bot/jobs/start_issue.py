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
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from ..tools import db, s3
from ..tools.content import issue
from . import _base, update_draft

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


def build_workshop_pointer(*, issue_number: int, window: dict, set_by: Optional[str], bucket: str) -> dict:
    """Shape the JSON the iOS Shortcuts read from
    ``https://{bucket}/weekly-thing/workshop.json`` to know the current
    in-flight issue. Has the window, the predictable workspace URLs (the
    Shortcuts upload to the first four; the bot writes the rest), and the
    issue's future archive URL."""
    n = int(issue_number)
    base = f"https://{bucket}/weekly-thing/{n}/"
    return {
        "issue_number": n,
        "pub_date": window["pub_date"],
        "end_date": window["end_date"],
        "start_date": window["start_date"],
        "day_count": int(window["day_count"]),
        "workspace_url": base,
        "workspace_prefix": f"weekly-thing/{n}/",
        "archive_url": f"{_ARCHIVE_BASE}{n}/",
        "reddit_tag_url": (
            f"https://www.reddit.com/r/weeklything/?f="
            f"flair_name%3A%22Weekly%20Thing%20{n}%22"
        ),
        "files": {
            # ----- Author-content atoms (live under atoms/) ---------
            # Shortcut-authored (Jamie's iOS flow): cover, intro, outro.
            # Currently is DB-backed (workshop.db); edited via Eddy or
            # `/eddy currently …` — not surfaced here.
            "cover_jpg": f"{base}cover.jpg",
            "cover_json": f"{base}atoms/cover.json",
            "intro_md": f"{base}atoms/intro.md",
            "outro_md": f"{base}atoms/outro.md",
            # Bot-composed atoms (compose-haiku, compose-meta,
            # compose-cta, compose-closer, create-final).
            "haiku_md": f"{base}atoms/haiku.md",
            "metadata_json": f"{base}atoms/metadata.json",
            "thesis_md": f"{base}atoms/thesis.md",
            "cta_1_md": f"{base}atoms/cta-1.md",
            "cta_2_md": f"{base}atoms/cta-2.md",
            "thanks_1_md": f"{base}atoms/thanks-1.md",
            "closer_md": f"{base}atoms/closer.md",
            # ----- Daily-rendered artifacts (live at issue root) ----
            # Produced by tools/renderers on every /eddy issue update
            # tick. final.md is gone — section ordering + promotions
            # live in workshop.db's issue_items table now.
            "draft_md": f"{base}draft.md",
            "draft_html": f"{base}draft.html",
            "archive_md": f"{base}archive.md",
            "links_json": f"{base}links.json",
            "buttondown_md": f"{base}buttondown.md",
            "buttondown_html": f"{base}buttondown.html",
            "transcript_full_txt": f"{base}transcript-full.txt",
            "proposal_html": f"{base}proposal.html",
        },
        "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "set_by": set_by or "start-issue",
    }


async def run(
    ctx: "_base.JobContext",
    *,
    number,
    pub_date: str,
    day_count: int = 7,
    set_by: Optional[str] = None,
) -> "_base.JobResult":
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
        db.set_issue_window(
            issue_number=n,
            pub_date=window["pub_date"],
            end_date=window["end_date"],
            start_date=window["start_date"],
            day_count=window["day_count"],
            set_by=set_by or "start-issue",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("start-issue: db write failed for #%d", n)
        return _base.JobResult(
            False, f"❌ couldn't save the issue window: `{type(exc).__name__}: {exc}`"
        )

    # Refresh the workshop pointer JSON Shortcuts read to discover the
    # current in-flight issue. Best-effort — a hiccup here doesn't block the
    # job; surface it in the result so Jamie knows Shortcuts may be stale.
    pointer_url: Optional[str] = None
    pointer_warning: Optional[str] = None
    try:
        from ..tools import s3 as _s3  # local alias so the import line above stays read-only
        pointer = build_workshop_pointer(
            issue_number=n, window=window, set_by=set_by, bucket=_s3._bucket(),
        )
        res = _s3.write_workshop_pointer(pointer)
        pointer_url = res.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.warning("start-issue: workshop.json write failed for #%d: %s", n, exc)
        pointer_warning = f"`{type(exc).__name__}: {exc}`"

    # Seed draft.md from the starter template — this also creates the S3
    # prefix weekly-thing/{n}/ if it didn't exist.
    try:
        s3.write_issue_file(n, "draft.md", _base.starter_template())
    except Exception as exc:  # noqa: BLE001
        logger.exception("start-issue: failed to seed draft.md for #%d", n)
        return _base.JobResult(
            False,
            f"⚠️ window recorded for #{n}, but couldn't seed `draft.md`: "
            f"`{type(exc).__name__}: {exc}` — try `/eddy issue update`.",
        )

    # Currently nudges — Mon + Wed of the cycle, posted in #editorial by
    # follow-up-sweep when each row's due_at passes. Late starts skip past
    # rows. Best-effort: a DB hiccup here doesn't block the job.
    nudges = _schedule_currently_nudges(
        issue_number=n, pub_date_iso=window["pub_date"], set_by=set_by,
    )

    # Fire update-draft so the first draft has real content. It owns the
    # draft.md lock; start-issue never holds it, so there's no collision.
    sub = await update_draft.run(_base.JobContext(deps=ctx.deps, trigger="chained"))

    # Post + pin the Build card so the one live content surface exists from the
    # start of the cycle (phase='build'). update-draft (just fired) also
    # refreshes it; this guarantees it lands even if that hiccuped.
    try:
        from . import build_card
        await build_card.post_or_update(ctx, n, window=window)
    except Exception:  # noqa: BLE001
        logger.exception("start-issue: Build card post failed for #%d", n)

    days_word = "day" if window["day_count"] == 1 else "days"
    pointer_line = (
        f"- Shortcuts pointer: 📄 {pointer_url}" if pointer_url
        else f"- ⚠️ couldn't refresh `workshop.json` for Shortcuts: {pointer_warning}"
        if pointer_warning else None
    )
    lines = [
        f"✅ Issue **#{n}** is now in flight.",
        f"- Publish: **{window['pub_date']}** (Sat)",
        f"- Content cutoff (end_date): **{window['end_date']}**",
        f"- Window start (prior cutoff): **{window['start_date']}**",
        f"- Span: **{window['day_count']} {days_word}**",
    ]
    if pointer_line:
        lines.append(pointer_line)
    if nudges:
        when_summary = " · ".join(
            f"`#{row['id']}` {(row.get('due_at') or '')[:16].replace('T', ' ')}"
            for row in nudges
        )
        lines.append(f"- Currently nudges scheduled: {when_summary}")
    lines.append(f"- `update-draft`: {sub.message}")
    return _base.JobResult(
        True, "\n".join(lines),
        data={"issue_number": n, "window": window, "update_draft": sub.data,
              "workshop_pointer_url": pointer_url,
              "currently_nudges": [row["id"] for row in nudges]},
    )
