"""SQLite row-level helpers for the workshop bot."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from .connection import connect


def insert_agent_output(
    agent_name: str,
    output_type: str,
    content: str,
    metadata: Optional[dict[str, Any]] = None,
    related_issue: Optional[int] = None,
    status: str = "ready",
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO agent_outputs "
            "(agent_name, output_type, content, metadata, status, related_issue) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                agent_name,
                output_type,
                content,
                json.dumps(metadata) if metadata else None,
                status,
                related_issue,
            ),
        )
        return int(cur.lastrowid or 0)


def upsert_link_candidate(
    url: str,
    title: Optional[str],
    description: Optional[str],
    pinboard_tags: Optional[str],
    pinboard_added: Optional[str],
    linky_summary: Optional[str] = None,
    linky_themes: Optional[list[str]] = None,
    archive_resonance: Optional[str] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO link_candidates "
            "(url, title, description, pinboard_tags, pinboard_added, "
            " linky_summary, linky_themes, archive_resonance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET "
            "  title=excluded.title, "
            "  description=excluded.description, "
            "  pinboard_tags=excluded.pinboard_tags, "
            "  pinboard_added=excluded.pinboard_added, "
            "  linky_summary=COALESCE(excluded.linky_summary, link_candidates.linky_summary), "
            "  linky_themes=COALESCE(excluded.linky_themes, link_candidates.linky_themes), "
            "  archive_resonance=COALESCE(excluded.archive_resonance, link_candidates.archive_resonance)",
            (
                url,
                title,
                description,
                pinboard_tags,
                pinboard_added,
                linky_summary,
                json.dumps(linky_themes) if linky_themes else None,
                archive_resonance,
            ),
        )
        return int(cur.lastrowid or 0)


def recent_link_candidates(limit: int = 30) -> list[dict[str, Any]]:
    """Return the most recently added/updated link_candidates rows."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT url, title, description, pinboard_tags, pinboard_added, "
            "       linky_summary, linky_themes, status "
            "FROM link_candidates "
            "ORDER BY COALESCE(pinboard_added, created_at) DESC "
            "LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- agent memory ----------

NOTE_KINDS = ("preference", "observation", "todo", "context", "theme")


def insert_agent_note(
    *,
    agent_name: str,
    kind: str,
    content: str,
    key: Optional[str] = None,
    related_issue: Optional[int] = None,
    expires_at: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO agent_notes "
            "(agent_name, kind, key, content, related_issue, expires_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                agent_name,
                kind,
                key,
                content,
                related_issue,
                expires_at,
                json.dumps(metadata) if metadata else None,
            ),
        )
        return int(cur.lastrowid or 0)


