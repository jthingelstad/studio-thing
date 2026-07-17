"""Exact-lookup helpers over the historical archive in workshop.db.

These are pure SQL queries against the ``issues`` and ``issue_links`` tables
(seeded by ``pipeline/one-shot/backfill_issues_data_layer.py`` for historical
issues, kept current by ``/eddy issue put-to-bed`` for each newly-shipped
issue). The agents use them through ``archive_lookup__*`` agent tools so a
question like "what was issue #200 about?" or "how often has Jamie cited
this domain?" becomes a sub-millisecond DB read instead of an LLM call.

All helpers are read-only and return plain dicts / lists of dicts so the
caller doesn't carry a sqlite3 row around. ``None`` is returned when the
identifier doesn't resolve (missing issue, missing domain) — never an
exception.
"""

from __future__ import annotations

from typing import Any, Optional

from .db.connection import connect

_ISSUE_COLUMNS = (
    "number",
    "subject",
    "slug",
    "description",
    "publish_date",
    "image",
    "absolute_url",
    "buttondown_id",
    "word_count",
    "notable_count",
    "briefly_count",
    "domain_count",
    "link_count",
    "audio_url",
    "audio_duration_s",
    "audio_byte_size",
    "audio_voice",
    "era",
    "filed_at",
)

_ISSUE_SELECT = "SELECT " + ", ".join(_ISSUE_COLUMNS) + " FROM issues"


def _row_to_dict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def get_issue(number: int) -> Optional[dict[str, Any]]:
    """Full ``issues`` row for ``number``, or ``None`` if not filed."""
    with connect() as conn:
        row = conn.execute(
            _ISSUE_SELECT + " WHERE number = ?",
            (int(number),),
        ).fetchone()
    return _row_to_dict(row) if row else None


