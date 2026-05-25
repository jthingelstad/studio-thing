"""Versioned schema migrations for ``apps/workshop_bot/data/workshop.db``.

The single source of truth for what shape the DB is in. ``schema.sql``
is the "create-from-scratch" snapshot; this module's :data:`MIGRATIONS`
tuple is the forward-only delta history applied on top of it.

Three migration shapes used to live in ``connection.py``
(``_COLUMN_MIGRATIONS`` / ``_DATA_MIGRATIONS`` / ``_PYTHON_MIGRATIONS``).
They've all collapsed into one :class:`Migration` shape — every migration
is a Python callable that takes an open :class:`sqlite3.Connection` and
mutates it however it needs to. The runner walks :data:`MIGRATIONS` in
order, skips ones whose id is already in ``schema_migrations``, applies
the rest, and records each on success.

To add a new migration:

1. Pick the next ``NNNN`` number (the highest existing id + 1).
2. Write a small ``def _m_NNNN_short_name(conn) -> None:`` body.
3. Append a :class:`Migration` entry to :data:`MIGRATIONS` referencing it.

The runner is invoked at bot startup (``apps/workshop_bot/bot.py`` →
``db.run_migrations()``) and again on every ``db.connect()`` whose
schema.sql hash has drifted (see ``connection._ensure_migrated``), so
long-running daemons pick up schema edits without a restart.

Operator surface — from the repo root::

    venv/bin/python -m apps.workshop_bot.tools.db.migrations status
    venv/bin/python -m apps.workshop_bot.tools.db.migrations pending
    venv/bin/python -m apps.workshop_bot.tools.db.migrations apply
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("workshop.db.migrations")


# ---------- migration record ----------

ApplyFn = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    """One forward-only schema/data delta.

    ``id``: stable string used as the row key in ``schema_migrations``.
        Convention: zero-padded sequence + snake_case description
        (``0007_agent_runs_cache_read_tokens``). Never change an id once
        it's shipped — recorded DBs would re-run the migration.
    ``description``: one-line human-readable purpose. Surfaced in the
        CLI status output and the "applying …" log line.
    ``apply``: idempotent body. Receives an autocommit
        :class:`sqlite3.Connection` (PRAGMA journal_mode=WAL,
        foreign_keys=ON). Raise on unrecoverable failure — the runner
        re-raises and leaves the migration unrecorded so it retries on
        the next boot.
    """

    id: str
    description: str
    apply: ApplyFn


# ---------- run report ----------

@dataclass(frozen=True)
class RunReport:
    applied: tuple[str, ...]
    skipped: tuple[str, ...]
    schema_hash: str
    total: int

    @property
    def latest_id(self) -> Optional[str]:
        if self.applied:
            return self.applied[-1]
        if self.skipped:
            return self.skipped[-1]
        return None


# ---------- helpers usable inside Migration.apply bodies ----------

def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return False
    return column in cols


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, type_decl: str,
) -> None:
    """``ALTER TABLE … ADD COLUMN`` only when the column isn't already
    there. Tolerates a concurrent add (another process raced us)."""
    if _has_column(conn, table, column):
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_decl}")
    except sqlite3.OperationalError:
        # Column added by another process between PRAGMA and ALTER. Idempotent: ignore.
        pass


# ---------- the migration list ----------
#
# Order is execution order. Append new entries — never reorder, never
# rewrite an existing id. The runner walks this list once per startup
# and skips anything whose id is already recorded.

# Path to the schema source-of-truth file. Resolved once at module load
# so individual migration bodies don't recompute it. Sits at
# apps/workshop_bot/db/schema.sql relative to this file.
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def _m_0001_initial_schema(conn: sqlite3.Connection) -> None:
    """Apply ``apps/workshop_bot/db/schema.sql`` — the create-from-scratch
    table+index+seed shape. Idempotent (``IF NOT EXISTS`` throughout) and
    always re-runs (see runner) so new tables/indexes added to schema.sql
    land on existing DBs without writing a column-migration."""
    conn.executescript(_SCHEMA_SQL_PATH.read_text(encoding="utf-8"))


def _m_0002_campaigns_copy(conn: sqlite3.Connection) -> None:
    """Add ``campaigns.copy`` — the actual ad creative that ran in a
    placement, so ``daily-metrics`` can read perf against the copy."""
    _add_column_if_missing(conn, "campaigns", "copy", "TEXT")


def _m_0003_pinboard_popular_seen_verdict_source(conn: sqlite3.Connection) -> None:
    """Add ``pinboard_popular_seen.verdict_source`` — which discovery
    feed first surfaced a URL so cross-source uplift can route back."""
    _add_column_if_missing(conn, "pinboard_popular_seen", "verdict_source", "TEXT")


def _m_0004_agent_runs_model(conn: sqlite3.Connection) -> None:
    """Add ``agent_runs.model`` — the Anthropic model id used for the
    call. Long-lived DBs pre-this-migration carry NULLs in this column
    for historical rows; new rows record real values."""
    _add_column_if_missing(conn, "agent_runs", "model", "TEXT")


def _m_0005_agent_runs_input_tokens(conn: sqlite3.Connection) -> None:
    """Add ``agent_runs.input_tokens`` — captured per-run from
    ``agent_loop``'s ``response.usage``. Drives the
    ``workshop-bot-llm-usage`` SKILL's cost queries."""
    _add_column_if_missing(conn, "agent_runs", "input_tokens", "INTEGER")