def query_agent_notes(
    *,
    agent_name: Optional[str] = None,
    kind: Optional[str] = None,
    query: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return notes ordered newest-first. Filter by agent, kind, or text match."""
    sql_parts = [
        "SELECT id, agent_name, kind, key, content, related_issue, status, "
        "       created_at, expires_at "
        "FROM agent_notes WHERE 1=1"
    ]
    params: list[Any] = []
    if agent_name:
        sql_parts.append("AND agent_name = ?")
        params.append(agent_name)
    if kind:
        sql_parts.append("AND kind = ?")
        params.append(kind)
    if not include_resolved:
        sql_parts.append("AND status = 'active'")
    if query:
        sql_parts.append("AND (content LIKE ? OR key LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
    sql_parts.append(
        "AND (expires_at IS NULL OR expires_at > datetime('now')) "
        "ORDER BY created_at DESC LIMIT ?"
    )
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()
    return [dict(r) for r in rows]


def update_agent_note_status(note_id: int, status: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE agent_notes SET status = ? WHERE id = ?",
            (status, note_id),
        )
        return cur.rowcount > 0


# ---------- subscriber events (Marky) ----------

def upsert_subscriber_event(
    *,
    external_id: str,
    email_hash: str,
    event_type: str,
    event_date: str,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Returns True if this is a new (external_id, event_type) pair."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscriber_events_seen "
            "(external_id, email_hash, event_type, event_date, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                external_id,
                email_hash,
                event_type,
                event_date,
                json.dumps(metadata) if metadata else None,
            ),
        )
        return cur.rowcount > 0


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



# ---------- follow-ups (agent commitments — the targeted heartbeat) ----------

FOLLOW_UP_PERSONAS = ("eddy", "linky", "marky", "patty")
FOLLOW_UP_KINDS = ("time", "issue")


def insert_follow_up(
    *,
    persona: str,
    trigger_kind: str,
    note: str,
    due_at: Optional[str] = None,
    trigger_issue: Optional[int] = None,
    channel_env: Optional[str] = None,
    created_by: Optional[str] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO follow_ups "
            "(persona, channel_env, trigger_kind, due_at, trigger_issue, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (persona, channel_env, trigger_kind, due_at,
             int(trigger_issue) if trigger_issue is not None else None, note, created_by),
        )
        return int(cur.lastrowid or 0)


def open_follow_ups(*, persona: Optional[str] = None) -> list[dict[str, Any]]:
    """Pending (not fired, not cancelled) follow-ups, oldest first."""
    sql = (
        "SELECT id, persona, channel_env, trigger_kind, due_at, trigger_issue, note, "
        "       created_by, created_at "
        "FROM follow_ups WHERE fired_at IS NULL AND cancelled_at IS NULL"
    )
    params: list[Any] = []
    if persona:
        sql += " AND persona = ?"
        params.append(persona)
    sql += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_follow_up(follow_up_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (int(follow_up_id),)).fetchone()
    return dict(row) if row else None


def due_follow_ups(*, now_iso: str, active_issue: Optional[int]) -> list[dict[str, Any]]:
    """Open follow-ups that are due now: time-based ones whose ``due_at`` has
    passed, plus issue-based ones once the active in-flight issue has reached
    their ``trigger_issue``. Oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, persona, channel_env, trigger_kind, due_at, trigger_issue, note, "
            "       created_by, created_at "
            "FROM follow_ups "
            "WHERE fired_at IS NULL AND cancelled_at IS NULL AND ("
            "  (trigger_kind = 'time' AND due_at IS NOT NULL AND due_at <= ?) OR "
            "  (trigger_kind = 'issue' AND trigger_issue IS NOT NULL AND ? IS NOT NULL AND trigger_issue <= ?)"
            ") ORDER BY created_at",
            (now_iso, active_issue, active_issue if active_issue is not None else -1),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_follow_up_fired(follow_up_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE follow_ups SET fired_at = datetime('now') "
            "WHERE id = ? AND fired_at IS NULL AND cancelled_at IS NULL",
            (int(follow_up_id),),
        )
        return cur.rowcount > 0


def cancel_follow_up(follow_up_id: int, *, persona: Optional[str] = None) -> bool:
    """Cancel an open follow-up. If ``persona`` is given, only cancels it when
    it belongs to that persona (so an agent can't cancel another's)."""
    sql = "UPDATE follow_ups SET cancelled_at = datetime('now') WHERE id = ? AND fired_at IS NULL AND cancelled_at IS NULL"
    params: list[Any] = [int(follow_up_id)]
    if persona:
        sql += " AND persona = ?"
        params.append(persona)
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount > 0


def recent_subscriber_events(
    *, limit: int = 30, event_type: Optional[str] = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT external_id, email_hash, event_type, event_date, created_at "
        "FROM subscriber_events_seen"
    )
    params: list[Any] = []
    if event_type:
        sql += " WHERE event_type = ?"
        params.append(event_type)
    sql += " ORDER BY event_date DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------- issue windows (operator-set publishing schedule) ----------


def set_issue_window(
    *,
    issue_number: int,
    pub_date: str,
    end_date: str,
    start_date: str,
    day_count: int,
    set_by: Optional[str] = None,
) -> dict[str, Any]:
    """Atomically deactivate any current active window and upsert this
    issue's row as the new active window.

    Returns the resulting active row.
    """
    with connect() as conn:
        # The connection runs in autocommit (isolation_level=None) so
        # explicit BEGIN/COMMIT brackets the two writes into one
        # transaction — keeps the partial-unique-on-is_active index
        # from tripping mid-update.
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE issue_windows SET is_active = 0 WHERE is_active = 1"
            )
            conn.execute(
                "INSERT INTO issue_windows "
                "(issue_number, pub_date, end_date, start_date, day_count, "
                " is_active, set_at, set_by) "
                "VALUES (?, ?, ?, ?, ?, 1, datetime('now'), ?) "
                "ON CONFLICT(issue_number) DO UPDATE SET "
                "  pub_date=excluded.pub_date, "
                "  end_date=excluded.end_date, "
                "  start_date=excluded.start_date, "
                "  day_count=excluded.day_count, "
                "  is_active=1, "
                "  set_at=datetime('now'), "
                "  set_by=excluded.set_by",
                (issue_number, pub_date, end_date, start_date, day_count, set_by),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return get_active_issue_window() or {}


def get_active_issue_window() -> Optional[dict[str, Any]]:
    """Return the currently active issue window, or None if none set."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       set_at, set_by "
            "FROM issue_windows WHERE is_active = 1 LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_issue_window(issue_number: int) -> Optional[dict[str, Any]]:
    """Return one issue window by number (active or not)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, set_at, set_by "
            "FROM issue_windows WHERE issue_number = ?",
            (int(issue_number),),
        ).fetchone()
    return dict(row) if row else None


