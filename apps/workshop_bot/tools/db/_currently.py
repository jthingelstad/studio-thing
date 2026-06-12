"""Per-issue ## Currently values + canonical types (moved from store.py)."""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import connect


# ---------- currently (per-issue `## Currently` values + canonical types) ----------


class CurrentlyError(ValueError):
    """Bad input to a currently_* helper — message is safe to surface."""


def currently_list_types(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    """Return canonical Currently types alphabetically, with their
    denormalised last-used recency. Active-only by default."""
    sql = (
        "SELECT label, is_active, last_used_issue, last_used_at "
        "FROM currently_types"
    )
    if not include_inactive:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY label COLLATE NOCASE"
    with connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def currently_get_type(label: str) -> Optional[dict[str, Any]]:
    if not label or not label.strip():
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT label, is_active, last_used_issue, last_used_at "
            "FROM currently_types WHERE label = ? COLLATE NOCASE",
            (label.strip(),),
        ).fetchone()
    return dict(row) if row else None


def currently_add_type(label: str) -> dict[str, Any]:
    """Insert a new canonical type. Raises :class:`CurrentlyError` if the
    label is blank or already exists (case-insensitive). Returns the
    inserted row."""
    norm = (label or "").strip()
    if not norm:
        raise CurrentlyError("Give a `label` — what to call this Currently type.")
    if currently_get_type(norm) is not None:
        raise CurrentlyError(f"Currently type `{norm}` already exists.")
    with connect() as conn:
        conn.execute("INSERT INTO currently_types (label) VALUES (?)", (norm,))
    return currently_get_type(norm) or {"label": norm, "is_active": 1}


def currently_retire_type(label: str) -> bool:
    """Mark a type inactive — past entries still render, future
    suggestions skip it. Returns False if no such type."""
    norm = (label or "").strip()
    if not norm:
        return False
    with connect() as conn:
        cur = conn.execute(
            "UPDATE currently_types SET is_active = 0 "
            "WHERE label = ? COLLATE NOCASE",
            (norm,),
        )
        return cur.rowcount > 0


def currently_get_entries(issue_number: int) -> list[dict[str, Any]]:
    """Return the entries for one issue in render order
    (``position`` ASC). Empty list when nothing's set."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT type_label, value, position, updated_at "
            "FROM currently_entries WHERE issue_number = ? "
            "ORDER BY position",
            (int(issue_number),),
        ).fetchall()
    return [dict(r) for r in rows]


def _currently_recompute_last_used(conn, label: str) -> None:
    """Refresh ``currently_types.last_used_issue`` / ``last_used_at`` for
    one label from ``currently_entries`` (MAX issue). Run inside an
    existing transaction; takes ``conn`` so callers compose."""
    row = conn.execute(
        "SELECT issue_number, updated_at FROM currently_entries "
        "WHERE type_label = ? COLLATE NOCASE "
        "ORDER BY issue_number DESC, updated_at DESC LIMIT 1",
        (label,),
    ).fetchone()
    if row is None:
        conn.execute(
            "UPDATE currently_types SET last_used_issue = NULL, "
            "last_used_at = NULL WHERE label = ? COLLATE NOCASE",
            (label,),
        )
    else:
        conn.execute(
            "UPDATE currently_types SET last_used_issue = ?, "
            "last_used_at = ? WHERE label = ? COLLATE NOCASE",
            (int(row["issue_number"]), row["updated_at"], label),
        )


def currently_set_entry(issue_number: int, label: str, value: str) -> dict[str, Any]:
    """UPSERT one entry. New rows get ``position = MAX(existing)+1`` for
    that issue (append). Existing rows preserve their position.
    ``currently_types.last_used_issue`` is updated to ``MAX(prior,
    this_issue)`` in the same transaction. Raises :class:`CurrentlyError`
    when the label isn't a known canonical type or value is blank."""
    n = int(issue_number)
    norm = (label or "").strip()
    val = (value or "").strip()
    if not norm:
        raise CurrentlyError("Give a `label`.")
    if not val:
        raise CurrentlyError("Give a non-empty `value` (use `currently_clear_entry` to delete).")
    type_row = currently_get_type(norm)
    if type_row is None:
        raise CurrentlyError(
            f"`{norm}` isn't a known Currently type. Add it with `currently_add_type` first."
        )
    canonical = type_row["label"]  # preserve canonical casing
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT position FROM currently_entries "
                "WHERE issue_number = ? AND type_label = ?",
                (n, canonical),
            ).fetchone()
            if existing is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 AS next "
                    "FROM currently_entries WHERE issue_number = ?",
                    (n,),
                ).fetchone()
                position = int(row["next"])
                conn.execute(
                    "INSERT INTO currently_entries "
                    "(issue_number, type_label, value, position) "
                    "VALUES (?, ?, ?, ?)",
                    (n, canonical, val, position),
                )
            else:
                position = int(existing["position"])
                conn.execute(
                    "UPDATE currently_entries SET value = ?, "
                    "updated_at = datetime('now') "
                    "WHERE issue_number = ? AND type_label = ?",
                    (val, n, canonical),
                )
            # Recency: MAX with prior so re-setting an older issue
            # doesn't move a newer one's last_used backwards.
            conn.execute(
                "UPDATE currently_types SET "
                "  last_used_issue = MAX(COALESCE(last_used_issue, 0), ?), "
                "  last_used_at = CASE "
                "    WHEN last_used_issue IS NULL OR last_used_issue <= ? "
                "      THEN datetime('now') "
                "    ELSE last_used_at "
                "  END "
                "WHERE label = ?",
                (n, n, canonical),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"issue_number": n, "label": canonical, "value": val, "position": position}


