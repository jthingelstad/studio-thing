"""Seeds — Jamie's idea garden, tended by Eddy.

A seed is a snippet of something Jamie might write. Eddy curates, tags,
clusters, merges/mutates (suggestions on the *idea*, never his prose), connects
each to his archive, and routes ripe clusters to a production type. A seed
graduates into an article/podcast production; Jamie writes the piece.
"""

from __future__ import annotations

from typing import Any, Optional

from .connection import connect

_SEED_COLS = ("id, body, title, source, tags, cluster_id, status, graduated_to, "
              "created_at, updated_at, created_by")
_CLUSTER_COLS = ("id, label, note, suggested_type, status, graduated_to, "
                 "created_at, updated_at")


# ---------- seeds ----------

def seed_add(body: str, *, title: Optional[str] = None, source: str = "discord",
             tags: Optional[str] = None, created_by: Optional[str] = None) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO seeds (body, title, source, tags, created_by) VALUES (?, ?, ?, ?, ?)",
            (body, title, source, tags, created_by),
        )
        sid = int(cur.lastrowid)
    return seed_get(sid) or {}


def seed_get(seed_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_SEED_COLS} FROM seeds WHERE id = ?", (int(seed_id),)
        ).fetchone()
    return dict(row) if row else None


def seed_list(*, status: Optional[str] = None, cluster_id: Optional[int] = None,
              limit: int = 500) -> list[dict[str, Any]]:
    clauses, params = [], []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if cluster_id is not None:
        clauses.append("cluster_id = ?")
        params.append(int(cluster_id))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(int(limit))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_SEED_COLS} FROM seeds{where} ORDER BY id DESC LIMIT ?", params
        ).fetchall()
    return [dict(r) for r in rows]


def seed_update(seed_id: int, *, body: Optional[str] = None, title: Optional[str] = None,
                tags: Optional[str] = None, status: Optional[str] = None,
                cluster_id: Optional[int] = None) -> dict[str, Any]:
    sets, params = [], []
    for col, val in (("body", body), ("title", title), ("tags", tags),
                     ("status", status), ("cluster_id", cluster_id)):
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)
    if not sets:
        return seed_get(seed_id) or {}
    sets.append("updated_at = datetime('now')")
    params.append(int(seed_id))
    with connect() as conn:
        conn.execute(f"UPDATE seeds SET {', '.join(sets)} WHERE id = ?", params)
    return seed_get(seed_id) or {}


def seed_delete(seed_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM seeds WHERE id = ?", (int(seed_id),))


# ---------- clusters ----------

def seed_cluster_create(label: str, *, note: Optional[str] = None,
                        suggested_type: Optional[str] = None,
                        seed_ids: Optional[list[int]] = None) -> dict[str, Any]:
    """Create a cluster and (optionally) assign seeds to it."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO seed_clusters (label, note, suggested_type) VALUES (?, ?, ?)",
            (label, note, suggested_type),
        )
        cid = int(cur.lastrowid)
        for sid in (seed_ids or []):
            conn.execute(
                "UPDATE seeds SET cluster_id = ?, status = 'clustered', "
                "updated_at = datetime('now') WHERE id = ?",
                (cid, int(sid)),
            )
    return seed_cluster_get(cid) or {}


def seed_cluster_get(cluster_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_CLUSTER_COLS} FROM seed_clusters WHERE id = ?", (int(cluster_id),)
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["seeds"] = seed_list(cluster_id=cluster_id)
    return out


def seed_cluster_list(*, status: Optional[str] = "open") -> list[dict[str, Any]]:
    clause = " WHERE status = ?" if status else ""
    params = [status] if status else []
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_CLUSTER_COLS} FROM seed_clusters{clause} ORDER BY id DESC", params
        ).fetchall()
    return [dict(r) for r in rows]


def seed_cluster_update(cluster_id: int, *, label: Optional[str] = None,
                        note: Optional[str] = None, suggested_type: Optional[str] = None,
                        status: Optional[str] = None, graduated_to: Optional[str] = None) -> dict[str, Any]:
    sets, params = [], []
    for col, val in (("label", label), ("note", note), ("suggested_type", suggested_type),
                     ("status", status), ("graduated_to", graduated_to)):
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)
    if not sets:
        return seed_cluster_get(cluster_id) or {}
    sets.append("updated_at = datetime('now')")
    params.append(int(cluster_id))
    with connect() as conn:
        conn.execute(f"UPDATE seed_clusters SET {', '.join(sets)} WHERE id = ?", params)
    return seed_cluster_get(cluster_id) or {}


def seed_mark_graduated(seed_ids: list[int], production_id: str) -> None:
    with connect() as conn:
        for sid in seed_ids:
            conn.execute(
                "UPDATE seeds SET status = 'graduated', graduated_to = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (production_id, int(sid)),
            )
