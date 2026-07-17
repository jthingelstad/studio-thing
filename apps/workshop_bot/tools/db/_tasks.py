"""Newsletter issue tasks.

An issue is phase + content + tasks. Each task has an owner (``jamie`` or
``eddy``) and a status.
"""

from __future__ import annotations

from typing import Any, Optional

from .connection import connect

TASK_OWNERS = ("jamie", "eddy")
TASK_STATUSES = ("todo", "doing", "done", "blocked")

_COLUMNS = (
    "id, production_id, title, owner, status, origin, phase, detail, "
    "created_at, updated_at, created_by"
)


def add_task(
    production_id: str,
    title: str,
    *,
    owner: str = "jamie",
    status: str = "todo",
    phase: Optional[str] = None,
    detail: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    """Add an ad-hoc / assigned task to a production. Returns the new row."""
    if owner not in TASK_OWNERS:
        raise ValueError(f"owner must be one of {TASK_OWNERS}; got {owner!r}")
    if status not in TASK_STATUSES:
        raise ValueError(f"status must be one of {TASK_STATUSES}; got {status!r}")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO production_tasks "
            "(production_id, title, owner, status, origin, phase, detail, created_by) "
            "VALUES (?, ?, ?, ?, 'added', ?, ?, ?)",
            (production_id, title, owner, status, phase, detail, created_by),
        )
        task_id = int(cur.lastrowid)
    return get_task(task_id) or {}


def get_task(task_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM production_tasks WHERE id = ?", (int(task_id),)
        ).fetchone()
    return dict(row) if row else None


def list_tasks(
    production_id: str, *, status: Optional[str] = None, owner: Optional[str] = None
) -> list[dict[str, Any]]:
    """The added tasks for a production, open first (todo/doing before done)."""
    clauses, params = ["production_id = ?"], [production_id]
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if owner is not None:
        clauses.append("owner = ?")
        params.append(owner)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM production_tasks WHERE {' AND '.join(clauses)} "
            "ORDER BY (status = 'done'), (status = 'blocked'), id",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def list_tasks_for_owner(owner: str, *, status: Optional[str] = "todo") -> list[dict[str, Any]]:
    """Open tasks assigned to one owner across all productions — the agent's
    'what's mine to do' queue (used by the proactive layer)."""
    clauses, params = ["owner = ?"], [owner]
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM production_tasks WHERE {' AND '.join(clauses)} ORDER BY id",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def update_task(
    task_id: int,
    *,
    title: Optional[str] = None,
    owner: Optional[str] = None,
    status: Optional[str] = None,
    phase: Optional[str] = None,
    detail: Optional[str] = None,
) -> dict[str, Any]:
    """Update only the fields passed. Validates owner/status."""
    if owner is not None and owner not in TASK_OWNERS:
        raise ValueError(f"owner must be one of {TASK_OWNERS}; got {owner!r}")
    if status is not None and status not in TASK_STATUSES:
        raise ValueError(f"status must be one of {TASK_STATUSES}; got {status!r}")
    sets, params = [], []
    for col, val in (
        ("title", title),
        ("owner", owner),
        ("status", status),
        ("phase", phase),
        ("detail", detail),
    ):
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)
    if not sets:
        return get_task(task_id) or {}
    sets.append("updated_at = datetime('now')")
    params.append(int(task_id))
    with connect() as conn:
        conn.execute(f"UPDATE production_tasks SET {', '.join(sets)} WHERE id = ?", params)
    return get_task(task_id) or {}


def complete_task(task_id: int) -> dict[str, Any]:
    return update_task(task_id, status="done")


def delete_task(task_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM production_tasks WHERE id = ?", (int(task_id),))