def currently_clear_entry(issue_number: int, label: str) -> bool:
    """Delete one entry, renumber remaining entries for that issue
    contiguously (1..N), and recompute ``last_used_issue`` for the
    cleared label. Returns False if the row didn't exist."""
    n = int(issue_number)
    norm = (label or "").strip()
    if not norm:
        return False
    canonical_row = currently_get_type(norm)
    canonical = canonical_row["label"] if canonical_row else norm
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "DELETE FROM currently_entries "
                "WHERE issue_number = ? AND type_label = ? COLLATE NOCASE",
                (n, canonical),
            )
            deleted = cur.rowcount > 0
            if deleted:
                remaining = conn.execute(
                    "SELECT type_label FROM currently_entries "
                    "WHERE issue_number = ? ORDER BY position",
                    (n,),
                ).fetchall()
                for i, r in enumerate(remaining, start=1):
                    conn.execute(
                        "UPDATE currently_entries SET position = ? "
                        "WHERE issue_number = ? AND type_label = ?",
                        (i, n, r["type_label"]),
                    )
                _currently_recompute_last_used(conn, canonical)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return deleted


def currently_reorder(issue_number: int, ordered_labels: list[str]) -> list[str]:
    """Reorder one issue's entries to ``ordered_labels`` (positions
    1..N). ``ordered_labels`` must be a strict permutation of the labels
    currently in ``currently_entries`` for that issue — raises
    :class:`CurrentlyError` on a missing or extra label. Returns the
    applied order (canonical casing)."""
    n = int(issue_number)
    if not isinstance(ordered_labels, (list, tuple)):
        raise CurrentlyError("`ordered_labels` must be a list of label strings.")
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing_rows = conn.execute(
                "SELECT type_label FROM currently_entries "
                "WHERE issue_number = ? ORDER BY position",
                (n,),
            ).fetchall()
            existing = [r["type_label"] for r in existing_rows]
            # Resolve each requested label to its canonical casing as
            # stored in currently_entries (case-insensitive match).
            existing_ci = {lbl.lower(): lbl for lbl in existing}
            seen: set[str] = set()
            resolved: list[str] = []
            for raw in ordered_labels:
                key = str(raw or "").strip().lower()
                if not key or key not in existing_ci:
                    conn.execute("ROLLBACK")
                    raise CurrentlyError(
                        f"`{raw}` isn't a filled Currently entry for issue #{n}. "
                        f"Filled entries: {', '.join(existing) or '(none)'}."
                    )
                if key in seen:
                    conn.execute("ROLLBACK")
                    raise CurrentlyError(f"Duplicate label `{raw}` in reorder.")
                seen.add(key)
                resolved.append(existing_ci[key])
            if len(resolved) != len(existing):
                missing = [lbl for lbl in existing if lbl.lower() not in seen]
                conn.execute("ROLLBACK")
                raise CurrentlyError(
                    f"Reorder must include every filled entry. Missing: {', '.join(missing)}."
                )
            for i, lbl in enumerate(resolved, start=1):
                conn.execute(
                    "UPDATE currently_entries SET position = ? "
                    "WHERE issue_number = ? AND type_label = ?",
                    (i, n, lbl),
                )
            conn.execute("COMMIT")
        except CurrentlyError:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return resolved


