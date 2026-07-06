"""In-web Eddy conversation threads for newsletter issue pages.

``context_key`` is the issue being discussed ('WT350'). A web handler records
Jamie's message, runs Eddy's agent loop in the background, and records the
reply; the page polls ``chat_list`` for new messages.
"""

from __future__ import annotations

from typing import Any, Optional

from .connection import connect

_COLS = "id, context_key, role, persona, content, created_at"


def chat_add(context_key: str, role: str, content: str,
             *, persona: Optional[str] = None) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO production_chats (context_key, role, persona, content) "
            "VALUES (?, ?, ?, ?)",
            (context_key, role, persona, content),
        )
        cid = int(cur.lastrowid)
        row = conn.execute(
            f"SELECT {_COLS} FROM production_chats WHERE id = ?", (cid,)
        ).fetchone()
    return dict(row)


def chat_list(context_key: str, *, since_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM production_chats "
            "WHERE context_key = ? AND id > ? ORDER BY id LIMIT ?",
            (context_key, int(since_id), int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