def _m_0006_agent_runs_output_tokens(conn: sqlite3.Connection) -> None:
    """Add ``agent_runs.output_tokens`` — counterpart to ``input_tokens``."""
    _add_column_if_missing(conn, "agent_runs", "output_tokens", "INTEGER")


def _m_0007_agent_runs_cache_read_tokens(conn: sqlite3.Connection) -> None:
    """Add ``agent_runs.cache_read_tokens`` — prompt-cache hits."""
    _add_column_if_missing(conn, "agent_runs", "cache_read_tokens", "INTEGER")


def _m_0008_agent_runs_cache_create_tokens(conn: sqlite3.Connection) -> None:
    """Add ``agent_runs.cache_create_tokens`` — prompt-cache writes."""
    _add_column_if_missing(conn, "agent_runs", "cache_create_tokens", "INTEGER")


def _m_0009_retire_non_pinboard_discovery_feeds(conn: sqlite3.Connection) -> None:
    """Clear rows from retired non-Pinboard discovery feeds. ``pinboard-scan``
    used to pull from HN/Lobsters/etc.; today only Pinboard popular runs.
    Sightings + research messages from the retired sources get dropped;
    ``verdict_source`` references to them get nulled."""
    conn.execute(
        "DELETE FROM popular_seen_sightings "
        "WHERE source NOT IN ('popular', 'toread')"
    )
    conn.execute(
        "DELETE FROM linky_research_messages "
        "WHERE source NOT IN ('popular', 'toread')"
    )
    conn.execute(
        "UPDATE pinboard_popular_seen SET verdict_source = NULL "
        "WHERE verdict_source IS NOT NULL "
        "AND verdict_source NOT IN ('popular', 'toread')"
    )


def _m_0011_editorial_comments_closed_at(conn: sqlite3.Connection) -> None:
    """Add ``editorial_comments.closed_at`` — set when a fresh review
    pass returned PASS (no new comments to chain via ``replaced_by_id``,
    but the prior pass's open comments are stale and shouldn't surface
    in the drawer). ``list_open_comments`` filters on both
    ``replaced_by_id IS NULL`` and ``closed_at IS NULL``."""
    _add_column_if_missing(conn, "editorial_comments", "closed_at", "TEXT")


def _m_0012_issue_windows_phase(conn: sqlite3.Connection) -> None:
    """Add ``issue_windows.phase`` — the publishing-spine phase of the active
    issue ('build' → 'publish'; see docs/publishing-process.md). The
    ``issue_cards`` table (per-phase persistent card handles) is created by the
    schema.sql re-apply (``CREATE TABLE IF NOT EXISTS``), so it needs no
    column-migration here."""
    _add_column_if_missing(conn, "issue_windows", "phase", "TEXT NOT NULL DEFAULT 'build'")


