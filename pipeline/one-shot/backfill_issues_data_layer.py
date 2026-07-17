"""One-shot historical backfill for ``workshop.db`` issues + issue_links.

Walks ``data/issues/{N}/`` for every shipped issue and inserts a row into
the ``issues`` table plus one row per link into ``issue_links``. Picks up
audio metadata from ``data/audio/manifest.json`` when present.

Idempotent — re-running upserts the issue row and rebuilds the link rows
for each issue (delete + insert) so a re-run produces identical state.
Skips in-flight issues whose ``metadata.json`` has empty ``buttondown_id``
or ``absolute_url`` — those get filed when they actually ship via
``/eddy issue put-to-bed``.

Usage::

    uv run --locked python pipeline/one-shot/backfill_issues_data_layer.py

The companion live-issue path is ``apps/workshop_bot/jobs/put_to_bed.py``;
they share field-extraction helpers via the ``archive_lookup`` /
``put_to_bed`` modules but this script is standalone (and one-shot) so
it can run before the bot has even seen any of these issues.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Line-buffered stdout so progress is visible when piped (project convention).
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from apps.workshop_bot.tools.archive_lookup import derive_era  # noqa: E402
from apps.workshop_bot.tools.db.connection import connect  # noqa: E402


DATA_ISSUES = REPO / "data" / "issues"
AUDIO_MANIFEST = REPO / "data" / "audio" / "manifest.json"


def _load_audio_manifest() -> dict[str, dict]:
    if not AUDIO_MANIFEST.exists():
        return {}
    raw = json.loads(AUDIO_MANIFEST.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if k.isdigit()}


def _iter_issue_dirs() -> list[Path]:
    out: list[Path] = []
    for p in DATA_ISSUES.iterdir():
        if not p.is_dir():
            continue
        if not p.name.isdigit():
            continue
        if not (p / "metadata.json").exists():
            continue
        out.append(p)
    out.sort(key=lambda d: int(d.name))
    return out


def _load_metadata(issue_dir: Path) -> dict:
    return json.loads((issue_dir / "metadata.json").read_text(encoding="utf-8"))


def _load_links(issue_dir: Path) -> dict:
    links_path = issue_dir / "links.json"
    if not links_path.exists():
        return {"notable_links": [], "briefly_links": [], "domains": [], "word_count": 0}
    return json.loads(links_path.read_text(encoding="utf-8"))


def _normalize_publish_date(raw: str) -> str:
    """Accept ISO datetime (``2017-05-13T13:00:00Z``) or date-only and
    return YYYY-MM-DD. SQLite lexicographic compare relies on this shape."""
    if not raw:
        return ""
    return raw[:10]


def _is_shipped(meta: dict) -> bool:
    return bool(meta.get("buttondown_id")) and bool(meta.get("absolute_url"))


def upsert_issue(conn, *, meta: dict, links: dict, audio: dict | None) -> None:
    number = int(meta["number"])
    publish_date = _normalize_publish_date(meta.get("publish_date", ""))
    notable = links.get("notable_links") or []
    briefly = links.get("briefly_links") or []
    domains = links.get("domains") or []
    word_count = int(links.get("word_count") or 0)
    audio = audio or {}

    conn.execute(
        "INSERT INTO issues "
        "  (number, subject, slug, description, publish_date, image, "
        "   absolute_url, buttondown_id, word_count, notable_count, "
        "   briefly_count, domain_count, link_count, audio_url, "
        "   audio_duration_s, audio_byte_size, audio_voice, era) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(number) DO UPDATE SET "
        "  subject=excluded.subject, "
        "  slug=excluded.slug, "
        "  description=excluded.description, "
        "  publish_date=excluded.publish_date, "
        "  image=excluded.image, "
        "  absolute_url=excluded.absolute_url, "
        "  buttondown_id=excluded.buttondown_id, "
        "  word_count=excluded.word_count, "
        "  notable_count=excluded.notable_count, "
        "  briefly_count=excluded.briefly_count, "
        "  domain_count=excluded.domain_count, "
        "  link_count=excluded.link_count, "
        "  audio_url=excluded.audio_url, "
        "  audio_duration_s=excluded.audio_duration_s, "
        "  audio_byte_size=excluded.audio_byte_size, "
        "  audio_voice=excluded.audio_voice, "
        "  era=excluded.era, "
        "  filed_at=datetime('now')",
        (
            number,
            meta.get("subject", "") or "",
            meta.get("slug", "") or "",
            meta.get("description", "") or "",
            publish_date,
            meta.get("image", "") or "",
            meta.get("absolute_url", "") or "",
            meta.get("buttondown_id", "") or "",
            word_count,
            len(notable),
            len(briefly),
            len(domains),
            len(notable) + len(briefly),
            audio.get("audio_url", "") or "",
            audio.get("audio_duration_seconds"),
            audio.get("audio_byte_size"),
            audio.get("audio_voice", "") or "",
            derive_era(number),
        ),
    )

    # Rebuild link rows for this issue — cheaper than per-link upsert and
    # semantically clean: links.json is the source of truth.
    conn.execute("DELETE FROM issue_links WHERE issue_number = ?", (number,))
    for section_name, items in (("notable", notable), ("briefly", briefly)):
        for idx, link in enumerate(items):
            conn.execute(
                "INSERT INTO issue_links "
                "  (issue_number, section, position, url, text, domain, heading_context) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    number,
                    section_name,
                    idx,
                    link.get("url", "") or "",
                    link.get("text", "") or "",
                    (link.get("domain", "") or "").lower(),
                    link.get("heading_context", "") or "",
                ),
            )


def run() -> int:
    audio_index = _load_audio_manifest()
    issue_dirs = _iter_issue_dirs()
    print(f"backfill: scanning {len(issue_dirs)} issue dirs under {DATA_ISSUES}")
    print(f"backfill: audio manifest has {len(audio_index)} keyed entries")

    filed = 0
    skipped_inflight = 0
    total_links = 0

    with connect() as conn:
        for issue_dir in issue_dirs:
            number = int(issue_dir.name)
            meta = _load_metadata(issue_dir)
            if not _is_shipped(meta):
                print(f"  WT{number}: skipped (in-flight; missing buttondown_id/absolute_url)")
                skipped_inflight += 1
                continue
            links = _load_links(issue_dir)
            audio = audio_index.get(str(number))
            upsert_issue(conn, meta=meta, links=links, audio=audio)
            link_n = len(links.get("notable_links") or []) + len(links.get("briefly_links") or [])
            total_links += link_n
            audio_tag = "🎧" if audio else "  "
            print(f"  WT{number}: filed ({link_n} links) {audio_tag} {meta.get('subject','')[:70]}")
            filed += 1

    print()
    print(f"backfill: done. {filed} issues filed, {skipped_inflight} in-flight skipped, {total_links} link rows written.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
