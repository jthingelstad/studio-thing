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


# ---------- linky_feedback (Jamie's explicit calibration signals) ----------


def record_linky_feedback(
    *,
    url: str,
    source: str,
    action: str,
    label: int,
    title: Optional[str] = None,
    discord_message_id: Optional[str] = None,
    note: Optional[str] = None,
) -> None:
    """Record Jamie's explicit feedback on a Linky card.

    This is the human preference journal, deliberately separate from
    ``pinboard_popular_seen``. The popular-seen table answers dedup /
    first-verdict questions and includes Linky's own "card posted"
    decisions; this table only records Jamie's gestures so future scans
    can calibrate against the real bar.
    """
    nurl = _norm_url(url)
    action = (action or "").strip()
    source = (source or "").strip()
    if not nurl or not source or not action:
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO linky_feedback "
            "(url, title, source, discord_message_id, action, label, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                nurl, title, source,
                str(discord_message_id) if discord_message_id else None,
                action, int(label), note,
            ),
        )


def recent_linky_feedback(*, source: Optional[str] = None, limit: int = 40) -> list[dict[str, Any]]:
    """Recent explicit Linky feedback, newest first."""
    limit = max(1, min(int(limit or 40), 200))
    sql = (
        "SELECT url, title, source, discord_message_id, action, label, note, created_at "
        "FROM linky_feedback "
    )
    params: list[Any] = []
    if source:
        sql += "WHERE source = ? "
        params.append(source)
    sql += "ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def linky_feedback_fingerprint(*, source: str = "popular") -> dict[str, Any]:
    """Return the source's feedback fingerprint used to detect stale
    synthesis rows."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS feedback_count, MAX(created_at) AS feedback_latest_at "
            "FROM linky_feedback WHERE source = ?",
            (source,),
        ).fetchone()
    return {
        "feedback_count": int(row["feedback_count"] or 0),
        "feedback_latest_at": row["feedback_latest_at"],
    }


def get_linky_feedback_profile(*, source: str = "popular") -> Optional[dict[str, Any]]:
    """Return the persisted synthesis profile for ``source`` if present."""
    with connect() as conn:
        row = conn.execute(
            "SELECT source, profile_md, feedback_count, feedback_latest_at, synthesized_at "
            "FROM linky_feedback_profiles WHERE source = ?",
            (source,),
        ).fetchone()
    return dict(row) if row else None


def upsert_linky_feedback_profile(
    *,
    source: str,
    profile_md: str,
    feedback_count: int,
    feedback_latest_at: Optional[str],
) -> None:
    """Persist a synthesized profile."""
    if not source or not (profile_md or "").strip():
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO linky_feedback_profiles "
            "(source, profile_md, feedback_count, feedback_latest_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET "
            "  profile_md=excluded.profile_md, "
            "  feedback_count=excluded.feedback_count, "
            "  feedback_latest_at=excluded.feedback_latest_at, "
            "  synthesized_at=datetime('now')",
            (source, profile_md.strip(), int(feedback_count), feedback_latest_at),
        )


def _format_feedback_example(row: dict[str, Any], *, title_cap: int = 86) -> str:
    title = " ".join((row.get("title") or row.get("url") or "(untitled)").split())
    if len(title) > title_cap:
        title = title[: title_cap - 3].rstrip() + "..."
    action = row.get("action") or "feedback"
    note = " ".join((row.get("note") or "").split())
    suffix = f" - {note}" if note else ""
    return f"- {title} ({action}){suffix}"


def _feedback_action_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = row.get("action") or "feedback"
        counts[action] = counts.get(action, 0) + 1
    return counts


def synthesize_linky_feedback_profile(*, source: str = "popular", limit: int = 80) -> dict[str, Any]:
    """Rebuild and persist the durable taste profile for one source.

    This deterministic synthesis turns explicit reactions into stable
    operating rules plus representative positive/negative anchors. The
    prompt then reads this profile before the freshest examples.
    """
    rows = recent_linky_feedback(source=source, limit=limit)
    fingerprint = linky_feedback_fingerprint(source=source)
    positives = [r for r in rows if int(r.get("label") or 0) > 0]
    negatives = [r for r in rows if int(r.get("label") or 0) < 0]
    hard_negatives = [
        r for r in negatives
        if r.get("action") == "rejected" or int(r.get("label") or 0) <= -2
    ]
    action_counts = _feedback_action_counts(rows)
    action_summary = ", ".join(
        f"{name}={count}" for name, count in sorted(action_counts.items())
    ) or "none yet"

    lines = [
        "## Jamie taste profile",
        "",
        f"Source: `{source}`. Synthesized from "
        f"{fingerprint['feedback_count']} explicit feedback signal(s).",
        "Operating bar: Jamie manually highlights only about 1-3 of every "
        "10 discovery items. Protect attention first; default to `SKIP:`.",
        f"Action mix: {action_summary}.",
        "",
        "Learned rules:",
        "- Treat reply, save, and Briefly reactions as strong positive examples.",
        "- Treat reviewed/fine as a weak negative: acceptable link, but not worth surfacing again.",
        "- Treat remove/rejected as a hard negative; avoid similar links unless a new angle is unmistakable.",
        "- Prefer durable, specific, curious pieces over product pages, launch chatter, listicles, or thin community heat.",
        "- A popular-feed score is supporting evidence only; it never overrides fit with Jamie's interests.",
    ]

    if positives:
        lines.extend(["", "Positive taste anchors:"])
        lines.extend(_format_feedback_example(r) for r in positives[:6])
    else:
        lines.extend(["", "Positive taste anchors: none recorded yet. Stay conservative."])

    if negatives:
        lines.extend(["", "Negative taste anchors:"])
        lines.extend(_format_feedback_example(r) for r in negatives[:8])
    else:
        lines.extend(["", "Negative taste anchors: none recorded yet."])

    if hard_negatives:
        lines.extend(["", "Hard-negative anchors:"])
        lines.extend(_format_feedback_example(r) for r in hard_negatives[:5])

    profile_md = "\n".join(lines)
    upsert_linky_feedback_profile(
        source=source,
        profile_md=profile_md,
        feedback_count=fingerprint["feedback_count"],
        feedback_latest_at=fingerprint["feedback_latest_at"],
    )
    return get_linky_feedback_profile(source=source) or {
        "source": source,
        "profile_md": profile_md,
        **fingerprint,
        "synthesized_at": None,
    }


def ensure_linky_feedback_profile(*, source: str = "popular") -> dict[str, Any]:
    """Return a current synthesized profile, rebuilding when feedback changed."""
    fingerprint = linky_feedback_fingerprint(source=source)
    profile = get_linky_feedback_profile(source=source)
    if (
        profile is None
        or int(profile.get("feedback_count") or 0) != fingerprint["feedback_count"]
        or profile.get("feedback_latest_at") != fingerprint["feedback_latest_at"]
    ):
        return synthesize_linky_feedback_profile(source=source)
    return profile


def linky_feedback_summary(*, source: str = "popular", limit: int = 40) -> str:
    """Render synthesized feedback plus recent examples as a prompt block.

    The scan job injects this before each per-link decision. Keep it
    short: the durable profile carries the rules; the recent examples
    keep the profile grounded in fresh gestures.
    """
    profile = ensure_linky_feedback_profile(source=source)
    rows = recent_linky_feedback(source=source, limit=limit)
    lines = [profile["profile_md"]]
    if not rows:
        lines.extend(["", "## Recent calibration examples", "", "No explicit reaction history yet."])
        return "\n".join(lines)

    positives = [r for r in rows if int(r.get("label") or 0) > 0]
    negatives = [r for r in rows if int(r.get("label") or 0) < 0]
    lines.extend([
        "",
        "## Recent calibration examples",
        "",
        f"Recent explicit feedback: {len(positives)} positive gesture(s), "
        f"{len(negatives)} negative gesture(s) in the last {len(rows)}.",
    ])
    if positives:
        lines.extend(["", "Recent positives:"])
        lines.extend(_format_feedback_example(r) for r in positives[:5])
    if negatives:
        lines.extend(["", "Recent negatives:"])
        lines.extend(_format_feedback_example(r) for r in negatives[:8])
    return "\n".join(lines)


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