def _m_0013_campaigns_schema_overhaul(conn: sqlite3.Connection) -> None:
    """Reshape the campaigns ledger around Marky's actual workflow.

    Changes (all in one atomic rebuild):

    - Add ``id INTEGER PRIMARY KEY AUTOINCREMENT`` so rows have a short
      integer handle in addition to ``name`` (which stays UNIQUE NOT NULL
      and remains the FK target for ``campaign_metrics``).
    - Add ``url TEXT`` — the raw destination URL people clicked. DD80's
      placement uses UTM params (not ``?ref=``), so ``url`` is the
      truthful record of what the ad linked to; ``ref`` stays as the
      attribution lookup key.
    - Add ``platform TEXT`` — explicit channel (DenseDiscovery, LinkedIn,
      Bluesky, etc.) so Marky can group placements without parsing
      ``name``/``ref``.
    - Add ``actual_signups INTEGER`` — denormalised current count,
      updated by ``daily-metrics`` after each poll (and by Marky via
      ``campaigns__set_actual_signups`` for manual corrections). The
      KPI now lives at the top level of the row, not behind a join.
    - Add ``cost REAL`` — actual dollars paid for the placement.
      Combined with ``actual_signups`` gives cost-per-signup.
    - Drop ``ends_at`` — redundant with the ``status='sunset'`` flip.
    - Drop ``expected_signups`` / ``expected_traffic`` — speculative
      targets with no realised-actual partner column; not useful in
      practice and never carried real data.
    - Drop ``campaign_metrics.traffic`` — traffic is downstream of
      signups for Jamie's purposes; KPI focus narrows to signups.

    SQLite table-rebuild idiom (see https://www.sqlite.org/lang_altertable.html):
    create new table, copy retained columns, drop old, rename. FK
    constraints on the campaign_metrics side reference ``name``, which
    survives the rebuild as a UNIQUE NOT NULL column. Backfills ``url``
    + ``platform`` for the six known DD rows; backfills
    ``actual_signups`` from the latest ``campaign_metrics.signups``
    snapshot per campaign.
    """
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        # --- campaigns ---
        conn.execute(
            """
            CREATE TABLE campaigns_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                ref TEXT NOT NULL,
                url TEXT,
                platform TEXT,
                status TEXT NOT NULL DEFAULT 'live',
                started_at TEXT NOT NULL DEFAULT (date('now')),
                actual_signups INTEGER,
                cost REAL,
                copy TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO campaigns_new "
            "(name, ref, status, started_at, copy, notes) "
            "SELECT name, ref, status, started_at, copy, notes FROM campaigns"
        )
        conn.execute("DROP TABLE campaigns")
        conn.execute("ALTER TABLE campaigns_new RENAME TO campaigns")
        conn.execute("CREATE INDEX idx_campaigns_ref ON campaigns(ref)")

        # --- campaign_metrics: drop traffic ---
        conn.execute(
            """
            CREATE TABLE campaign_metrics_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_name TEXT NOT NULL REFERENCES campaigns(name),
                ran_at TEXT NOT NULL DEFAULT (datetime('now')),
                signups INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO campaign_metrics_new (id, campaign_name, ran_at, signups) "
            "SELECT id, campaign_name, ran_at, signups FROM campaign_metrics"
        )
        conn.execute("DROP TABLE campaign_metrics")
        conn.execute("ALTER TABLE campaign_metrics_new RENAME TO campaign_metrics")
        conn.execute(
            "CREATE INDEX idx_campaign_metrics_name "
            "ON campaign_metrics(campaign_name, ran_at DESC, id DESC)"
        )

        # --- backfill url + platform for the six known DD rows ---
        dd_url_backfills = [
            ("DD389", "https://weekly.thingelstad.com/?ref=DenseDiscovery-389"),
            ("DD388", "https://weekly.thingelstad.com/?ref=DenseDiscovery-388"),
            ("DD339", "https://weekly.thingelstad.com/?ref=DD-20250520"),
            ("DD338", "https://weekly.thingelstad.com/?ref=DD-20250513"),
            ("DD308", "https://weekly.thingelstad.com/?ref=DD-20241001"),
            (
                "DD80",
                "https://weekly.thingelstad.com/"
                "?utm_source=densediscovery&utm_medium=email"
                "&utm_campaign=newsletter-issue-80",
            ),
        ]
        for name, url in dd_url_backfills:
            conn.execute(
                "UPDATE campaigns SET url = ?, platform = 'DenseDiscovery' "
                "WHERE name = ?",
                (url, name),
            )

        # --- backfill actual_signups from the most recent metric per row ---
        conn.execute(
            "UPDATE campaigns SET actual_signups = ("
            "  SELECT signups FROM campaign_metrics "
            "  WHERE campaign_name = campaigns.name "
            "  ORDER BY ran_at DESC, id DESC LIMIT 1"
            ")"
        )

        # Scoped FK integrity check — only the two tables we touched.
        # A whole-DB `PRAGMA foreign_key_check` would surface pre-existing
        # orphans elsewhere that aren't this migration's concern.
        for tbl in ("campaign_metrics", "campaigns"):
            bad = conn.execute(f"PRAGMA foreign_key_check({tbl})").fetchall()
            if bad:
                raise RuntimeError(
                    f"foreign key check failed on {tbl} after rebuild: "
                    f"{[tuple(r) for r in bad]!r}"
                )
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _m_0010_strip_markers_from_issue_items_body_md(conn: sqlite3.Connection) -> None:
    """An older manual-seed path baked rendered ``<!-- cta:N -->`` /
    ``<!-- thanks:N -->`` markers into ``issue_items.body_md``. Marker
    placement is editorial state (lives in ``final.md``, never in row
    content); the embedded markers leak into every subsequent render.
    SQLite has no native regex, so this runs Python-side to clean any
    pre-existing rows once."""
    from ..issue_items_render import strip_membership_markers  # local — cycle
    rows = conn.execute(
        "SELECT id, body_md FROM issue_items "
        "WHERE body_md LIKE '%<!-- cta:%' OR body_md LIKE '%<!-- thanks:%'"
    ).fetchall()
    for row in rows:
        cleaned = strip_membership_markers(row["body_md"] or "")
        conn.execute(
            "UPDATE issue_items SET body_md = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (cleaned, int(row["id"])),
        )


