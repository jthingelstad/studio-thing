"""``feedbin-ingest`` — poll Jamie's Feedbin starred-items feed and
mirror each new item as a Pinboard ``toread`` bookmark.

Why: Feedbin is where Jamie reads, Pinboard is the curation surface
Linky watches. Starring an article in Feedbin is a "consider this for
the Weekly Thing" signal; this job turns that signal into a Pinboard
``toread=yes shared=yes`` bookmark, and Linky's existing
``pinboard-scan`` toread lane surfaces it as a research card on the
next scan. No bespoke per-link card flow — Feedbin is an ingestion
source, not a discovery feed.

Dedup is two-layer:

1. ``feedbin_starred_seen`` (workshop.db) keyed by the Feedbin item's
   stable GUID. Re-stars after the first ingest are silent no-ops; we
   never call Pinboard twice for the same GUID.
2. ``pinboard.posts_add(replace=False)`` is the backstop — even if the
   local dedup table got blown away, Pinboard refuses the duplicate.

Best-effort throughout: a Feedbin fetch error, a Pinboard error on one
item, or a missing ``FEEDBIN_STARRED_FEED_URL`` env var all PASS silently
(logged) rather than failing the cron. The next firing retries.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from ..systems.pinboard import client as pinboard_client
from ..tools import db, feedbin
from . import _base

logger = logging.getLogger("workshop.jobs.feedbin_ingest")

NAME = "feedbin-ingest"

# Cap how many items we touch per run. The starred feed is typically
# small (Feedbin keeps ~recent stars); a cap protects against an
# unforeseen flood (e.g. a bulk re-star).
_PER_RUN_CAP = 25


def _ingest_items(items: list[dict[str, Any]]) -> dict[str, int]:
    """Synchronous core: dedup against ``feedbin_starred_seen``, call
    ``pinboard.posts_add`` for each unseen item, record the result.
    Returns counters for the run summary."""
    if not items:
        return {"new": 0, "skipped": 0, "errors": 0}

    # Newest first in the feed → process newest first too. Cap the slice.
    items = items[:_PER_RUN_CAP]
    guids = [it["guid"] for it in items]
    seen = db.feedbin_seen_guids(guids)

    new_count = 0
    skipped = 0
    errors = 0
    for item in items:
        guid = item["guid"]
        if guid in seen:
            skipped += 1
            continue
        url = item["url"]
        title = item.get("title") or url
        # Deliberately don't carry Feedbin's RSS <description> across to
        # Pinboard — the bookmark's `extended` field stays empty so Jamie
        # can write his own commentary later (via a Discord reply on the
        # toread research card). Feedbin descriptions are often article
        # excerpts, not editorial intent, and we'd rather not import them.
        try:
            res = pinboard_client.posts_add(
                url=url,
                title=title,
                description="",
                tags="",
                toread=True,
                shared=True,
                replace=False,
            )
            result_code = res.get("result_code") or ""
        except Exception:  # noqa: BLE001
            logger.exception("feedbin-ingest: posts_add failed for %s", url)
            errors += 1
            continue
        db.record_feedbin_seen(
            guid=guid, url=url, title=title, pinboard_result=result_code,
        )
        if result_code == "done":
            new_count += 1
        else:
            # "item already exists" / anything else still counts as filed
            # locally (we've recorded the GUID), but it's not a fresh add.
            skipped += 1
    return {"new": new_count, "skipped": skipped, "errors": errors}


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    """Poll Feedbin starred, mirror to Pinboard, dedup via DB."""
    if not feedbin.feed_url():
        msg = "feedbin-ingest: FEEDBIN_STARRED_FEED_URL not set — skipping"
        logger.info(msg)
        return _base.JobResult(False, msg)

    if not (os.environ.get("PINBOARD_API_TOKEN") or "").strip():
        msg = "feedbin-ingest: PINBOARD_API_TOKEN not set — skipping"
        logger.info(msg)
        return _base.JobResult(False, msg)

    try:
        items = await asyncio.to_thread(feedbin.fetch_starred)
    except feedbin.FeedbinError as exc:
        logger.warning("feedbin-ingest: feed fetch failed: %s", exc)
        return _base.JobResult(False, f"feedbin fetch failed: {exc}")

    counts = await asyncio.to_thread(_ingest_items, items)

    if counts["new"] == 0 and counts["errors"] == 0:
        # PASS silently (typical case — Jamie hasn't starred anything new
        # since the last poll).
        return _base.JobResult(
            True,
            f"feedbin-ingest: no new starred items ({counts['skipped']} already filed)",
            data=counts,
        )

    # Loud-only when something actually changed or errored. Single line —
    # the running tally and next-step explanation are noise; the relevant
    # signal is "this scan filed N bookmarks."
    summary = f"📥 Feedbin ingest: **{counts['new']}** new toread bookmark(s)"
    if counts["errors"]:
        summary += f" · ⚠️ {counts['errors']} failed (see logs)"
    # Status, not actionable: the bookmarks are already in Pinboard; they
    # surface as #research toread cards on the next pinboard-scan, which
    # is where Jamie acts on them. The ingest summary is "I just did X" —
    # belongs in #chatter, not #research.
    await ctx.post("DISCORD_CHANNEL_CHATTER", summary, persona="linky")
    return _base.JobResult(True, summary, data=counts)