def currently_suggest_stale(
    active_issue: Optional[int], *, k: int = 3, include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """Top-K active types ordered by recency (never-used first, then
    least-recent). Each row carries ``gap_issues`` — how many issues since
    last use (``None`` for never-used). When ``active_issue`` is None,
    ``gap_issues`` is reported relative to each type's
    ``last_used_issue`` only (so never-used still sort first)."""
    k = max(1, int(k))
    rows = currently_list_types(include_inactive=include_inactive)
    rows.sort(
        key=lambda r: (
            0 if r.get("last_used_issue") is None else 1,
            r.get("last_used_issue") or 0,
            (r.get("last_used_at") or ""),
            r["label"].lower(),
        )
    )
    out: list[dict[str, Any]] = []
    for r in rows[:k]:
        last = r.get("last_used_issue")
        gap: Optional[int] = None
        if active_issue is not None and last is not None:
            gap = int(active_issue) - int(last)
        out.append({
            "label": r["label"],
            "last_used_issue": last,
            "last_used_at": r.get("last_used_at"),
            "gap_issues": gap,
        })
    return out


def currently_backfill_from_s3(issue_number: int) -> int:
    """Seed ``currently_entries`` for ``issue_number`` from the legacy
    ``currently.json`` in S3, if present. Idempotent: no-ops when the
    issue already has any DB entries. Returns the number of rows
    inserted (0 on no-op or missing JSON).

    Used as a one-time bridge so the in-flight issue's existing
    Shortcut-authored content survives the renderer migration. After
    the issue ships once via the new flow, the DB has rows and this
    is a no-op forever."""
    n = int(issue_number)
    with connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM currently_entries WHERE issue_number = ? LIMIT 1",
            (n,),
        ).fetchone()
    if existing is not None:
        return 0
    try:
        from .. import s3  # local import — avoid module-load cycle with tools/s3.py
    except Exception:  # noqa: BLE001
        return 0
    try:
        raw = s3.read_issue_file(n, "currently.json")
    except Exception:  # noqa: BLE001
        return 0
    if not raw.get("found"):
        return 0
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return 0
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return 0
    if not isinstance(data, dict):
        return 0
    inserted = 0
    for raw_label, raw_value in data.items():
        label = str(raw_label or "").strip().rstrip(":").strip()
        value = str(raw_value or "").strip()
        if not label or not value:
            continue
        if currently_get_type(label) is None:
            try:
                currently_add_type(label)
            except CurrentlyError:
                # Race with another writer is fine — just look it up again.
                if currently_get_type(label) is None:
                    continue
        try:
            currently_set_entry(n, label, value)
            inserted += 1
        except CurrentlyError:
            continue
    return inserted


