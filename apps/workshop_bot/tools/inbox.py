"""Agent inbox — structured handoffs between personas.

Complements Discord channels (free-form chatter) and ``agent_notes``
(persistent memory) by giving agents a typed, addressable surface for
"I finished X, you should pick it up." Every persona's heartbeat opens
with ``inbox.list(filter='unread')`` so handoffs are the first thing
the agent reads on each wake-up.

The recipient is a persona name or ``team``. The sender is derived
from the ``active_persona`` ContextVar at post time so handlers don't
need to thread an extra arg through every tool call.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from . import db


VALID_RECIPIENTS: frozenset[str] = frozenset(
    {"eddy", "linky", "marky", "patty", "team"}
)
VALID_KINDS: frozenset[str] = frozenset(
    {"handoff", "request", "fyi", "completed"}
)
VALID_READ_STATUSES: frozenset[str] = frozenset({"read", "acted", "dismissed"})


# ---------- low-level SQL helpers ----------

def _row_to_dict(row: Any) -> dict[str, Any]:
    out = dict(row)
    raw_meta = out.get("metadata")
    if raw_meta:
        try:
            out["metadata"] = json.loads(raw_meta)
        except (TypeError, ValueError):
            # Leave as-is if it isn't valid JSON; the model can still read it.
            pass
    return out


def insert_inbox_item(
    *,
    recipient: str,
    sender: str,
    kind: str,
    subject: str,
    body: str,
    related_issue: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    expires_at: Optional[str] = None,
) -> int:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO agent_inbox "
            "(recipient, sender, kind, subject, body, metadata, related_issue, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                recipient,
                sender,
                kind,
                subject,
                body,
                json.dumps(metadata) if metadata else None,
                related_issue,
                expires_at,
            ),
        )
        return int(cur.lastrowid or 0)


def query_inbox(
    *,
    recipient: str,
    unread_only: bool = True,
    kind: Optional[str] = None,
    related_issue: Optional[int] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql_parts = [
        "SELECT id, recipient, sender, kind, subject, body, metadata, "
        "       related_issue, created_at, read_at, expires_at "
        "FROM agent_inbox WHERE recipient = ?"
    ]
    params: list[Any] = [recipient]
    if unread_only:
        sql_parts.append("AND read_at IS NULL")
    if kind:
        sql_parts.append("AND kind = ?")
        params.append(kind)
    if related_issue is not None:
        sql_parts.append("AND related_issue = ?")
        params.append(int(related_issue))
    sql_parts.append(
        "AND (expires_at IS NULL OR expires_at > datetime('now')) "
        "ORDER BY created_at DESC LIMIT ?"
    )
    params.append(int(limit))
    with db.connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_inbox_item(item_id: int) -> Optional[dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, recipient, sender, kind, subject, body, metadata, "
            "       related_issue, created_at, read_at, expires_at "
            "FROM agent_inbox WHERE id = ?",
            (int(item_id),),
        ).fetchone()
    return _row_to_dict(row) if row else None


def mark_inbox_read(item_id: int, status: str = "read") -> bool:
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE agent_inbox SET read_at = datetime('now') WHERE id = ?",
            (int(item_id),),
        )
        ok = cur.rowcount > 0
        if ok and status != "read":
            # Status is recorded inside the metadata JSON so the table
            # stays simple. acted/dismissed are read-state nuances, not
            # separate workflow states.
            conn.execute(
                "UPDATE agent_inbox SET metadata = json_set("
                "  COALESCE(metadata, '{}'), '$.read_status', ?) "
                "WHERE id = ?",
                (status, int(item_id)),
            )
        return ok


# ---------- tool handlers ----------

def t_inbox_post(
    deps,
    recipient: str,
    kind: str,
    subject: str,
    body: str,
    related_issue: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send a structured message to another persona or the team."""
    # Local import to avoid an agent_tools <-> inbox cycle at module load.
    from . import agent_tools

    if recipient not in VALID_RECIPIENTS:
        return {
            "error": f"unknown recipient {recipient!r}; "
            f"must be one of {sorted(VALID_RECIPIENTS)}"
        }
    if kind not in VALID_KINDS:
        return {
            "error": f"unknown kind {kind!r}; "
            f"must be one of {sorted(VALID_KINDS)}"
        }
    sender = agent_tools.active_persona.get()
    item_id = insert_inbox_item(
        recipient=recipient,
        sender=sender,
        kind=kind,
        subject=subject,
        body=body,
        related_issue=related_issue,
        metadata=metadata,
    )
    return {
        "id": item_id,
        "recipient": recipient,
        "sender": sender,
        "kind": kind,
        "posted": True,
    }


