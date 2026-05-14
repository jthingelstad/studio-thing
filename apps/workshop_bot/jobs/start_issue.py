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
from datetime import datetime, timezone
from typing import Optional

from ..tools import db, s3
from ..tools.content import issue
from . import _base, update_draft

logger = logging.getLogger("workshop.jobs.start_issue")

NAME = "start-issue"

# The published archive lives here — used in the workshop.json pointer so
# Shortcuts have the eventual `archive_url` for the issue handy.
_ARCHIVE_BASE = "https://weekly.thingelstad.com/archive/"


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
            # Shortcut-authored (Jamie's iOS flow):
            "cover_jpg": f"{base}cover.jpg",
            "cover_json": f"{base}cover.json",
            "intro_md": f"{base}intro.md",
            "currently_json": f"{base}currently.json",
            # Bot-written, but their URLs are useful for previewing / sharing:
            "haiku_md": f"{base}haiku.md",
            "metadata_json": f"{base}metadata.json",
            "draft_md": f"{base}draft.md",
            "draft_html": f"{base}draft.html",
            "final_md": f"{base}final.md",
            "publish_md": f"{base}publish.md",
            "publish_html": f"{base}publish.html",
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
            f"`{type(exc).__name__}: {exc}` — try `/workshop issue update`.",
        )

    # Fire update-draft so the first draft has real content. It owns the
    # draft.md lock; start-issue never holds it, so there's no collision.
    sub = await update_draft.run(_base.JobContext(deps=ctx.deps, trigger="chained"))

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
    lines.append(f"- `update-draft`: {sub.message}")
    return _base.JobResult(
        True, "\n".join(lines),
        data={"issue_number": n, "window": window, "update_draft": sub.data,
              "workshop_pointer_url": pointer_url},
    )