def list_issue_windows(*, limit: int = 12) -> list[dict[str, Any]]:
    """Return recent issue windows, newest issue number first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT issue_number, pub_date, end_date, start_date, day_count, "
            "       is_active, set_at, set_by "
            "FROM issue_windows ORDER BY issue_number DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- job locks (single-asset serialization for the jobs pipeline) ----------


def _pid_alive(pid: int) -> bool:
    """True if ``pid`` looks like a live process. A nonexistent pid is
    dead; a permission error means the process exists but isn't ours to
    signal (won't happen in a single-user deployment, but treat as live)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def acquire_job_lock(*, asset: str, job: str, pid: int) -> Optional[dict[str, Any]]:
    """Try to lock ``asset`` for ``job``.

    Returns ``None`` on success. If the asset is already held by a *live*
    process, returns that lock row as a dict (the caller surfaces an
    "already running" message). A lock held by a dead pid is stale —
    deleted and re-acquired. (workshop_bot is single-process, so a live
    holder is genuinely another running job; a dead holder is a leftover
    from a prior crashed instance, since a restart gets a new pid.)
    """
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT asset, job, started_at, pid FROM job_locks WHERE asset = ?",
                (asset,),
            ).fetchone()
            if row is not None:
                if _pid_alive(row["pid"]):
                    conn.execute("ROLLBACK")
                    return dict(row)
                conn.execute("DELETE FROM job_locks WHERE asset = ?", (asset,))
            conn.execute(
                "INSERT INTO job_locks (asset, job, started_at, pid) "
                "VALUES (?, ?, datetime('now'), ?)",
                (asset, job, int(pid)),
            )
            conn.execute("COMMIT")
            return None
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_job_lock(asset: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM job_locks WHERE asset = ?", (asset,))
        return cur.rowcount > 0


def list_job_locks() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT asset, job, started_at, pid FROM job_locks ORDER BY started_at"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- goals (Patty's milestone progression) ----------


def get_active_goal() -> Optional[dict[str, Any]]:
    """The current goal — the row with ``achieved_at IS NULL`` — or None."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, target_kind, target_value, started_at, achieved_at, notes "
            "FROM goals WHERE achieved_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def recent_achieved_goals(limit: int = 3) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, target_kind, target_value, started_at, achieved_at, notes "
            "FROM goals WHERE achieved_at IS NOT NULL ORDER BY achieved_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_goal(*, target_kind: str, target_value: int, started_at: Optional[str] = None,
                notes: Optional[str] = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO goals (target_kind, target_value, started_at, notes) "
            "VALUES (?, ?, COALESCE(?, date('now')), ?)",
            (target_kind, int(target_value), started_at, notes),
        )
        return int(cur.lastrowid or 0)


def mark_goal_achieved(
    goal_id: int, *, achieved_at: Optional[str] = None, notes: Optional[str] = None
) -> bool:
    sets = ["achieved_at = COALESCE(?, date('now'))"]
    params: list[Any] = [achieved_at]
    if notes is not None:
        sets.append("notes = ?")
        params.append(notes)
    params.append(int(goal_id))
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE goals SET {', '.join(sets)} WHERE id = ? AND achieved_at IS NULL",
            params,
        )
        return cur.rowcount > 0


# ---------- campaigns (Marky's ad-placement ledger) ----------


def insert_campaign(
    *,
    name: str,
    ref: str,
    expected_signups: Optional[int] = None,
    expected_traffic: Optional[int] = None,
    started_at: Optional[str] = None,
    ends_at: Optional[str] = None,
    copy: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """Insert a campaign. Returns False if a campaign with that name
    already exists (ON CONFLICT DO NOTHING)."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO campaigns (name, ref, status, started_at, ends_at, "
            " expected_signups, expected_traffic, copy, notes) "
            "VALUES (?, ?, 'live', COALESCE(?, date('now')), ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO NOTHING",
            (name, ref, started_at, ends_at,
             int(expected_signups) if expected_signups is not None else None,
             int(expected_traffic) if expected_traffic is not None else None, copy, notes),
        )
        return cur.rowcount > 0


