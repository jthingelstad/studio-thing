"""Linky discovery: popular-feed dedup, sightings, to-read research, research-card messages, feedbin dedup (moved from store.py)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from .connection import connect


# ---------- Linky: popular feed dedup + to-read research ----------

def filter_unseen_popular(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only items whose URL isn't yet in pinboard_popular_seen."""
    if not items:
        return []
    norm_pairs = [(it, _norm_url(it.get("url"))) for it in items if it.get("url")]
    norm_urls = [url for _, url in norm_pairs if url]
    if not norm_urls:
        return []
    placeholders = ",".join("?" * len(norm_urls))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT url FROM pinboard_popular_seen WHERE url IN ({placeholders})",
            norm_urls,
        ).fetchall()
    seen = {r["url"] for r in rows}
    return [it for it, url in norm_pairs if url and url not in seen]


def _norm_url(url: Optional[str]) -> str:
    """Normalise ``url`` for dedup-table storage and lookup. Delegates to
    :func:`url_normalize.dedup_key`; falls back to the trimmed raw URL
    when normalisation returns ``""`` (e.g. for inputs ``dedup_key``
    can't parse). Empty input returns ``""``.

    Both write paths and read paths in this module funnel URLs through
    here, so a fragment-or-utm-only difference between two URL forms
    of the same article collapses to one row. See
    :mod:`apps.workshop_bot.tools.url_normalize` for the rule set."""
    if not url:
        return ""
    # Avoid an import cycle at module load — url_normalize is a leaf.
    from ..url_normalize import dedup_key
    key = dedup_key(url)
    return key or (url.strip() if isinstance(url, str) else "")


def mark_popular_seen(
    items: list[dict[str, Any]],
    *,
    judged: Optional[dict[str, tuple[bool, str]]] = None,
    verdict_source: Optional[str] = None,
) -> int:
    """Insert ``items`` into pinboard_popular_seen (no-op on conflict).

    ``judged`` is an optional ``url -> (interesting?, note)`` mapping
    from the LLM filter, persisted alongside the row so future audits
    can see what Linky judged interesting vs not.

    ``verdict_source`` is the lane/feed name that produced the verdict
    (for example ``"popular"`` or ``"toread"``). Stored so the
    cross-source uplift block can label the previous verdict without
    inferring from the sightings log. Optional for backwards-compat —
    callers that don't pass it leave the column NULL.

    The URL column stores the normalised dedup-key form so cross-scan
    lookups by either the raw URL or its normalised form hit the same
    row (callers should pass the form they have; the helper normalises
    on the way in). The ``judged`` dict's keys can be in either form
    too — they're normalised before lookup.
    """
    n = 0
    judged_raw = judged or {}
    judged_norm = {_norm_url(k): v for k, v in judged_raw.items() if k}
    with connect() as conn:
        for it in items:
            raw_url = it.get("url")
            url = _norm_url(raw_url)
            if not url:
                continue
            interesting_flag: Optional[int] = None
            note: Optional[str] = None
            if url in judged_norm:
                ok, note = judged_norm[url]
                interesting_flag = 1 if ok else 0
            cur = conn.execute(
                "INSERT OR IGNORE INTO pinboard_popular_seen "
                "(url, title, posted_by, judged_interesting, judgment_note, "
                " verdict_source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    url,
                    it.get("title"),
                    it.get("posted_by"),
                    interesting_flag,
                    note,
                    verdict_source,
                ),
            )
            if cur.rowcount:
                n += 1
    return n


def set_popular_seen_judgment(
    *,
    url: str,
    interesting: bool,
    note: str,
    title: Optional[str] = None,
    verdict_source: Optional[str] = None,
) -> None:
    """UPSERT a judgment into ``pinboard_popular_seen`` for a URL.

    Unlike :func:`mark_popular_seen` (which is INSERT OR IGNORE — write
    only on first sight), this helper always writes the judgment, used
    when Jamie's reaction supplies the verdict for a URL Linky already
    recorded. New rows get inserted with the judgment populated; existing
    rows get ``judged_interesting`` + ``judgment_note`` updated.

    ``note`` is the editorial differentiator (e.g. ``'reviewed-fine'``
    vs ``'rejected'`` from the ✅ vs 🛑 reaction).
    """
    if not url:
        return
    nurl = _norm_url(url)
    if not nurl:
        return
    flag = 1 if interesting else 0
    with connect() as conn:
        conn.execute(
            "INSERT INTO pinboard_popular_seen "
            "(url, title, judged_interesting, judgment_note, verdict_source) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET "
            "  judged_interesting=excluded.judged_interesting, "
            "  judgment_note=excluded.judgment_note, "
            "  title=COALESCE(excluded.title, pinboard_popular_seen.title), "
            "  verdict_source=COALESCE(excluded.verdict_source, pinboard_popular_seen.verdict_source)",
            (nurl, title, flag, note, verdict_source),
        )


# ---------- popular_seen_sightings (cross-source temporal signal) ----------


def record_sighting(*, url: str, source: str) -> bool:
    """Insert one (url, source) sighting. ``url`` is normalised via
    :func:`_norm_url` before storage so fragment-only or tracking-param-
    only variants collapse to one row. Idempotent: returns False if the
    row already existed, True if newly inserted."""
    nurl = _norm_url(url)
    if not nurl or not source:
        return False
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO popular_seen_sightings (url, source) "
            "VALUES (?, ?)",
            (nurl, source),
        )
        return cur.rowcount > 0