# The id of the schema.sql-applying migration. The runner re-runs this
# one on every invocation regardless of whether it's recorded — schema.sql
# evolves over time, and the file's idempotent DDL is what lets new tables
# added to it appear on existing DBs without writing a fresh column
# migration.
SCHEMA_MIGRATION_ID = "0001_schema_sql"


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        id=SCHEMA_MIGRATION_ID,
        description="Apply schema.sql — create-or-update all tables, indexes, and seeds",
        apply=_m_0001_initial_schema,
    ),
    Migration(
        id="0002_campaigns_copy",
        description="Add campaigns.copy column for ad placement creative",
        apply=_m_0002_campaigns_copy,
    ),
    Migration(
        id="0003_pinboard_popular_seen_verdict_source",
        description="Add pinboard_popular_seen.verdict_source for cross-source uplift",
        apply=_m_0003_pinboard_popular_seen_verdict_source,
    ),
    Migration(
        id="0004_agent_runs_model",
        description="Add agent_runs.model (per-run LLM accounting)",
        apply=_m_0004_agent_runs_model,
    ),
    Migration(
        id="0005_agent_runs_input_tokens",
        description="Add agent_runs.input_tokens",
        apply=_m_0005_agent_runs_input_tokens,
    ),
    Migration(
        id="0006_agent_runs_output_tokens",
        description="Add agent_runs.output_tokens",
        apply=_m_0006_agent_runs_output_tokens,
    ),
    Migration(
        id="0007_agent_runs_cache_read_tokens",
        description="Add agent_runs.cache_read_tokens",
        apply=_m_0007_agent_runs_cache_read_tokens,
    ),
    Migration(
        id="0008_agent_runs_cache_create_tokens",
        description="Add agent_runs.cache_create_tokens",
        apply=_m_0008_agent_runs_cache_create_tokens,
    ),
    Migration(
        id="0009_retire_non_pinboard_discovery_feeds",
        description="Drop sightings + research messages from retired discovery feeds",
        apply=_m_0009_retire_non_pinboard_discovery_feeds,
    ),
    Migration(
        id="0010_strip_markers_from_issue_items_body_md",
        description="Scrub cta/thanks markers baked into issue_items.body_md",
        apply=_m_0010_strip_markers_from_issue_items_body_md,
    ),
    Migration(
        id="0011_editorial_comments_closed_at",
        description="Add editorial_comments.closed_at for PASS-closed comments",
        apply=_m_0011_editorial_comments_closed_at,
    ),
    Migration(
        id="0012_issue_windows_phase",
        description="Add issue_windows.phase (build|publish) for the publishing spine",
        apply=_m_0012_issue_windows_phase,
    ),
    Migration(
        id="0013_campaigns_schema_overhaul",
        description=(
            "campaigns: add id/url/platform/actual_signups/cost, "
            "drop ends_at/expected_*; drop campaign_metrics.traffic"
        ),
        apply=_m_0013_campaigns_schema_overhaul,
    ),
)


# ---------- runner ----------

def _record_migration(conn: sqlite3.Connection, migration_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)",
        (migration_id,),
    )


def applied_ids(conn: sqlite3.Connection) -> set[str]:
    """Set of migration ids already recorded in ``schema_migrations``.
    Returns an empty set if the table doesn't exist yet (fresh DB)."""
    try:
        rows = conn.execute("SELECT id FROM schema_migrations").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row["id"] for row in rows}


def pending(
    conn: sqlite3.Connection, migrations: tuple[Migration, ...] = MIGRATIONS,
) -> list[Migration]:
    """Migrations whose ids are not yet in ``schema_migrations``. The
    schema-applying migration is treated as "always pending" — it
    re-runs every invocation to pick up additions to schema.sql."""
    done = applied_ids(conn)
    return [m for m in migrations if m.id == SCHEMA_MIGRATION_ID or m.id not in done]