def get_campaign(name: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT name, ref, status, started_at, ends_at, expected_signups, "
            "       expected_traffic, copy, notes FROM campaigns WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def active_campaigns() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, ref, status, started_at, ends_at, expected_signups, "
            "       expected_traffic, copy, notes FROM campaigns WHERE status = 'live' "
            "ORDER BY started_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def active_campaigns_with_age() -> list[dict[str, Any]]:
    """Active campaigns annotated with ``days_running`` — used by
    ``build_marky_context``."""
    from datetime import datetime as _dt

    out: list[dict[str, Any]] = []
    today = _dt.now().date()
    for c in active_campaigns():
        days = None
        try:
            d = _dt.strptime(str(c.get("started_at"))[:10], "%Y-%m-%d").date()
            days = (today - d).days
        except (TypeError, ValueError):
            pass
        out.append({**c, "days_running": days})
    return out


def set_campaign_status(name: str, status: str) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE campaigns SET status = ? WHERE name = ?", (status, name))
        return cur.rowcount > 0


def set_campaign_copy(name: str, copy: Optional[str]) -> bool:
    """Set (or clear, with ``None``) the promo copy for a campaign.
    Returns False if no campaign with that name exists."""
    with connect() as conn:
        cur = conn.execute("UPDATE campaigns SET copy = ? WHERE name = ?", (copy, name))
        return cur.rowcount > 0


# Fields a campaign's row may be edited in place (the name is the PK and
# referenced by campaign_metrics, so it's immutable; status flips via
# set_campaign_status / sunset).
CAMPAIGN_EDITABLE = ("ref", "expected_signups", "expected_traffic", "started_at", "ends_at", "copy", "notes")


def update_campaign(name: str, **changes: Any) -> Optional[dict[str, Any]]:
    """Update an existing campaign's editable fields in place. Only keys in
    :data:`CAMPAIGN_EDITABLE` with a non-``None`` value are written (a
    ``None`` means "leave it alone"); ``expected_signups`` /
    ``expected_traffic`` are coerced to int. Returns the updated row, or
    ``None`` if no campaign with that name exists."""
    fields: dict[str, Any] = {}
    for k, v in changes.items():
        if k not in CAMPAIGN_EDITABLE or v is None:
            continue
        if k in ("expected_signups", "expected_traffic"):
            fields[k] = int(v)
        else:
            fields[k] = v
    if get_campaign(name) is None:
        return None
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with connect() as conn:
            conn.execute(f"UPDATE campaigns SET {sets} WHERE name = ?", [*fields.values(), name])
    return get_campaign(name)


def insert_campaign_metric(*, campaign_name: str, signups: Optional[int],
                           traffic: Optional[int]) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO campaign_metrics (campaign_name, signups, traffic) VALUES (?, ?, ?)",
            (campaign_name,
             int(signups) if signups is not None else None,
             int(traffic) if traffic is not None else None),
        )
        return int(cur.lastrowid or 0)


