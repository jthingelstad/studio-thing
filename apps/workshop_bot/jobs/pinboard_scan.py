"""``pinboard-scan`` — hourly per-link research for Linky.

Two sources, one rhythm. Every hour 07:00–22:00 Central, year-round:

- **Toread** — Jamie's public toread bookmarks Linky hasn't researched yet
  (`shared=yes`, not in ``pinboard_research_done``). These are Jamie's own
  picks; Linky always writes a card.
- **Popular** — Pinboard's site-wide popular feed, minus avoid-domains and
  minus anything in ``pinboard_popular_seen``. Linky decides per-item
  whether it's "interesting to Jamie" — not "fits the Weekly Thing." A
  rejection still marks the URL seen; a fetch failure does not.

For each candidate, Linky's ``research-card`` prompt runs once: fetch the
URL, archive recall, read-length, then either a Discord card or one of
two signals — ``SKIP: <reason>`` (popular only — not interesting) or
``FETCH_FAILED: <reason>`` (either source — couldn't actually read it,
retry next scan). Each card posts as its own ``#research`` message; the
message id is recorded in ``linky_research_messages`` so a reply lands
on the right Pinboard bookmark.

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
from ..tools import anthropic_client, avoid_domains, context, db
from . import _base

logger = logging.getLogger("workshop.jobs.pinboard_scan")

NAME = "pinboard-scan"

# Soft caps per scan so a runaway popular hour or a backlog catch-up doesn't
# flood ``#research``. Adjust via env if needed; defaults err on the side
# of "let it through."
_POPULAR_PER_SCAN_CAP = 10        # max popular cards posted per scan
_TOREAD_PER_SCAN_CAP = 10         # max toread cards posted per scan
_POPULAR_FEED_LIMIT = 30          # how many popular items to consider per scan
_TOREAD_FEED_LIMIT = 25           # how many unresearched toread items to consider

_SKIP_RE = re.compile(r"^\s*SKIP:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)
_FAIL_RE = re.compile(r"^\s*FETCH_FAILED:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


# ---------- per-link LLM call ----------


def _format_user_msg(
    *, source: str, url: str, title: str, pinboard_url: str, description: str,
) -> str:
    return (
        f"## The link\n\n"
        f"- **Source:** `{source}`\n"
        f"- **URL:** `{url}`\n"
        f"- **Title:** {title or '(no title)'}\n"
        f"- **Pinboard URL:** {pinboard_url or '(not bookmarked yet)'}\n"
        f"- **Existing description:** {description or '(none)'}\n"
    )


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


def _gather_candidates() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pull both source lists in one blocking pass. Each side degrades to
    an empty list on its own failure — one source flakey shouldn't kill
    the other."""
    try:
        raw_popular = pinboard.popular(limit=_POPULAR_FEED_LIMIT)
        popular = [
            it for it in raw_popular
            if it.get("url") and not avoid_domains.is_excluded_url(it["url"])
        ]
        popular = db.filter_unseen_popular(popular)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: popular feed pull failed: %s", exc)
        popular = []
    try:
        toread = pinboard.toread_public_unresearched(limit=_TOREAD_FEED_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: toread pull failed: %s", exc)
        toread = []
    return popular, toread


# ---------- per-link runtime ----------


async def _research_one(
    *, linky, prompt: str, linky_ctx_block: str, source: str, item: dict[str, Any],
) -> tuple[str, str]:
    """Run one per-link LLM call. Returns ``(kind, payload)`` per
    :func:`_parse_signal`."""
    url = item.get("url") or ""
    title = item.get("title") or ""
    pin_url = item.get("pinboard_url") or ""
    description = item.get("description") or ""
    item_block = _format_user_msg(
        source=source, url=url, title=title,
        pinboard_url=pin_url, description=description,
    )
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
        # Popular-only signal — but be defensive if it shows up on toread too.
        if source == "popular":
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
            discord_message_id=str(msg.id), url=url, source=source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: record_research_message failed for %s: %s", url, exc)
    if source == "popular":
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

    # Gather both source lists (blocking — off the event loop).
    popular, toread = await asyncio.to_thread(_gather_candidates)
    if not popular and not toread:
        return _base.JobResult(
            True, "Linky: nothing new in either source — PASS.", data={"posted": 0},
        )

    counters = {"posted": 0, "skip": 0, "fail": 0}

    with db.AgentRun("linky", trigger="pinboard-scan") as run_:
        # Toread first — Jamie's own picks before random popular finds.
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
        run_.records_written = counters["posted"]

    if counters["posted"] == 0:
        return _base.JobResult(
            True,
            f"Linky: considered {len(popular)} popular + {len(toread)} toread; "
            f"no cards posted ({counters['skip']} skip, {counters['fail']} retry).",
            data={"posted": 0, **counters},
        )
    return _base.JobResult(
        True,
        f"Linky: posted {counters['posted']} card(s) "
        f"({counters['skip']} skip, {counters['fail']} retry).",
        data={"posted": counters["posted"], **counters},
    )
