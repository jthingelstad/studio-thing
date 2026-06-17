"""``/scout slate`` — Scout's production-slate snapshot.

Read-only summary of what's in flight, by surface. In Part 1 the only
surface tracked is ``newsletter`` (one in-flight ``issue_windows`` row
at most). The job signature already accepts a ``kind`` filter so the
Part 2 migration to a multi-surface ``productions`` table can extend
this without rewriting callers.

The slate snapshot is the closest thing Scout has to a state-of-the-
world view today. Phase 2 will widen the per-surface block (Build /
Publish / Share for newsletter, idea / research / outline / draft /
review / publish prep for blog and podcast, ready / in copy / sent for
membership messages).
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


def _newsletter_block() -> tuple[list[str], dict]:
    """Render the newsletter slate block (one in-flight issue at most)."""
    lines: list[str] = ["**Newsletter** — `weekly.thingelstad.com`"]
    w = db.get_active_issue_window()
    if w is None:
        lines.append("  └ *(no in-flight issue — `/scout issue start` to open one)*")
        return lines, {"in_flight": None}

    n = int(w["issue_number"])
    phase = str(w.get("phase") or "build").lower()
    pub = w.get("pub_date", "?")
    lines.append(
        f"  └ **WT{n}** [{phase}] · pub {pub} ({_rel(pub)}) · cutoff {w.get('end_date', '?')}"
    )
    return lines, {"in_flight": {"issue_number": n, "phase": phase, "pub_date": pub}}


def _blog_block() -> tuple[list[str], dict]:
    """Placeholder until the Phase 2 productions schema lands."""
    return (
        ["**Blog** — `thingelstad.com`",
         "  └ *(no in-flight tracker yet — Phase 2)*"],
        {"in_flight": None, "deferred": True},
    )


def _podcast_block() -> tuple[list[str], dict]:
    return (
        ["**Podcast** — `another.thingelstad.com`",
         "  └ *(no in-flight tracker yet — Phase 2)*"],
        {"in_flight": None, "deferred": True},
    )


def _membership_block() -> tuple[list[str], dict]:
    """Show the active milestone goal as the current membership surface signal."""
    lines: list[str] = ["**Membership / supporters**"]
    g = db.get_active_goal()
    if g is None:
        lines.append("  └ *(no active goal — `/patty goal set` to open one)*")
        return lines, {"active_goal": None}
    lines.append(
        f"  └ goal **{g['target_kind']} → {g['target_value']}** "
        f"(since {g.get('started_at', '?')})"
        + (f" — {g['notes']}" if g.get("notes") else "")
    )
    return lines, {"active_goal": dict(g)}


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
