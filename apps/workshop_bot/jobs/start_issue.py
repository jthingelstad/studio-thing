"""``start-issue`` — bootstrap a new in-flight issue.

Records the issue window in workshop.db, seeds ``draft.md`` from the
starter template (which creates the per-issue S3 prefix), and fires
``update-draft`` synchronously so the first draft has real content. The
only job that takes the issue number explicitly.

Note: ``start-issue`` does not hold the ``draft.md`` lock — the issue is
brand new, nothing else is in flight for it, and the chained
``update-draft`` needs to acquire that lock itself.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..tools import db, issue, s3
from . import _base, update_draft

logger = logging.getLogger("workshop.jobs.start_issue")

NAME = "start-issue"


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

    # Seed draft.md from the starter template — this also creates the S3
    # prefix weekly-thing/{n}/ if it didn't exist.
    try:
        s3.write_issue_file(n, "draft.md", _base.starter_template())
    except Exception as exc:  # noqa: BLE001
        logger.exception("start-issue: failed to seed draft.md for #%d", n)
        return _base.JobResult(
            False,
            f"⚠️ window recorded for #{n}, but couldn't seed `draft.md`: "
            f"`{type(exc).__name__}: {exc}` — try `/workshop issue update`.",
        )

    # Fire update-draft so the first draft has real content. It owns the
    # draft.md lock; start-issue never holds it, so there's no collision.
    sub = await update_draft.run(_base.JobContext(deps=ctx.deps, trigger="chained"))

    days_word = "day" if window["day_count"] == 1 else "days"
    msg = (
        f"✅ Issue **#{n}** is now in flight.\n"
        f"- Publish: **{window['pub_date']}** (Sat)\n"
        f"- Content cutoff (end_date): **{window['end_date']}**\n"
        f"- Window start (prior cutoff): **{window['start_date']}**\n"
        f"- Span: **{window['day_count']} {days_word}**\n"
        f"- `update-draft`: {sub.message}"
    )
    return _base.JobResult(
        True, msg, data={"issue_number": n, "window": window, "update_draft": sub.data}
    )