def t_inbox_list(
    deps,
    filter: Optional[str] = None,
    limit: int = 20,
    recipient: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List your inbox. Default is unread items addressed to you."""
    from . import agent_tools

    target = recipient or agent_tools.active_persona.get()
    unread_only = True
    kind: Optional[str] = None
    related_issue: Optional[int] = None
    raw = (filter or "unread").strip().lower()
    if raw == "all":
        unread_only = False
    elif raw == "unread":
        unread_only = True
    elif raw.startswith("kind="):
        kind = raw.split("=", 1)[1].strip() or None
    elif raw.startswith("related_issue="):
        try:
            related_issue = int(raw.split("=", 1)[1].strip())
        except ValueError:
            return [{"error": f"could not parse related_issue from {filter!r}"}]
    return query_inbox(
        recipient=target,
        unread_only=unread_only,
        kind=kind,
        related_issue=related_issue,
        limit=int(limit),
    )


def t_inbox_read(deps, id: int) -> dict[str, Any]:
    """Read one inbox item. Does NOT mark it read — call ``inbox.mark_read``
    when you've acted on it."""
    item = get_inbox_item(int(id))
    if item is None:
        return {"error": f"no inbox item with id {id}"}
    return item


def t_inbox_mark_read(deps, id: int, status: str = "read") -> dict[str, Any]:
    """Mark an inbox item read. ``status`` ∈ ``read``, ``acted``,
    ``dismissed`` (default ``read``)."""
    if status not in VALID_READ_STATUSES:
        return {
            "error": f"unknown status {status!r}; "
            f"must be one of {sorted(VALID_READ_STATUSES)}"
        }
    ok = mark_inbox_read(int(id), status=status)
    return {"id": int(id), "status": status, "updated": ok}


# ---------- registry hook ----------

def tool_specs() -> dict[str, dict[str, Any]]:
    """Return Anthropic tool specs for the four inbox tools, keyed by full
    dotted name."""
    return {
        "inbox.post": {
            "name": "inbox.post",
            "description": (
                "Send a structured message to another persona or to the team. "
                "Use for handoffs ('I finished curation, you can pick up'), "
                "requests ('can you draft the CTA?'), or fyi pings ('referral "
                "spike on dd-2026-05-15'). Recipient must be one of eddy, "
                "linky, marky, patty, team. Kind must be one of handoff, "
                "request, fyi, completed. Body is markdown."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string"},
                    "kind": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "related_issue": {"type": "integer"},
                    "metadata": {"type": "object"},
                },
                "required": ["recipient", "kind", "subject", "body"],
            },
        },
        "inbox.list": {
            "name": "inbox.list",
            "description": (
                "List your inbox. Default returns unread items addressed to "
                "you. Pass filter='all' for read+unread, filter='kind=handoff' "
                "to scope by kind, filter='related_issue=348' to scope by "
                "issue. Pass recipient='team' to read the shared team inbox."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string"},
                    "limit": {"type": "integer"},
                    "recipient": {"type": "string"},
                },
            },
        },
        "inbox.read": {
            "name": "inbox.read",
            "description": (
                "Read the full body of one inbox item by id. Does NOT mark "
                "it read — call inbox.mark_read once you've acted on it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
        },
        "inbox.mark_read": {
            "name": "inbox.mark_read",
            "description": (
                "Mark an inbox item read. Status defaults to 'read' but may "
                "also be 'acted' (you took action) or 'dismissed' (you "
                "decided to skip it)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "status": {"type": "string"},
                },
                "required": ["id"],
            },
        },
    }


def tool_handlers() -> dict[str, Any]:
    """Return tool handler functions keyed by full dotted name."""
    return {
        "inbox.post": t_inbox_post,
        "inbox.list": t_inbox_list,
        "inbox.read": t_inbox_read,
        "inbox.mark_read": t_inbox_mark_read,
    }
