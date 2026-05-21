"""Source-to-rows sync — pull Pinboard + micro.blog into ``issue_items``.

``update-draft`` calls this first thing: it refreshes the row state for
the in-flight issue from upstream sources, then renders ``draft.md``
from those rows + the file-backed atoms (intro / outro / cover /
currently / haiku).

Pinboard items partition by tag: ``_brief`` → ``brief``; everything else
→ ``notable``. Source id is the Pinboard bookmark hash (stable per URL).

micro.blog posts always land in ``journal``. Source id is the post URL.

Pruning: items that disappear upstream (Pinboard bookmark deleted or
its window no longer matches; micro.blog post deleted) are removed from
``issue_items`` so the rendered draft doesn't carry stale entries.
Promoted items are NOT pruned — Eddy's editorial promotion is a
deliberate decision that survives upstream churn; if the underlying
post was deleted, the promoted row remains and Eddy's next review can
flag it.

journal images are rehosted by ``tools.content.journal_images`` (called
once per post during sync) before the body is written to ``body_md``.
The rehost manifest (image URLs we rewrote, with their alt text) is
captured in ``metadata_json`` so the renderer can emit ``<img>`` tags
byte-identically across re-syncs.
"""

from __future__ import annotations

import logging
from typing import Any

from ..systems.pinboard import client as pinboard
from . import issue_items
from .content import journal_images, microblog
from .db.connection import connect

logger = logging.getLogger("workshop.issue_items_sync")

# Pinboard "_brief" tag → brief section. Mirrors ``pinboard.BRIEF_TAG``.
_BRIEF_TAG = "_brief"


def _journal_label(published_iso: Any) -> str:
    """Render a journal entry's timestamp as ``Sunday @ 4:16 PM``.

    Same shape ``update-draft._render_journal`` uses today. Day-of-week +
    12-hour clock, no date — every entry in an issue is within a seven-
    day window so the weekday already identifies it.
    """
    dt = microblog.published_local(published_iso)
    if dt is None:
        return str(published_iso or "").strip()
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A')} @ {hour12}:{dt.minute:02d} {ampm}"


# ---------- Pinboard ----------

def _pinboard_source_id(post: dict[str, Any]) -> str:
    """Pinboard hash is the stable identity. URL is the fallback when the
    hash is empty (rare — Pinboard always returns it for posts/all)."""
    return str(post.get("hash") or post.get("url") or "").strip()


def _pinboard_metadata(post: dict[str, Any], section: str) -> dict[str, Any]:
    """Capture the upstream extras that don't fit the columns. Sorting
    keys when serializing so identical inputs produce identical bytes
    (helps the diff harness).
    """
    return {
        "tags": post.get("tags") or "",
        "added": post.get("added") or "",
        "added_date": post.get("added_date") or "",
        "pinboard_url": post.get("pinboard_url") or "",
        "is_brief_tagged": section == "brief",
    }


def sync_pinboard(
    issue_number: int, window: dict[str, Any], *, prune: bool = True,
) -> dict[str, int]:
    """Pull Pinboard's issue-window candidates into ``issue_items``.

    Items present upstream get UPSERTed (existing row identity preserved
    via ``hash``; section/title/body/metadata refreshed). When
    ``prune=True`` (default), non-promoted Pinboard rows whose hash
    isn't in this sync's observed set are deleted — that handles
    Pinboard bookmarks Jamie removed mid-cycle.

    Returns ``{'observed': N, 'pruned': N}``. Inserts vs updates aren't
    distinguished (upsert hides the difference); the count of observed
    items is the operationally useful number.
    """
    n = int(issue_number)
    cand = pinboard.issue_window_candidates(window["start_date"], window["end_date"])
    observed_ids: set[str] = set()
    for section in ("notable", "brief"):
        for post in cand.get(section, []):
            sid = _pinboard_source_id(post)
            if not sid:
                continue  # defensive — skip anything Pinboard returned without identity
            observed_ids.add(sid)
            issue_items.upsert_item(
                issue_number=n,
                section=section,
                source="pinboard",
                source_id=sid,
                url=(post.get("url") or "").strip() or None,
                title=(post.get("title") or "").strip() or None,
                body_md=(post.get("description") or "").strip() or None,
                metadata=_pinboard_metadata(post, section),
            )
    pruned = _prune_stale(n, source="pinboard", observed=observed_ids) if prune else 0
    logger.info(
        "sync_pinboard: WT%d observed=%d pruned=%d",
        n, len(observed_ids), pruned,
    )
    return {"observed": len(observed_ids), "pruned": pruned}


# ---------- micro.blog ----------

def _microblog_source_id(post: dict[str, Any]) -> str:
    """micro.blog post URL is the stable identity (each post has a
    permanent ``/YYYY/MM/DD/slug.html``-style URL)."""
    return str(post.get("url") or "").strip()


def _microblog_metadata(post: dict[str, Any]) -> dict[str, Any]:
    """Capture published timestamp + weekday-time label + category tags.
    The label is computed once here and stored verbatim so re-renders
    produce identical bytes even if the renderer's clock interpretation
    drifts. Categories drive the Featured-section promotion at
    sync time (``Featured`` lifts the post into a standalone H2 above
    Notable). Rehosted ``<img>`` tags are already baked into ``body_md``.
    """
    categories = post.get("categories")
    if not isinstance(categories, list):
        categories = []
    return {
        "published": post.get("published") or "",
        "label": _journal_label(post.get("published")),
        "categories": list(categories),
    }


FEATURED_CATEGORY = "Featured"
FEATURED_POSITION = "before_notable"