def run_migrations(
    conn_factory: Callable[[], "sqlite3.Connection"],
    *,
    migrations: tuple[Migration, ...] = MIGRATIONS,
    schema_path: Optional[Path] = None,
) -> RunReport:
    """Apply pending migrations. Returns a :class:`RunReport`.

    ``conn_factory`` is a callable returning a managed connection (the
    caller owns lifecycle — typically ``_open_raw(path).__enter__()``
    inside a ``with`` block, or a ``connect()`` context manager). The
    runner doesn't open the connection itself so callers can pass a
    pre-opened connection for tests / nested contexts.

    ``schema_path`` is optional and used only for the returned
    ``schema_hash`` — the actual schema.sql application is handled by
    the ``0001_schema_sql`` Migration entry.
    """
    schema_hash = ""
    if schema_path is not None:
        try:
            schema_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest()
        except OSError:
            schema_hash = ""

    applied: list[str] = []
    skipped: list[str] = []
    with conn_factory() as conn:
        done = applied_ids(conn)
        for m in migrations:
            already_recorded = m.id in done and m.id != SCHEMA_MIGRATION_ID
            if already_recorded:
                skipped.append(m.id)
                continue
            t0 = time.monotonic()
            logger.info("workshop.db: applying %s — %s", m.id, m.description)
            try:
                m.apply(conn)
            except Exception:
                logger.exception("workshop.db: migration %s FAILED", m.id)
                raise
            _record_migration(conn, m.id)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info("workshop.db: applied %s OK (%dms)", m.id, elapsed_ms)
            applied.append(m.id)

    return RunReport(
        applied=tuple(applied),
        skipped=tuple(skipped),
        schema_hash=schema_hash,
        total=len(migrations),
    )


# ---------- CLI ----------

def _status_text(conn: sqlite3.Connection, db_path: Path) -> str:
    done = applied_ids(conn)
    applied_at_by_id: dict[str, str] = {}
    if "schema_migrations" in _tables(conn):
        cols = {c[1] for c in conn.execute("PRAGMA table_info(schema_migrations)")}
        if "applied_at" in cols:
            for row in conn.execute(
                "SELECT id, applied_at FROM schema_migrations"
            ):
                applied_at_by_id[row["id"]] = str(row["applied_at"] or "")
    lines = [
        f"workshop.db (path: {db_path})",
        "",
    ]
    pending_count = sum(1 for m in MIGRATIONS if m.id not in done)
    applied_count = sum(1 for m in MIGRATIONS if m.id in done)
    lines.append(f"{applied_count} applied, {pending_count} pending")
    lines.append("")
    for m in MIGRATIONS:
        applied_at = applied_at_by_id.get(m.id, "")
        mark = "✓" if m.id in done else "·"
        lines.append(f"{mark} {m.id:50} {m.description:60} {applied_at}")
    return "\n".join(lines)


def _pending_text(conn: sqlite3.Connection) -> str:
    pend = pending(conn)
    # Drop the always-rerun schema migration from the pending list — it's
    # not interesting to operators ("is there schema.sql work to do?" → yes,
    # always; the point of `pending` is "is there a NEW migration?").
    pend = [m for m in pend if m.id != SCHEMA_MIGRATION_ID]
    if not pend:
        return "no pending migrations\n"
    lines = [f"{len(pend)} pending:"]
    for m in pend:
        lines.append(f"  · {m.id:50} {m.description}")
    return "\n".join(lines) + "\n"


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apps.workshop_bot.tools.db.migrations",
        description="Inspect or apply schema migrations for workshop.db",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Show applied + pending migration list")
    sub.add_parser("pending", help="Show only the pending migrations")
    sub.add_parser("apply", help="Apply any pending migrations (no-op if none)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Lazy imports — only when invoked as CLI — so importing the module
    # is cheap and side-effect-free.
    from . import connection as conn_mod

    path = conn_mod.db_path()
    if args.cmd == "status":
        with conn_mod._open_raw(path) as conn:
            print(_status_text(conn, path))
        return 0
    if args.cmd == "pending":
        with conn_mod._open_raw(path) as conn:
            print(_pending_text(conn), end="")
        return 0
    if args.cmd == "apply":
        report = run_migrations(
            lambda: conn_mod._open_raw(path),
            schema_path=conn_mod.SCHEMA_PATH,
        )
        if report.applied:
            print(f"Applied {len(report.applied)} migration(s):")
            for mid in report.applied:
                print(f"  ✓ {mid}")
        else:
            print("No pending migrations.")
        return 0
    return 1  # unreachable — argparse rejects unknown subcommands


if __name__ == "__main__":
    sys.exit(main())