def latest_campaign_metric(campaign_name: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, campaign_name, ran_at, signups, traffic FROM campaign_metrics "
            "WHERE campaign_name = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (campaign_name,),
        ).fetchone()
    return dict(row) if row else None


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


# ---------- draft digests (Eddy's delta context for update-draft) ----------


def insert_draft_digest(
    *,
    issue: int,
    word_count: int,
    notable_count: int,
    brief_count: int,
    journal_count: int,
    intro_present: bool,
    currently_present: bool,
    haiku_present: bool,
    cover_present: bool,
    source_hash: Optional[str] = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO draft_digests "
            "(issue, word_count, notable_count, brief_count, journal_count, "
            " intro_present, currently_present, haiku_present, cover_present, source_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(issue), int(word_count), int(notable_count), int(brief_count),
                int(journal_count),
                1 if intro_present else 0, 1 if currently_present else 0,
                1 if haiku_present else 0, 1 if cover_present else 0, source_hash,
            ),
        )
        return int(cur.lastrowid or 0)


def latest_draft_digest(issue: int) -> Optional[dict[str, Any]]:
    """Most recent digest row for ``issue`` — i.e. the prior update-draft
    run's snapshot, used to compute the delta for the current run."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, issue, ran_at, word_count, notable_count, brief_count, "
            "       journal_count, intro_present, currently_present, haiku_present, "
            "       cover_present, source_hash "
            "FROM draft_digests WHERE issue = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (int(issue),),
        ).fetchone()
    return dict(row) if row else None


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


def recent_agent_runs(limit: int = 8) -> list[dict[str, Any]]:
    """Most recent agent_runs rows, newest first — for the ``/eddy
    status`` snapshot ("what's the bot done lately / did anything fail")."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, agent_name, trigger, status, duration_ms, error, "
            "       records_written, model, input_tokens, output_tokens, "
            "       cache_read_tokens, cache_create_tokens, "
            "       started_at, ended_at "
            "FROM agent_runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


