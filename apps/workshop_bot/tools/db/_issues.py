"""Issue windows + publishing-spine phase/cards (moved from store.py).

Newsletters are concurrent: several issue windows can be ``is_active = 1`` at
once (some in build, some in share). Each in-flight window is mirrored by a
``newsletter`` row in the generic ``productions`` registry (id ``WT{n}``), so
the slate / web app / feed see newsletters alongside the other production
types. ``issue_windows`` stays authoritative for the live publish path; the
mirror is kept current by the write helpers here.
"""

from __future__ import annotations

from typing import Any, Optional

from ..content import production_types as ptypes
from .connection import connect

_NEWSLETTER_SURFACE = ptypes.PRODUCTION_TYPES["newsletter"].surface


# ---------- issue windows (operator-set publishing schedule) ----------


def _mirror_newsletter_production(
    conn: Any,
    *,
    issue_number: int,
    phase: str,
    pub_date: str,
    status: str = "active",
    set_by: Optional[str] = None,
) -> None:
    """Upsert the ``productions`` registry row mirroring a newsletter window,
    inside the caller's open transaction. Preserves an existing title (so a
    web-edited title survives a re-start); only moves phase/status/dates."""
    n = int(issue_number)
    conn.execute(
        "INSERT INTO productions "
        "(id, production_type, seq, title, phase, status, due_at, pub_date, "
        " source, detail_issue_number, created_by, updated_by) "
        "VALUES ('WT'||?, 'newsletter', ?, 'WT'||?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "  phase=excluded.phase, "
        "  status=excluded.status, "
        "  due_at=excluded.due_at, "
        "  pub_date=excluded.pub_date, "
        "  detail_issue_number=excluded.detail_issue_number, "
        "  updated_at=datetime('now'), "
        "  updated_by=excluded.updated_by",
        (n, n, n, phase, status, pub_date, pub_date, _NEWSLETTER_SURFACE, n, set_by, set_by),
    )


def set_issue_window(
    *,
    issue_number: int,
    pub_date: str,
    end_date: str,
    start_date: str,
    day_count: int,
    set_by: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert this issue's row as an active in-flight window and mirror it into
    the ``productions`` registry.

    Newsletters are concurrent — this does NOT deactivate other active windows
    (the single-active model is retired). Returns the upserted window row.
    """
    with connect() as conn:
        # Autocommit connection (isolation_level=None) — bracket the window
        # upsert + the productions mirror into one transaction so the registry
        # never diverges from the window.
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO issue_windows "
                "(issue_number, pub_date, end_date, start_date, day_count, "
                " is_active, set_at, set_by) "
                "VALUES (?, ?, ?, ?, ?, 1, datetime('now'), ?) "
                "ON CONFLICT(issue_number) DO UPDATE SET "
                "  pub_date=excluded.pub_date, "
                "  end_date=excluded.end_date, "
                "  start_date=excluded.start_date, "
                "  day_count=excluded.day_count, "
                "  is_active=1, "
                "  phase='build', "
                "  set_at=datetime('now'), "
                "  set_by=excluded.set_by",
                (issue_number, pub_date, end_date, start_date, day_count, set_by),
            )
            _mirror_newsletter_production(
                conn,
                issue_number=issue_number,
                phase="build",
                pub_date=pub_date,
                status="active",
                set_by=set_by,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return get_issue_window(issue_number) or {}


def plan_issue_window(
    *,
    issue_number: int,
    pub_date: str,
    end_date: str,
    start_date: str,
    day_count: int,
    set_by: Optional[str] = None,
) -> dict[str, Any]:
    """Define a newsletter as *planned* — a DB row only, no workspace seeding.

    Like ``set_issue_window`` but seeds ``phase='planned'`` (not 'build') and
    mirrors a planned productions row. 'Start working' (start_working) later
    flips it to 'build' and seeds the pipeline. This is the web "create a future
    issue" path — defining one is just a row, per the rearchitecture."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO issue_windows "
                "(issue_number, pub_date, end_date, start_date, day_count, "
                " is_active, phase, set_at, set_by) "
                "VALUES (?, ?, ?, ?, ?, 1, 'planned', datetime('now'), ?) "
                "ON CONFLICT(issue_number) DO UPDATE SET "
                "  pub_date=excluded.pub_date, "
                "  end_date=excluded.end_date, "
                "  start_date=excluded.start_date, "
                "  day_count=excluded.day_count, "
                "  is_active=1, "
                "  set_at=datetime('now'), "
                "  set_by=excluded.set_by",
                (issue_number, pub_date, end_date, start_date, day_count, set_by),
            )
            _mirror_newsletter_production(
                conn,
                issue_number=issue_number,
                phase="planned",
                pub_date=pub_date,
                status="active",
                set_by=set_by,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return get_issue_window(issue_number) or {}


def get_active_issue_window(issue_number: Optional[int] = None) -> Optional[dict[str, Any]]:
    """Resolve an in-flight issue window.

    Pass ``issue_number`` to target a specific issue (the concurrency-safe
    path — entry points thread the number they operate on). With no argument,
    returns the single active window, or — when several are in flight — the
    most-recently-set one, preserving the legacy "the active issue" behaviour
    for un-threaded callers. None if nothing is in flight.

    Carries ``phase`` ('write' | 'build' | 'publish' | 'share')."""
    if issue_number is not None:
        return get_issue_window(int(issue_number))
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       phase, buttondown_id, absolute_url, set_at, set_by "
            "FROM issue_windows WHERE is_active = 1 "
            "ORDER BY set_at DESC, issue_number DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def list_active_issue_windows() -> list[dict[str, Any]]:
    """All in-flight newsletter windows (``is_active = 1``), newest set first.
    The concurrency-aware reader for the slate / status / feed."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       phase, buttondown_id, absolute_url, set_at, set_by "
            "FROM issue_windows WHERE is_active = 1 "
            "ORDER BY set_at DESC, issue_number DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_issue_window(issue_number: int) -> Optional[dict[str, Any]]:
    """Return one issue window by number (active or not)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, phase, buttondown_id, absolute_url, set_at, set_by "
            "FROM issue_windows WHERE issue_number = ?",
            (int(issue_number),),
        ).fetchone()
    return dict(row) if row else None


