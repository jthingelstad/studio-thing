"""The authored-content store — production content as DB rows.

This is the single read/write seam for authored content, replacing the S3
`atoms/` prefix. S3 is now publishing-only (generated outputs + binaries);
nothing reads authored content from S3. Content is keyed by `production_id`
(`WT350`/`ART7`/`POD3`) so every production type shares one store; newsletters
map their issue number through `pid_for_issue`.

`body` is stored as raw text — JSON blocks (cover/metadata) are the literal JSON
string (callers `json.loads` them), cta/thanks keep their YAML frontmatter.
Presence == a row exists, so `list()` returns the names present (the same
contract the old `s3.list_issue` gave the card/status presence checks).
"""

from __future__ import annotations

import re
from typing import Optional

from .db.connection import connect

# The newsletter authored-content names (the former S3 atoms). Other production
# types use their own names (e.g. 'body.md', 'script.md'); the store itself is
# name-agnostic — this set only gates the agent-tool routing in local_tools.
ATOM_NAMES = frozenset({
    "intro.md", "outro.md", "cover.json", "haiku.md",
    "metadata.json", "echoes.md",
})
_NUMBERED_RE = re.compile(r"^(cta|thanks)-\d+\.md$")


def is_atom_name(name: str) -> bool:
    """True if ``name`` is one of the newsletter authored-content names."""
    return name in ATOM_NAMES or bool(_NUMBERED_RE.match(name))


def pid_for_issue(n: int) -> str:
    """The production id for a newsletter issue number."""
    return f"WT{int(n)}"


# ---------- generic (production_id) API ----------

def get(production_id: str, name: str) -> Optional[str]:
    """The content body for one block, or None if no row exists."""
    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM production_content WHERE production_id = ? AND name = ?",
            (production_id, name),
        ).fetchone()
    return row["body"] if row is not None else None


def set(production_id: str, name: str, body: str, *, by: Optional[str] = None) -> None:
    """Upsert a content block."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO production_content (production_id, name, body, updated_by) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(production_id, name) DO UPDATE SET "
            "  body = excluded.body, updated_at = datetime('now'), "
            "  updated_by = excluded.updated_by",
            (production_id, name, body if body is not None else "", by),
        )


def list(production_id: str) -> list[str]:  # noqa: A001 — deliberate: the store's listing verb
    """The names present for a production (presence contract)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM production_content WHERE production_id = ? ORDER BY name",
            (production_id,),
        ).fetchall()
    return [r["name"] for r in rows]


def delete(production_id: str, name: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM production_content WHERE production_id = ? AND name = ?",
            (production_id, name),
        )


# ---------- newsletter (issue-number) convenience wrappers ----------

def read_issue(n: int, name: str) -> Optional[str]:
    return get(pid_for_issue(n), name)


def write_issue(n: int, name: str, body: str, *, by: Optional[str] = None) -> None:
    set(pid_for_issue(n), name, body, by=by)


def list_issue(n: int) -> list[str]:
    return list(pid_for_issue(n))


def delete_issue(n: int, name: str) -> None:
    delete(pid_for_issue(n), name)
