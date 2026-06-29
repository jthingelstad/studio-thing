"""``/scout slate`` — Scout's production-slate snapshot.

Read-only summary of what's in flight, by surface, backed by the generic
``productions`` registry (newsletters via ``issue_windows`` + their mirrored
``productions`` rows; articles / podcasts / projects directly from
``productions``). Multiple productions of each type can be in flight at once,
each in its own phase. The ``kind`` filter narrows to one surface.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.scout_slate")

NAME = "scout-slate"

ProductionKind = Literal["newsletter", "blog", "podcast", "membership"]
KNOWN_KINDS: tuple[ProductionKind, ...] = ("newsletter", "blog", "podcast", "membership")


def _rel(date_iso: str | None) -> str:
    try:
        d = (
            datetime.strptime(str(date_iso)[:10], "%Y-%m-%d").date()
            - datetime.now().date()
        ).days
    except (TypeError, ValueError):
        return "?"
    if d == 0:
        return "today"
    return f"in {d}d" if d > 0 else f"{-d}d ago"


def _prod_line(p: dict) -> str:
    """Render one generic production row as a slate ``└`` line."""
    pid = p.get("id", "?")
    phase = str(p.get("phase") or "").lower()
    title = (p.get("title") or "").strip()
    due = p.get("due_at")
    bits = [f"  └ **{pid}** [{phase}]"]
    if title and title != pid:
        bits.append(f"· {title}")
    if due:
        bits.append(f"· due {due} ({_rel(due)})")
    return " ".join(bits)


def _newsletter_block() -> tuple[list[str], dict]:
    """Render the newsletter slate block — every in-flight issue (concurrent)."""
    lines: list[str] = ["**Newsletter** — `weekly.thingelstad.com`"]
    windows = db.list_active_issue_windows()
    if not windows:
        lines.append("  └ *(no in-flight issue — `/scout issue start` to open one)*")
        return lines, {"in_flight": []}

    in_flight = []
    for w in windows:
        n = int(w["issue_number"])
        phase = str(w.get("phase") or "build").lower()
        pub = w.get("pub_date", "?")
        lines.append(
            f"  └ **WT{n}** [{phase}] · pub {pub} ({_rel(pub)}) "
            f"· cutoff {w.get('end_date', '?')}"
        )
        in_flight.append({"issue_number": n, "phase": phase, "pub_date": pub})
    return lines, {"in_flight": in_flight}


def _type_block(production_type: str, heading: str) -> tuple[list[str], dict]:
    """Render the active productions of one generic type (article / podcast)."""
    lines: list[str] = [heading]
    rows = db.list_productions(production_type=production_type, status="active")
    if not rows:
        lines.append(f"  └ *(no in-flight {production_type}s)*")
        return lines, {"in_flight": []}
    for p in rows:
        lines.append(_prod_line(p))
    return lines, {"in_flight": [{"id": p["id"], "phase": p["phase"]} for p in rows]}


def _blog_block() -> tuple[list[str], dict]:
    return _type_block("article", "**Blog** — `thingelstad.com`")


def _podcast_block() -> tuple[list[str], dict]:
    return _type_block("podcast", "**Podcast** — `another.thingelstad.com`")


def _membership_block() -> tuple[list[str], dict]:
    """The active milestone goal plus any in-flight generic projects (e.g. the
    50-supporters project)."""
    lines: list[str] = ["**Membership / projects**"]
    data: dict = {}
    g = db.get_active_goal()
    if g is None:
        lines.append("  └ *(no active goal — `/patty goal set` to open one)*")
        data["active_goal"] = None
    else:
        lines.append(
            f"  └ goal **{g['target_kind']} → {g['target_value']}** "
            f"(since {g.get('started_at', '?')})"
            + (f" — {g['notes']}" if g.get("notes") else "")
        )
        data["active_goal"] = dict(g)
    projects = db.list_productions(production_type="project", status="active")
    for p in projects:
        lines.append(_prod_line(p))
    data["projects"] = [{"id": p["id"], "phase": p["phase"]} for p in projects]
    return lines, data


_BUILDERS = {
    "newsletter": _newsletter_block,
    "blog": _blog_block,
    "podcast": _podcast_block,
    "membership": _membership_block,
}


def snapshot(kind: Optional[ProductionKind] = None) -> tuple[list[str], dict]:
    """Build the slate snapshot, optionally narrowed to one surface.

    Returns ``(lines, data)`` so the same shape backs the slash command,
    a future ``slate__snapshot`` agent tool, and tests.
    """
    if kind is not None and kind not in KNOWN_KINDS:
        return ([f"*Unknown production kind: {kind!r}*"], {"error": "unknown_kind"})

    kinds = (kind,) if kind is not None else KNOWN_KINDS
    out_lines: list[str] = ["🎬 **production slate**"]
    out_data: dict = {}
    for k in kinds:
        block_lines, block_data = _BUILDERS[k]()
        out_lines.extend(block_lines)
        out_data[k] = block_data
    return out_lines, out_data


async def run(
    ctx: "_base.JobContext",
    kind: Optional[ProductionKind] = None,
) -> "_base.JobResult":
    lines, data = snapshot(kind=kind)
    return _base.JobResult(True, "\n".join(lines), data=data)