def set_issue_publish_record(
    issue_number: int, *, buttondown_id: str = "", absolute_url: str = ""
) -> None:
    """Stamp the publish record (buttondown_id / absolute_url) on the issue
    window — written by `publish buttondown` when the issue ships. Only
    non-empty values overwrite, so a re-run that omits one keeps the prior."""
    n = int(issue_number)
    with connect() as conn:
        if buttondown_id:
            conn.execute(
                "UPDATE issue_windows SET buttondown_id = ? WHERE issue_number = ?",
                (buttondown_id, n),
            )
        if absolute_url:
            conn.execute(
                "UPDATE issue_windows SET absolute_url = ? WHERE issue_number = ?",
                (absolute_url, n),
            )


# ---------- publishing-spine phase + per-phase cards ----------

# Newsletter phase vocabulary, owned by tools/content/production_types.py.
_ISSUE_PHASES = ptypes.phases_for("newsletter")  # ('write','build','publish','share')


def set_issue_phase(issue_number: int, phase: str) -> None:
    """Set an issue's publishing-spine phase and mirror it to the productions
    registry. ``phase`` ∈ ('write','build','publish','share'); see
    docs/publishing-process.md — `mark built` flips build→publish."""
    if phase not in _ISSUE_PHASES:
        raise ValueError(f"phase must be one of {_ISSUE_PHASES}; got {phase!r}")
    n = int(issue_number)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE issue_windows SET phase = ? WHERE issue_number = ?",
                (phase, n),
            )
            conn.execute(
                "UPDATE productions SET phase = ?, updated_at = datetime('now') WHERE id = 'WT'||?",
                (phase, n),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


# The per-phase card handles (issue_cards) were retired with the Discord phase
# cards — production status is the web scoreboard now. The table is dropped by a
# migration; these helpers are gone.


def get_latest_issue() -> Optional[dict[str, Any]]:
    """Return the most-recently-published issue (highest number) from the
    `issues` table — i.e. the issue currently in the **Share** phase. None if
    no issue has been filed yet."""
    with connect() as conn:
        row = conn.execute(
            "SELECT number, subject, slug, description, publish_date, absolute_url, "
            "       buttondown_id, audio_url, notable_count, briefly_count, link_count, filed_at "
            "FROM issues ORDER BY number DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def list_issue_windows(*, limit: int = 12) -> list[dict[str, Any]]:
    """Return recent issue windows, newest issue number first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, set_at, set_by "
            "FROM issue_windows ORDER BY issue_number DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]