class AgentRun:
    """Context manager that opens an agent_runs row and closes it with the result.

    Trigger label convention
    ------------------------

    ``trigger`` is the string written to the ``trigger`` column. A single
    ``agent_runs`` row covers one logical unit of work (one cron fire,
    one slash invocation), regardless of how many internal LLM calls it
    makes — open one ``AgentRun`` per job, not per ``bot.core``.

    The label shape is:

      - **Bare job name** for jobs that make one LLM call (or one
        logical batch under a single context manager):
        ``compose-haiku``, ``compose-cta``, ``daily-metrics``,
        ``promotion-prep``, ``pinboard-scan``, ``review-text``,
        ``linky-research``, ``create-final``, ``follow-up``.
      - **``<job>:<sub>``** when a *single job module* opens multiple
        ``AgentRun`` blocks for distinguishable LLM passes that you
        want to query independently in ``agent_runs``:
        ``update-draft:html-review`` + ``update-draft:editorial-card``
        (Eddy's two separate review passes inside ``update-draft``);
        ``compose-meta:subject`` + ``compose-meta:description``
        (the two passes inside ``compose-meta``).
      - **``scheduled:<job-id>``** is added by the scheduler runner
        for the outer cron context (not by job code itself).
      - **``mention``** by ``PersonaBot.on_message`` for an
        @-mention-driven turn outside the job pipeline.

    Adding a new sub-label is the right move only when you'd actually
    query ``agent_runs`` for the distinction (cost analysis,
    latency-bucketing one pass vs another). Otherwise the bare job
    name is enough and the JobResult / logs carry the rest.
    """

    def __init__(self, agent_name: str, trigger: str) -> None:
        self.agent_name = agent_name
        self.trigger = trigger
        self.run_id: Optional[int] = None
        self._t0 = 0.0
        self.records_written = 0
        self.error: Optional[str] = None
        # LLM accounting — set via `record_meta(meta)` from agent_loop's
        # return dict (or any equivalent {"model": …, "usage": {…}} shape).
        # Stored on __exit__. Accumulates across multiple record_meta calls
        # so a single AgentRun covering many internal LLM calls (e.g.,
        # pinboard-scan's per-link loop) sums correctly.
        self.model: Optional[str] = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_create_tokens = 0
        self._has_usage = False

    def record_meta(self, meta: Optional[dict[str, Any]]) -> None:
        """Capture model + accumulate token usage from agent_loop's response.

        ``meta`` is the second element of the ``(reply, meta)`` tuple that
        ``bot.core(...)`` / ``agent_loop.run_async(...)`` returns:

            {"model": "claude-sonnet-4-6",
             "usage": {"input": int, "output": int,
                       "cache_read": int, "cache_create": int},
             "iterations": int, "tool_calls": [...]}

        Safe to call zero, one, or many times within a single AgentRun
        block. Last non-None model wins; usage adds. Tolerates a
        ``None`` meta or a meta without the usage / model keys (logs
        but doesn't raise).
        """
        if not meta:
            return
        model = meta.get("model")
        if model:
            self.model = model
        usage = meta.get("usage") or {}
        self.input_tokens += int(usage.get("input", 0) or 0)
        self.output_tokens += int(usage.get("output", 0) or 0)
        self.cache_read_tokens += int(usage.get("cache_read", 0) or 0)
        self.cache_create_tokens += int(usage.get("cache_create", 0) or 0)
        if usage:
            self._has_usage = True

    def __enter__(self) -> "AgentRun":
        self._t0 = time.monotonic()
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs (agent_name, trigger, status) "
                "VALUES (?, ?, 'pending')",
                (self.agent_name, self.trigger),
            )
            self.run_id = int(cur.lastrowid or 0)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = int((time.monotonic() - self._t0) * 1000)
        if exc is not None:
            status = "error"
            self.error = f"{exc_type.__name__}: {exc}" if self.error is None else self.error
        else:
            status = "success"
        # NULL the token columns when no LLM call was recorded — keeps
        # SUM() reports clean (untracked rows don't dilute the avg).
        in_t = self.input_tokens if self._has_usage else None
        out_t = self.output_tokens if self._has_usage else None
        cr_t = self.cache_read_tokens if self._has_usage else None
        cc_t = self.cache_create_tokens if self._has_usage else None
        with connect() as conn:
            conn.execute(
                "UPDATE agent_runs SET status=?, duration_ms=?, error=?, "
                "records_written=?, model=?, input_tokens=?, output_tokens=?, "
                "cache_read_tokens=?, cache_create_tokens=?, "
                "ended_at=datetime('now') WHERE id=?",
                (status, duration_ms, self.error, self.records_written,
                 self.model, in_t, out_t, cr_t, cc_t, self.run_id),
            )
        # Don't suppress exceptions