def feed_has_seen(*, url: str, source: str) -> bool:
    """True if (url, source) is in popular_seen_sightings. ``url`` is
    normalised before lookup."""
    nurl = _norm_url(url)
    if not nurl or not source:
        return False
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM popular_seen_sightings WHERE url = ? AND source = ?",
            (nurl, source),
        ).fetchone()
    return row is not None


def sightings_for(url: str) -> list[dict[str, Any]]:
    """Return ``[{source, seen_at}, ...]`` for every recorded sighting of
    ``url``, oldest first. Empty list if the URL has never been seen.
    ``url`` is normalised before lookup."""
    nurl = _norm_url(url)
    if not nurl:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT source, seen_at FROM popular_seen_sightings "
            "WHERE url = ? ORDER BY seen_at",
            (nurl,),
        ).fetchall()
    return [{"source": r["source"], "seen_at": r["seen_at"]} for r in rows]


def popular_verdict(url: str) -> Optional[dict[str, Any]]:
    """Return ``{judged_interesting, judgment_note, verdict_source,
    first_seen_at, title, posted_by}`` for ``url`` if it has a row in
    ``pinboard_popular_seen``, else ``None``. ``url`` is normalised
    before lookup. ``verdict_source`` is the feed name that produced
    the verdict (may be ``None`` on legacy rows written before the
    column was added)."""
    nurl = _norm_url(url)
    if not nurl:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT url, title, posted_by, judged_interesting, judgment_note, "
            "       verdict_source, first_seen_at "
            "FROM pinboard_popular_seen WHERE url = ?",
            (nurl,),
        ).fetchone()
    return dict(row) if row else None


def filter_unresearched_urls(urls: list[str]) -> list[str]:
    """Return only URLs not yet present in pinboard_research_done. Each
    input URL is normalised before lookup; the original strings are
    returned for callers that need to preserve the raw form."""
    if not urls:
        return []
    norm_pairs = [(u, _norm_url(u)) for u in urls]
    norm_keys = [n for _, n in norm_pairs if n]
    if not norm_keys:
        return list(urls)
    placeholders = ",".join("?" * len(norm_keys))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT url FROM pinboard_research_done WHERE url IN ({placeholders})",
            norm_keys,
        ).fetchall()
    done = {r["url"] for r in rows}
    return [raw for raw, n in norm_pairs if not n or n not in done]


def mark_url_researched(
    *,
    url: str,
    title: Optional[str],
    summary: str,
    confidence: Optional[str] = None,
    fit_note: Optional[str] = None,
) -> bool:
    """Insert a research record. ``url`` is normalised before storage.
    Returns True if newly inserted."""
    nurl = _norm_url(url)
    if not nurl:
        return False
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pinboard_research_done "
            "(url, title, summary, confidence, fit_note) "
            "VALUES (?, ?, ?, ?, ?)",
            (nurl, title, summary, confidence, fit_note),
        )
        return cur.rowcount > 0





# ---------- Linky research cards (one row per posted #research message) ----------


RESEARCH_SOURCES = (
    "popular", "toread",
)


def record_research_message(
    *, discord_message_id: str, url: str, source: str, title: Optional[str] = None,
) -> None:
    """Persist that Linky posted a per-link research card to #research,
    so a future reply to that message can be routed back to the URL.
    ``title`` is captured so a popular-feed reply that auto-creates a
    bookmark has something more useful than the URL as the title.
    ``source`` is one of :data:`RESEARCH_SOURCES`.

    ``url`` is normalised before storage to keep this table aligned with
    the dedup tables — so the reply / save-reaction routing reaches the
    same row regardless of which URL form upstream handed us."""
    if not discord_message_id or not url or source not in RESEARCH_SOURCES:
        return
    nurl = _norm_url(url)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO linky_research_messages "
            "(discord_message_id, url, source, title) VALUES (?, ?, ?, ?)",
            (str(discord_message_id), nurl, source, title),
        )


def lookup_research_message(discord_message_id: str) -> Optional[dict[str, Any]]:
    """Return the row for ``discord_message_id`` (the message Jamie's reply
    references), or ``None`` if it isn't one of Linky's cards."""
    if not discord_message_id:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT discord_message_id, url, source, title, posted_at "
            "FROM linky_research_messages WHERE discord_message_id = ?",
            (str(discord_message_id),),
        ).fetchone()
    return dict(row) if row else None


# ---------- feedbin starred-items dedup (one row per ingested guid) ----------


def feedbin_seen_guids(guids: list[str]) -> set[str]:
    """Subset of ``guids`` already recorded in ``feedbin_starred_seen``.
    Lets the ingest job batch-check before per-item Pinboard calls."""
    if not guids:
        return set()
    placeholders = ",".join("?" * len(guids))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT guid FROM feedbin_starred_seen WHERE guid IN ({placeholders})",
            guids,
        ).fetchall()
    return {r["guid"] for r in rows}


def record_feedbin_seen(
    *, guid: str, url: str, title: str = "", pinboard_result: Optional[str] = None,
) -> None:
    """Idempotent insert of a Feedbin ingest record. Re-stars of an item
    are no-ops once the GUID is recorded — Pinboard already has the
    bookmark."""
    if not guid:
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO feedbin_starred_seen (guid, url, title, pinboard_result) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guid) DO UPDATE SET "
            "  url=excluded.url, "
            "  title=excluded.title, "
            "  pinboard_result=COALESCE(excluded.pinboard_result, feedbin_starred_seen.pinboard_result)",
            (guid, url, title or "", pinboard_result),
        )