def find_issues_by_domain(
    domain: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Issues that cite ``domain`` in any link, newest issue first.

    Returns one row per (issue, occurrence-count-in-issue). Caller usually
    only cares about ``number`` + ``publish_date`` + ``subject``, but the
    shape mirrors a slim issue card for display.
    """
    if not domain:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT i.number, i.publish_date, i.subject, i.absolute_url, "
            "       COUNT(l.id) AS hit_count "
            "FROM issues i "
            "JOIN issue_links l ON l.issue_number = i.number "
            "WHERE l.domain = ? "
            "GROUP BY i.number "
            "ORDER BY i.number DESC "
            "LIMIT ?",
            (domain.lower(), int(limit)),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def find_issues_in_year(year: int) -> list[dict[str, Any]]:
    """All issues published in ``year``, newest first."""
    return find_issues_in_range(f"{int(year):04d}-01-01", f"{int(year):04d}-12-31")


def find_issues_in_range(start: str, end: str) -> list[dict[str, Any]]:
    """All issues whose ``publish_date`` is in [start, end] (inclusive),
    newest first. Dates are ISO YYYY-MM-DD strings."""
    with connect() as conn:
        rows = conn.execute(
            _ISSUE_SELECT + " WHERE publish_date BETWEEN ? AND ? " + "ORDER BY publish_date DESC",
            (start, end),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def link_history(url: str) -> list[dict[str, Any]]:
    """Every shipping of an exact ``url`` — issue number, section, position,
    publish date. Today Pinboard refuses to re-pin a URL that's already
    been bookmarked, so this is forward-looking for the day workshop hosts
    link commentary directly. Returns an empty list if the URL has never
    been shipped (the common case)."""
    if not url:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT i.number, i.publish_date, i.subject, "
            "       l.section, l.position, l.text, l.heading_context "
            "FROM issue_links l "
            "JOIN issues i ON i.number = l.issue_number "
            "WHERE l.url = ? "
            "ORDER BY i.number DESC, l.section, l.position",
            (url,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def domain_history(domain: str) -> dict[str, Any]:
    """Aggregate snapshot for ``domain``: link_count, issue_count,
    first/last issue numbers + dates, plus the latest 5 issue numbers
    that cited the domain. Returns an empty dict if the domain isn't
    in the corpus."""
    if not domain:
        return {}
    domain = domain.lower()
    with connect() as conn:
        agg = conn.execute(
            "SELECT link_count, issue_count, first_issue, last_issue "
            "FROM domain_stats WHERE domain = ?",
            (domain,),
        ).fetchone()
        if not agg:
            return {}
        recent_rows = conn.execute(
            "SELECT DISTINCT i.number, i.publish_date, i.subject "
            "FROM issue_links l "
            "JOIN issues i ON i.number = l.issue_number "
            "WHERE l.domain = ? "
            "ORDER BY i.number DESC LIMIT 5",
            (domain,),
        ).fetchall()
        first_row = conn.execute(
            "SELECT publish_date FROM issues WHERE number = ?",
            (int(agg["first_issue"]),),
        ).fetchone()
        last_row = conn.execute(
            "SELECT publish_date FROM issues WHERE number = ?",
            (int(agg["last_issue"]),),
        ).fetchone()
    return {
        "domain": domain,
        "link_count": int(agg["link_count"]),
        "issue_count": int(agg["issue_count"]),
        "first_issue": int(agg["first_issue"]),
        "last_issue": int(agg["last_issue"]),
        "first_date": first_row["publish_date"] if first_row else "",
        "last_date": last_row["publish_date"] if last_row else "",
        "recent": [_row_to_dict(r) for r in recent_rows],
    }


def recent_issues(n: int = 10) -> list[dict[str, Any]]:
    """The ``n`` most recently shipped issues, newest first."""
    with connect() as conn:
        rows = conn.execute(
            _ISSUE_SELECT + " ORDER BY number DESC LIMIT ?",
            (int(n),),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def aggregate_stats() -> dict[str, Any]:
    """Corpus-wide totals: issue count, link count, domain count, total
    words, audio coverage. Useful for archive overviews and site stats."""
    with connect() as conn:
        issues_row = conn.execute(
            "SELECT COUNT(*) AS total_issues, "
            "       COALESCE(SUM(word_count), 0) AS total_words, "
            "       COALESCE(SUM(link_count), 0) AS total_links, "
            "       COALESCE(SUM(notable_count), 0) AS total_notable, "
            "       COALESCE(SUM(briefly_count), 0) AS total_briefly, "
            "       SUM(CASE WHEN audio_url != '' THEN 1 ELSE 0 END) AS issues_with_audio, "
            "       MIN(publish_date) AS first_date, "
            "       MAX(publish_date) AS last_date "
            "FROM issues"
        ).fetchone()
        domain_count = conn.execute("SELECT COUNT(*) AS n FROM domain_stats").fetchone()["n"]
    total = int(issues_row["total_issues"] or 0)
    with_audio = int(issues_row["issues_with_audio"] or 0)
    return {
        "total_issues": total,
        "total_links": int(issues_row["total_links"] or 0),
        "total_notable": int(issues_row["total_notable"] or 0),
        "total_briefly": int(issues_row["total_briefly"] or 0),
        "total_words": int(issues_row["total_words"] or 0),
        "unique_domains": int(domain_count or 0),
        "issues_with_audio": with_audio,
        "audio_coverage_pct": round(100.0 * with_audio / total, 1) if total else 0.0,
        "first_date": issues_row["first_date"] or "",
        "last_date": issues_row["last_date"] or "",
    }


def list_issue_links(
    issue_number: int,
    *,
    section: Optional[str] = None,
) -> list[dict[str, Any]]:
    """All ``issue_links`` rows for one issue, ordered by section + position."""
    sql = (
        "SELECT section, position, url, text, domain, heading_context "
        "FROM issue_links WHERE issue_number = ?"
    )
    params: list[Any] = [int(issue_number)]
    if section:
        sql += " AND section = ?"
        params.append(section)
    sql += " ORDER BY section, position"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def derive_era(number: int) -> str:
    """Issue eras per project memory: 1–41 tinyletter, 42–130 mailchimp,
    131+ buttondown. Kept here so the put-to-bed job and the backfill
    script don't disagree on the boundary."""
    n = int(number)
    if n <= 41:
        return "tinyletter"
    if n <= 130:
        return "mailchimp"
    return "buttondown"