def _is_featured(post: dict[str, Any]) -> bool:
    cats = post.get("categories")
    if not isinstance(cats, list):
        return False
    return FEATURED_CATEGORY in {str(c).strip() for c in cats if isinstance(c, str)}


def _featured_heading(post: dict[str, Any]) -> str:
    """The H2 heading text for the standalone Featured section.

    Uses the micro.blog post title if present; otherwise falls back to
    the linked first line of the body so the section never renders with
    an empty heading. micro.blog's titled posts always carry a name,
    so the fallback is defensive."""
    title = (post.get("title") or "").strip()
    if title:
        return title
    body = (post.get("content_md") or "").strip()
    if body:
        first_line = body.splitlines()[0].strip()
        # Strip leading markdown headings / formatting markers for a clean H2.
        cleaned = first_line.lstrip("#").strip().strip("*_").strip()
        if cleaned:
            return cleaned[:120]
    return "Featured"


def sync_microblog(
    issue_number: int, window: dict[str, Any], *, prune: bool = True,
) -> dict[str, int]:
    """Pull micro.blog's in-window posts into ``issue_items`` (journal).

    Images embedded in each post are rehosted via
    :mod:`tools.content.journal_images` once per post (the same call
    ``update-draft`` made in the file-based world); the rehosted body
    is what ends up in ``body_md``.

    ``prune=True`` removes non-promoted micro.blog rows whose URL isn't
    in this sync's observed set (Jamie deleted the post upstream).
    """
    n = int(issue_number)
    posts = microblog.posts_in_window(window["start_date"], window["end_date"])
    observed_ids: set[str] = set()
    featured_count = 0
    for post in posts:
        sid = _microblog_source_id(post)
        if not sid:
            continue
        observed_ids.add(sid)
        try:
            rehosted = journal_images.rehost_in_markdown(post.get("content_md") or "", n)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sync_microblog: image rehost failed for %s: %s",
                sid, exc,
            )
            rehosted = post.get("content_md") or ""
        row_id = issue_items.upsert_item(
            issue_number=n,
            section="journal",
            source="microblog",
            source_id=sid,
            url=sid,
            title=(post.get("title") or "").strip() or None,
            body_md=rehosted.strip() or None,
            metadata=_microblog_metadata(post),
        )
        # Featured-category promotion: the post's ``Featured`` category
        # lifts it into a standalone ``## {title}`` section above Notable
        # (driven by Jamie's micro.blog tag, not Eddy). Idempotent across
        # re-syncs: tagging adds the promotion, un-tagging clears it.
        if _is_featured(post):
            issue_items.promote(
                row_id,
                promoted_position=FEATURED_POSITION,
                promoted_heading=_featured_heading(post),
            )
            featured_count += 1
        else:
            issue_items.unpromote(row_id)
    pruned = _prune_stale(n, source="microblog", observed=observed_ids) if prune else 0
    logger.info(
        "sync_microblog: WT%d observed=%d pruned=%d featured=%d",
        n, len(observed_ids), pruned, featured_count,
    )
    return {"observed": len(observed_ids), "pruned": pruned, "featured": featured_count}


# ---------- pruning ----------

def _prune_stale(
    issue_number: int, *, source: str, observed: set[str],
) -> int:
    """Delete non-promoted rows for ``(issue, source)`` whose
    ``source_id`` is not in ``observed``. Promoted items are preserved
    no matter what — they're an editorial decision and the next review
    should flag a missing upstream rather than the sync silently dropping
    it. Returns the number of rows deleted.

    ``editorial_comments.item_id`` is an FK to ``issue_items.id`` with no
    ON DELETE action, so a stale item that has a draft-review comment
    anchored to it would otherwise block the DELETE. We null out the
    item_id for those comments first — the comment row, its handle, body,
    section, and scope all survive, just unanchored from the now-gone
    upstream item.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, source_id FROM issue_items "
            "WHERE issue_number = ? AND source = ? AND is_promoted = 0",
            (int(issue_number), source),
        ).fetchall()
        stale_ids = [
            int(r["id"]) for r in rows if str(r["source_id"]) not in observed
        ]
        if not stale_ids:
            return 0
        # SQLite limits parameter count; chunk just in case (unlikely
        # to exceed ~50 stale per issue but defensive).
        deleted = 0
        for i in range(0, len(stale_ids), 200):
            chunk = stale_ids[i:i + 200]
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(
                f"UPDATE editorial_comments SET item_id = NULL "
                f"WHERE item_id IN ({placeholders})",
                chunk,
            )
            cur = conn.execute(
                f"DELETE FROM issue_items WHERE id IN ({placeholders})",
                chunk,
            )
            deleted += int(cur.rowcount or 0)
        return deleted


# ---------- combined entrypoint ----------

def sync_all(
    issue_number: int, window: dict[str, Any], *, prune: bool = True,
) -> dict[str, dict[str, int]]:
    """Run both syncs back-to-back. ``update-draft`` calls this once per
    refresh. Failures in one source don't block the other — each is
    wrapped, errors logged, and the row state from the previous sync
    survives the failure (no rows deleted on a failed sync).
    """
    out: dict[str, dict[str, int]] = {}
    try:
        out["pinboard"] = sync_pinboard(issue_number, window, prune=prune)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "sync_all: Pinboard sync failed for WT%d: %s",
            issue_number, exc,
        )
        out["pinboard"] = {"observed": 0, "pruned": 0, "error": str(exc)}  # type: ignore[dict-item]
    try:
        out["microblog"] = sync_microblog(issue_number, window, prune=prune)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "sync_all: micro.blog sync failed for WT%d: %s",
            issue_number, exc,
        )
        out["microblog"] = {"observed": 0, "pruned": 0, "error": str(exc)}  # type: ignore[dict-item]
    return out
