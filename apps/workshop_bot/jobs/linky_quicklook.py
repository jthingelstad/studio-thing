"""``/linky {pile,stats}`` — read-only quick looks for Linky.

Neither hits the LLM. ``pile`` queries Pinboard for currently
``_brief``-tagged bookmarks (the Briefly candidates Jamie's marked via
the ⏩ reaction). ``stats`` reports recent Linky surfacing activity from
the local DB.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..systems.pinboard import client as pinboard_client
from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.linky_quicklook")

_PILE_LIMIT = 40


# ---------- /linky pile ----------

async def pile(ctx: "_base.JobContext", *, limit: int = 25) -> "_base.JobResult":
    """List the currently-active `_brief`-tagged Pinboard bookmarks."""
    limit = max(1, min(int(limit or 25), _PILE_LIMIT))
    try:
        rows = await asyncio.to_thread(pinboard_client.recent_posts, count=limit, tag="_brief")
    except Exception as exc:  # noqa: BLE001
        logger.warning("linky_quicklook pile: pinboard fetch failed: %s", exc)
        return _base.JobResult(False, f"❌ Pinboard fetch failed: `{type(exc).__name__}: {exc}`")

    if not rows:
        return _base.JobResult(
            True,
            "_(No `_brief`-tagged bookmarks in your Pinboard pile right now.)_",
            data={"count": 0},
        )

    bits = [f"⏩ **Briefly pile** — {len(rows)} bookmarks tagged `_brief`"]
    for r in rows[:limit]:
        title = (r.get("description") or r.get("title") or "(untitled)").strip()
        href = r.get("href") or r.get("url") or ""
        when = (r.get("time") or "")[:10]
        # Pinboard's `extended` field is the long description / Jamie's notes.
        ext = (r.get("extended") or "").strip()
        line = f"- [{title}]({href})"
        if when:
            line += f" · _{when}_"
        bits.append(line)
        if ext:
            short = ext if len(ext) <= 120 else ext[:117] + "…"
            bits.append(f"  > {short}")

    return _base.JobResult(True, "\n".join(bits), data={"count": len(rows)})


# ---------- /linky stats ----------

async def stats(ctx: "_base.JobContext", *, days: int = 7) -> "_base.JobResult":
    """Summary of Linky's recent surfacing activity from the local DB."""
    days = max(1, min(int(days or 7), 90))
    try:
        rows: list[dict[str, Any]] = await asyncio.to_thread(_recent_research_messages, days)
    except Exception as exc:  # noqa: BLE001
        logger.warning("linky_quicklook stats: db query failed: %s", exc)
        return _base.JobResult(False, f"❌ research-message query failed: `{type(exc).__name__}: {exc}`")

    if not rows:
        return _base.JobResult(
            True, f"_(No Linky cards posted in the last {days} days.)_", data={"days": days, "count": 0},
        )

    by_source: dict[str, int] = {}
    for r in rows:
        s = r.get("source") or "?"
        by_source[s] = by_source.get(s, 0) + 1

    total = len(rows)
    bits = [f"📊 **Linky surface — last {days}d** · {total} cards"]
    for src in sorted(by_source, key=by_source.get, reverse=True):
        bits.append(f"- `{src}`: **{by_source[src]}**")

    return _base.JobResult(
        True, "\n".join(bits),
        data={"days": days, "count": total, "by_source": by_source},
    )


def _recent_research_messages(days: int) -> list[dict[str, Any]]:
    """SELECT recent rows from linky_research_messages within the window."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT source, url, posted_at "
            "FROM linky_research_messages "
            "WHERE posted_at >= datetime('now', ?) "
            "ORDER BY posted_at DESC",
            (f"-{int(days)} days",),
        ).fetchall()
    return [dict(r) for r in rows]
