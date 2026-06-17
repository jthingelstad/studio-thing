"""In-flight issue window — operator-set, persisted in SQLite.

Replaces the old auto-derived resolver (S3 folder names + corpus
latest). Jamie sets the active window via the ``/scout issue start``
slash command; agents read it via ``issue__current_window`` and look up
historical windows via ``issue__list_windows``.

Date semantics
--------------
``pub_date``     YYYY-MM-DD, must be a Saturday — the day the issue
                 is published (for display; actual send may slip to
                 Sunday).
``end_date``     ``pub_date - 1 day`` — the content cutoff for this
                 issue.
``start_date``   ``end_date - day_count days`` — the previous issue's
                 cutoff. Items whose timestamp is strictly after
                 ``start_date`` and not after ``end_date`` belong to
                 this issue's content window.
``day_count``    Almost always 7. 14 for double issues. Any positive
                 integer is accepted.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .. import db


class IssueWindowError(ValueError):
    """Raised when ``/scout issue start`` arguments don't validate."""


def compute_window(pub_date_iso: str, day_count: int) -> dict[str, Any]:
    """Validate inputs and derive the full window dict.

    ``pub_date_iso`` must parse as YYYY-MM-DD on a Saturday.
    ``day_count`` must be a positive integer.
    """
    raw = (pub_date_iso or "").strip()
    try:
        pub = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise IssueWindowError(
            f"pub_date must be YYYY-MM-DD; got {pub_date_iso!r}"
        ) from exc
    if pub.weekday() != 5:  # 0=Mon … 5=Sat … 6=Sun
        raise IssueWindowError(
            f"pub_date {raw} is a {pub.strftime('%A')}; must be Saturday"
        )
    try:
        n = int(day_count)
    except (TypeError, ValueError) as exc:
        raise IssueWindowError(
            f"day_count must be a positive integer; got {day_count!r}"
        ) from exc
    if n <= 0:
        raise IssueWindowError(
            f"day_count must be a positive integer; got {n}"
        )
    end = pub - timedelta(days=1)
    start = end - timedelta(days=n)
    return {
        "pub_date": pub.isoformat(),
        "end_date": end.isoformat(),
        "start_date": start.isoformat(),
        "day_count": n,
    }


def t_current_issue_window(deps) -> dict[str, Any]:
    """Return the active issue window, or an error if none is set."""
    row = db.get_active_issue_window()
    if row is None:
        return {
            "error": (
                "No active issue window. Jamie sets this via "
                "/scout issue start <number> <YYYY-MM-DD> <day_count>."
            ),
        }
    return row


def t_list_issue_windows(deps, limit: int = 12) -> list[dict[str, Any]]:
    """Return recent issue windows (newest issue number first)."""
    return db.list_issue_windows(limit=int(limit))
