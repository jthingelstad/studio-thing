"""Productions — the generic, multi-type, multi-instance production registry.

One row per production unit of any type (newsletter / article / podcast /
project); several of several types run concurrently, each in its own phase.
This is the spine that supersedes the single-active ``issue_windows`` model for
the registry view. ``issue_windows`` stays as the newsletter's working/detail
table (linked by ``detail_issue_number``); the live newsletter publish path
still reads it.

The per-type phase vocabulary is owned in code by
``tools/content/production_types.py``; every write here validates against it.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..content import production_types as ptypes
from .connection import connect

_COLUMNS = (
    "id, production_type, seq, title, phase, status, due_at, pub_date, source, "
    "details, detail_issue_number, created_at, updated_at, created_by, updated_by"
)


def _row(row: Any) -> dict[str, Any]:
    """Map a sqlite Row to a dict, parsing the ``details`` JSON blob back."""
    d = dict(row)
    raw = d.get("details")
    if raw:
        try:
            d["details"] = json.loads(raw)
        except TypeError, ValueError:
            d["details"] = None
    else:
        d["details"] = None
    return d


def next_production_seq(production_type: str) -> int:
    """The next per-type ordinal (``MAX(seq)+1``, starting at 1). Newsletters pass
    ``seq`` explicitly (= the issue number); other types auto-assign via this."""
    with connect() as conn:
        row = conn.execute(
            "SELECT MAX(seq) AS m FROM productions WHERE production_type = ?",
            (production_type,),
        ).fetchone()
    return int(row["m"]) + 1 if row and row["m"] is not None else 1


def create_production(
    *,
    production_type: str,
    title: str,
    seq: Optional[int] = None,
    phase: Optional[str] = None,
    status: str = "active",
    due_at: Optional[str] = None,
    pub_date: Optional[str] = None,
    source: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    detail_issue_number: Optional[int] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    """Create a production row and return it.

    ``id`` is computed as ``{prefix}{seq}`` (e.g. ``WT350``, ``ART7``). ``seq``
    is required-ish for newsletters (pass the issue number); for other types it
    auto-assigns the next per-type ordinal. ``phase`` defaults to the type's
    first phase and is validated against the type's vocabulary.
    """
    pt = ptypes.get_type(production_type)  # raises ValueError on unknown type
    if not ptypes.is_valid_status(status):
        raise ValueError(f"status {status!r} not valid; one of {ptypes.STATUSES}")
    if seq is None:
        seq = next_production_seq(production_type)
    seq = int(seq)
    phase = phase or ptypes.default_phase(production_type)
    if not ptypes.is_valid_phase(production_type, phase):
        raise ValueError(f"phase {phase!r} not valid for {production_type!r}; one of {pt.phases}")
    production_id = f"{pt.id_prefix}{seq}"
    src = pt.surface if source is None else source
    details_json = json.dumps(details) if details else None
    with connect() as conn:
        conn.execute(
            "INSERT INTO productions "
            "(id, production_type, seq, title, phase, status, due_at, pub_date, "
            " source, details, detail_issue_number, created_by, updated_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                production_id,
                production_type,
                seq,
                title,
                phase,
                status,
                due_at,
                pub_date,
                src,
                details_json,
                detail_issue_number,
                created_by,
                created_by,
            ),
        )
    return get_production(production_id) or {}


def get_production(production_id: str) -> Optional[dict[str, Any]]:
    """Return one production by id, or None. ``details`` is parsed back to a dict."""
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM productions WHERE id = ?",
            (production_id,),
        ).fetchone()
    return _row(row) if row else None


def list_productions(
    *,
    production_type: Optional[str] = None,
    status: Optional[str] = None,
    phase: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return productions, optionally filtered by type/status/phase. Active first,
    then soonest due (nulls last), then newest seq."""
    clauses, params = [], []
    if production_type is not None:
        clauses.append("production_type = ?")
        params.append(production_type)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if phase is not None:
        clauses.append("phase = ?")
        params.append(phase)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(int(limit))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM productions{where} "
            "ORDER BY (status = 'active') DESC, due_at IS NULL, due_at, seq DESC "
            "LIMIT ?",
            params,
        ).fetchall()
    return [_row(r) for r in rows]


def update_production(
    production_id: str,
    *,
    title: Optional[str] = None,
    due_at: Optional[str] = None,
    pub_date: Optional[str] = None,
    status: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    updated_by: Optional[str] = None,
) -> dict[str, Any]:
    """Update only the fields passed (non-None). Always bumps ``updated_at``.
    ``details`` replaces the stored blob wholesale (caller merges if needed)."""
    if status is not None and not ptypes.is_valid_status(status):
        raise ValueError(f"status {status!r} not valid; one of {ptypes.STATUSES}")
    sets, params = [], []
    if title is not None:
        sets.append("title = ?")
        params.append(title)
    if due_at is not None:
        sets.append("due_at = ?")
        params.append(due_at)
    if pub_date is not None:
        sets.append("pub_date = ?")
        params.append(pub_date)
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if details is not None:
        sets.append("details = ?")
        params.append(json.dumps(details))
    if updated_by is not None:
        sets.append("updated_by = ?")
        params.append(updated_by)
    sets.append("updated_at = datetime('now')")
    params.append(production_id)
    with connect() as conn:
        conn.execute(
            f"UPDATE productions SET {', '.join(sets)} WHERE id = ?",
            params,
        )
    return get_production(production_id) or {}


def set_production_phase(
    production_id: str, phase: str, *, updated_by: Optional[str] = None
) -> dict[str, Any]:
    """Move a production to ``phase``, validated against its type's vocabulary."""
    row = get_production(production_id)
    if not row:
        raise ValueError(f"no such production: {production_id!r}")
    ptype = row["production_type"]
    if not ptypes.is_valid_phase(ptype, phase):
        raise ValueError(
            f"phase {phase!r} not valid for {ptype!r}; one of {ptypes.phases_for(ptype)}"
        )
    with connect() as conn:
        conn.execute(
            "UPDATE productions SET phase = ?, updated_at = datetime('now'), "
            "updated_by = COALESCE(?, updated_by) WHERE id = ?",
            (phase, updated_by, production_id),
        )
    return get_production(production_id) or {}
