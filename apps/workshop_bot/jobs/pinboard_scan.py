"""``pinboard-scan`` — hourly per-link research for Linky.

Four sources, one rhythm. Every hour 07:00–22:00 Central, year-round:

- **Toread** — Jamie's public toread bookmarks Linky hasn't researched yet
  (`shared=yes`, not in ``pinboard_research_done``). These are Jamie's own
  picks; Linky always writes a card.
- **Popular** — Pinboard's site-wide popular feed, minus avoid-domains and
  minus anything in ``pinboard_popular_seen``. Linky decides per-item
  whether it's "interesting to Jamie" — not "fits the Weekly Thing." A
  rejection still marks the URL seen; a fetch failure does not.
- **Lobsters** — Lobste.rs hottest feed (`https://lobste.rs/hottest.json`),
  with the same avoid-domains + ``pinboard_popular_seen`` filters as
  Pinboard popular. Same "interesting to Jamie" bar, same SKIP /
  FETCH_FAILED semantics.
- **Hacker News** — HN's current front page, fetched via Algolia's
  search index (`tags=front_page`). Same filter chain and SKIP /
  FETCH_FAILED semantics as the other two discovery feeds. Ask HN /
  Show HN posts without an external URL are dropped upstream in
  ``tools.hackernews``.

The dedup table ``pinboard_popular_seen`` is shared across all three
discovery feeds — URLs Jamie has been shown from any popular surface
stay out of the queue, even if multiple feeds trend the same URL on
the same day.

For each candidate, Linky's ``research-card`` prompt runs once: fetch the
URL, archive recall, read-length, then either a Discord card or one of
two signals — ``SKIP: <reason>`` (discovery sources only — not
interesting) or ``FETCH_FAILED: <reason>`` (any source — couldn't
actually read it, retry next scan). Each card posts as its own
``#research`` message; the message id is recorded in
``linky_research_messages`` so a reply / save-reaction lands on the
right Pinboard bookmark.

The job is unconditional — no window gate, no weekday gate. Most off-hour
scans will have an empty candidate list and PASS silently.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from ..systems.pinboard import client as pinboard
from ..tools import alt_text  # noqa: F401 — keep imports light; reserve for future
from ..tools import anthropic_client, avoid_domains, context, db, hackernews, lobsters
from . import _base

logger = logging.getLogger("workshop.jobs.pinboard_scan")

NAME = "pinboard-scan"

# Soft caps per scan so a runaway popular hour or a backlog catch-up doesn't
# flood ``#research``. Adjust via env if needed; defaults err on the side
# of "let it through."
_POPULAR_PER_SCAN_CAP = 10        # max Pinboard-popular cards posted per scan
_TOREAD_PER_SCAN_CAP = 10         # max toread cards posted per scan
_LOBSTERS_PER_SCAN_CAP = 10       # max Lobste.rs cards posted per scan
_HACKERNEWS_PER_SCAN_CAP = 10     # max Hacker News cards posted per scan
_POPULAR_FEED_LIMIT = 30          # how many popular items to consider per scan
_TOREAD_FEED_LIMIT = 25           # how many unresearched toread items to consider
_LOBSTERS_FEED_LIMIT = 25         # how many lobsters items to consider per scan
_HACKERNEWS_FEED_LIMIT = 25       # how many HN front-page items to consider per scan

_SKIP_RE = re.compile(r"^\s*SKIP:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)
_FAIL_RE = re.compile(r"^\s*FETCH_FAILED:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


# ---------- per-link LLM call ----------


# Display labels for the discussion-feed sources — same data shape
# (discussion URL + score + comments + submitter), different community
# names in the prompt so the LLM knows which thread it's looking at.
_DISCUSSION_LABEL: dict[str, str] = {
    "lobsters": "Lobsters",
    "hackernews": "Hacker News",
}


def _format_user_msg(*, source: str, item: dict[str, Any]) -> str:
    """Render the per-link prompt's `## The link` block from one candidate.
    Source-specific fields are included only when relevant — the
    discussion-feed sources (`lobsters`, `hackernews`) carry a
    discussion URL plus score / comments / submitter, the `toread` row
    carries the Pinboard URL + Jamie's existing description, the
    `popular` row carries neither."""
    url = (item.get("url") or "").strip()
    title = (item.get("title") or "").strip()
    lines = [
        "## The link",
        "",
        f"- **Source:** `{source}`",
        f"- **URL:** `{url}`",
        f"- **Title:** {title or '(no title)'}",
    ]
    if source == "toread":
        pin = (item.get("pinboard_url") or "").strip()
        desc = (item.get("description") or "").strip()
        lines.append(f"- **Pinboard URL:** {pin or '(missing)'}")
        lines.append(f"- **Existing description:** {desc or '(none)'}")
    elif source in _DISCUSSION_LABEL:
        label = _DISCUSSION_LABEL[source]
        disc = (item.get("discussion_url") or "").strip()
        tags = ", ".join(item.get("tags") or [])
        score = item.get("score")
        comments = item.get("comment_count")
        submitter = (item.get("submitter") or "").strip()
        lines.append(f"- **{label} discussion:** {disc}")
        if tags:
            lines.append(f"- **{label} tags:** {tags}")
        if score is not None and comments is not None:
            lines.append(f"- **{label} signal:** {score} points · {comments} comments")
        if submitter:
            lines.append(f"- **Submitter:** {submitter}")
    # `popular` carries no extras — just URL + title.
    lines.append("")
    return "\n".join(lines)


def _parse_signal(answer: str) -> tuple[str, str]:
    """Classify Linky's per-link response. Returns ``(kind, payload)`` where
    ``kind`` ∈ ``{'skip', 'fail', 'card'}`` and ``payload`` is the reason
    (for skip/fail) or the card text. Empty / PASS responses are treated
    as ``fail`` so we don't mark the URL seen prematurely."""
    text = (answer or "").strip()
    if not text:
        return "fail", "empty response"
    # Two failure signals: SKIP: ... or FETCH_FAILED: ...; both must be the
    # entire first line (case-insensitive). Anything else is the card.
    first_line = text.splitlines()[0]
    m = _FAIL_RE.match(first_line)
    if m:
        return "fail", m.group(1)
    m = _SKIP_RE.match(first_line)
    if m:
        return "skip", m.group(1)
    return "card", text


