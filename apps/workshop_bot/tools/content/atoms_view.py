"""The read-side atom projection (atom editor, build 1).

Presents an in-flight newsletter issue as **one ordered list of atoms** —
the unified view from ``notes/design/issue-atoms.md`` — assembled at read
time from the three existing stores:

- ``production_content``  → authored atoms (intro / outro / echoes / closer)
- ``currently_entries``   → currently atoms (label + one line of markdown)
- ``issue_items``         → derived atoms (notable / journal / briefly),
  including the editor-owned ``section_override`` / ``excluded`` state
- ``cover.json``          → the photo atom (image + caption + location)

No new table; no store is written here. When the real ``atoms`` table lands
(migration step 2+), this module is the only thing that changes — its
consumers keep seeing the same shape.

Atom shape (dict):
    kind        'intro' | 'currently' | 'photo' | 'notable' | 'journal' |
                'brief' | 'outro' | 'echoes' | 'closer'
    key         stable handle for POSTs: 'content:intro.md' |
                'currently:Building' | 'item:123' | 'photo:cover.json'
    title       display title (item title, currently label, kind label)
    body        markdown body ('' when absent)
    source      provenance: 'pinboard' | 'microblog' | 'original' | 'generated'
    url         upstream URL when derived (the pin / blog post)
    editable    body editable in the web editor (authored atoms only in
                build 1 — derived bodies mirror their upstream until the
                Pinboard write-back lands)
    selected    False when the editor deselected it (issue_items.excluded)
    flippable   participates in the briefly ↔ notable promotion verb
    item_id     issue_items row id (derived atoms only)
    overridden  True when section_override is set (flip active)
    promoted    True when lifted to a standalone featured section
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .. import content_store, issue_items
from .. import db

# Reading order of the issue, per the design brief. Notable/journal/brief
# expand to one atom per row; the authored kinds are one atom each.
KIND_ORDER = (
    "intro", "currently", "photo", "notable", "journal", "brief",
    "outro", "echoes", "closer",
)

# Authored kinds → production_content name. ``closer`` is the haiku (the
# closer *template* stays in the renderer for build 1).
_AUTHORED = {
    "intro": "intro.md",
    "outro": "outro.md",
    "echoes": "echoes.md",
    "closer": "haiku.md",
}

# Content-store names the editor may write (the authored atoms).
AUTHORED_NAMES = frozenset(_AUTHORED.values())

_DERIVED_SECTIONS = ("notable", "journal", "brief")


def _authored_atom(production_id: str, kind: str) -> dict[str, Any]:
    name = _AUTHORED[kind]
    body = content_store.get(production_id, name) or ""
    return {
        "kind": kind, "key": f"content:{name}",
        "title": kind.capitalize(), "body": body,
        "source": "generated" if kind in ("echoes", "closer") else "original",
        "url": None, "editable": True, "selected": True,
        "flippable": False, "item_id": None,
        "overridden": False, "promoted": False,
    }


def _currently_atoms(issue_number: int) -> list[dict[str, Any]]:
    out = []
    for e in db.currently_get_entries(issue_number):
        out.append({
            "kind": "currently", "key": f"currently:{e['type_label']}",
            "title": e["type_label"], "body": e.get("value") or "",
            "source": "original", "url": None, "editable": True,
            "selected": True, "flippable": False, "item_id": None,
            "overridden": False, "promoted": False,
        })
    return out


def _photo_atom(production_id: str) -> dict[str, Any]:
    raw = content_store.get(production_id, "cover.json") or ""
    fields: dict[str, Any] = {}
    if raw:
        try:
            fields = json.loads(raw)
        except (TypeError, ValueError):
            fields = {}
    caption = str(fields.get("caption") or "")
    location = str(fields.get("location") or "")
    body = caption if not location else (f"{caption}\n\n📍 {location}" if caption else f"📍 {location}")
    return {
        "kind": "photo", "key": "photo:cover.json",
        "title": "Photo", "body": body,
        "source": "original", "url": None, "editable": False,
        "selected": True, "flippable": False, "item_id": None,
        "overridden": False, "promoted": False,
    }


def _item_atom(row: dict[str, Any]) -> dict[str, Any]:
    effective = str(row.get("section_override") or row["section"])
    return {
        "kind": effective, "key": f"item:{row['id']}",
        "title": row.get("title") or "(untitled)",
        "body": row.get("body_md") or "",
        "source": row["source"], "url": row.get("url"),
        "editable": False,  # derived bodies mirror upstream in build 1
        "selected": not row.get("excluded"),
        "flippable": effective in ("notable", "brief"),
        "item_id": int(row["id"]),
        "overridden": row.get("section_override") is not None,
        "promoted": bool(row.get("is_promoted")),
    }


def build(issue_number: int, production_id: Optional[str] = None) -> list[dict[str, Any]]:
    """The issue as one ordered atom list (reading order, deselected rows
    included so the editor can re-select them)."""
    pid = production_id or f"WT{int(issue_number)}"
    by_kind: dict[str, list[dict[str, Any]]] = {k: [] for k in KIND_ORDER}
    by_kind["intro"].append(_authored_atom(pid, "intro"))
    by_kind["currently"].extend(_currently_atoms(issue_number))
    by_kind["photo"].append(_photo_atom(pid))
    for section in _DERIVED_SECTIONS:
        rows = issue_items.list_items(
            issue_number, section=section, include_excluded=True)
        by_kind[section].extend(_item_atom(r) for r in rows)
    by_kind["outro"].append(_authored_atom(pid, "outro"))
    by_kind["echoes"].append(_authored_atom(pid, "echoes"))
    by_kind["closer"].append(_authored_atom(pid, "closer"))
    return [atom for kind in KIND_ORDER for atom in by_kind[kind]]