# ---------- candidate gathering (blocking; off the event loop) ----------


def _filter_discovery(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Common filter chain for any discovery feed: drop items without a
    URL, drop avoid-domain hosts, dedup against ``pinboard_popular_seen``."""
    pre = [
        it for it in raw
        if it.get("url") and not avoid_domains.is_excluded_url(it["url"])
    ]
    return db.filter_unseen_popular(pre)


def _gather_candidates() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]],
    list[dict[str, Any]], list[dict[str, Any]],
]:
    """Pull all four source lists in one blocking pass. Each source
    degrades to an empty list on its own failure — one flakey upstream
    shouldn't block the others.

    Returns ``(popular, toread, lobsters, hackernews)``. The three
    discovery feeds (popular + lobsters + hackernews) share the
    avoid-domains + ``pinboard_popular_seen`` filter chain; the toread
    side has its own via :func:`pinboard.toread_public_unresearched`."""
    try:
        popular = _filter_discovery(pinboard.popular(limit=_POPULAR_FEED_LIMIT))
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: popular feed pull failed: %s", exc)
        popular = []
    try:
        toread = pinboard.toread_public_unresearched(limit=_TOREAD_FEED_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: toread pull failed: %s", exc)
        toread = []
    try:
        lobs = _filter_discovery(lobsters.hottest(limit=_LOBSTERS_FEED_LIMIT))
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: lobsters feed pull failed: %s", exc)
        lobs = []
    try:
        hn = _filter_discovery(hackernews.top(limit=_HACKERNEWS_FEED_LIMIT))
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: hackernews feed pull failed: %s", exc)
        hn = []
    return popular, toread, lobs, hn


# ---------- per-link runtime ----------


async def _research_one(
    *, linky, prompt: str, linky_ctx_block: str, source: str, item: dict[str, Any],
) -> tuple[str, str]:
    """Run one per-link LLM call. Returns ``(kind, payload)`` per
    :func:`_parse_signal`."""
    url = item.get("url") or ""
    item_block = _format_user_msg(source=source, item=item)
    user_msg = f"{linky_ctx_block}\n\n{prompt}\n\n{item_block}"
    try:
        answer, _meta = await linky.core(latest=user_msg, history=[], model="sonnet")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: per-link LLM call failed for %s: %s", url, exc)
        return "fail", f"LLM error: {type(exc).__name__}"
    return _parse_signal(answer)


async def _process_one(
    *, ctx: "_base.JobContext", linky, prompt: str, linky_ctx_block: str,
    source: str, item: dict[str, Any], counters: dict[str, int],
) -> None:
    """Research one candidate end-to-end: LLM call, response classify, post
    if it's a card, record the message + mark seen/researched. Idempotent
    per scan — exceptions are caught and logged, never re-raised."""
    url = (item.get("url") or "").strip()
    if not url:
        return
    title = item.get("title") or ""
    kind, payload = await _research_one(
        linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
        source=source, item=item,
    )
    if kind == "fail":
        # Don't mark seen — retry next scan.
        counters["fail"] += 1
        logger.info("pinboard-scan: %s [%s] -> FETCH_FAILED: %s", source, url, payload[:100])
        return
    if kind == "skip":
        # Discovery feeds share the same `pinboard_popular_seen` dedup.
        if source in ("popular", "lobsters", "hackernews"):
            db.mark_popular_seen(
                [{"url": url, "title": title}],
                judged={url: (False, payload)},
            )
        elif source == "toread":
            # Toread items shouldn't skip; treat as a researched-no-card,
            # mark researched so we don't keep re-asking.
            db.mark_url_researched(
                url=url, title=title, summary=f"SKIP: {payload}",
                confidence="⊘", fit_note=payload[:200],
            )
        counters["skip"] += 1
        logger.info("pinboard-scan: %s [%s] -> SKIP: %s", source, url, payload[:100])
        return
    # kind == "card"
    msg = await ctx.send_one(
        "DISCORD_CHANNEL_RESEARCH", payload, persona="linky",
    )
    if msg is None:
        # Channel not resolvable; don't mark anything — try again next scan.
        counters["fail"] += 1
        logger.warning("pinboard-scan: send_one returned None for %s [%s]", source, url)
        return
    try:
        db.record_research_message(
            discord_message_id=str(msg.id), url=url, source=source, title=title,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: record_research_message failed for %s: %s", url, exc)
    if source in ("popular", "lobsters", "hackernews"):
        db.mark_popular_seen(
            [{"url": url, "title": title}],
            judged={url: (True, "card posted")},
        )
    else:
        db.mark_url_researched(
            url=url, title=title, summary=payload[:500],
            confidence="✦", fit_note="card posted",
        )
    counters["posted"] += 1
    logger.info("pinboard-scan: %s [%s] -> posted card msg=%s", source, url, msg.id)


# ---------- the job ----------


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return _base.JobResult(True, "(no Discord — pinboard-scan skipped)", data={"posted": 0})
    linky = team.bots.get("linky")
    if linky is None or getattr(linky, "user", None) is None:
        return _base.JobResult(True, "(Linky unavailable — pinboard-scan skipped)", data={"posted": 0})

    # Load the per-link prompt + the dynamic context once per scan; both
    # apply identically to every candidate this scan considers.
    try:
        prompt = anthropic_client.load_prompt("linky-research-card")
    except OSError as exc:
        logger.warning("pinboard-scan: research-card prompt missing: %s", exc)
        return _base.JobResult(False, f"research-card prompt missing: {exc}", data={"posted": 0})

    from datetime import datetime
    today = datetime.now().date()
    linky_ctx = await asyncio.to_thread(context.build_linky_context, ref_date=today)
    linky_ctx_block = context.render_block(linky_ctx)

    # Gather all four source lists (blocking — off the event loop).
    popular, toread, lobs, hn = await asyncio.to_thread(_gather_candidates)
    if not popular and not toread and not lobs and not hn:
        return _base.JobResult(
            True, "Linky: nothing new in any source — PASS.", data={"posted": 0},
        )

    counters = {"posted": 0, "skip": 0, "fail": 0}

    with db.AgentRun("linky", trigger="pinboard-scan") as run_:
        # Toread first — Jamie's own picks before random discovery finds.
        for item in toread[:_TOREAD_PER_SCAN_CAP]:
            await _process_one(
                ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                source="toread", item=item, counters=counters,
            )
        for item in popular[:_POPULAR_PER_SCAN_CAP]:
            await _process_one(
                ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                source="popular", item=item, counters=counters,
            )
        for item in lobs[:_LOBSTERS_PER_SCAN_CAP]:
            await _process_one(
                ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                source="lobsters", item=item, counters=counters,
            )
        for item in hn[:_HACKERNEWS_PER_SCAN_CAP]:
            await _process_one(
                ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                source="hackernews", item=item, counters=counters,
            )
        run_.records_written = counters["posted"]

    considered = (
        f"{len(popular)} popular + {len(toread)} toread + "
        f"{len(lobs)} lobsters + {len(hn)} hackernews"
    )
    if counters["posted"] == 0:
        return _base.JobResult(
            True,
            f"Linky: considered {considered}; "
            f"no cards posted ({counters['skip']} skip, {counters['fail']} retry).",
            data={"posted": 0, **counters},
        )
    return _base.JobResult(
        True,
        f"Linky: posted {counters['posted']} card(s) "
        f"({counters['skip']} skip, {counters['fail']} retry).",
        data={"posted": counters["posted"], **counters},
    )
