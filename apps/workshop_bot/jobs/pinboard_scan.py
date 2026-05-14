"""``pinboard-scan`` — hourly per-link research for Linky.

One toread lane plus N discovery feeds, one rhythm. Every hour 07:00–
22:00 Central, year-round:

- **Toread** — Jamie's public toread bookmarks Linky hasn't researched
  yet (`shared=yes`, not in ``pinboard_research_done``). Jamie's own
  picks; Linky always writes a card.
- **Discovery feeds** — declared in :data:`DISCOVERY_FEEDS` (a tuple of
  :class:`FeedSpec`). Each feed runs through the same avoid-domains
  filter; a per-(url, source) sightings log
  (``popular_seen_sightings``) decides whether each item is **fresh**
  (never seen by anyone), **uplift** (URL was seen before from a
  *different* feed — re-evaluate with that history), or **dropped**
  (URL already sighted from *this* feed; today's silent-dedup).
  Linky decides per-item whether it's "interesting to Jamie" — not
  "fits the Weekly Thing." A rejection still marks the URL seen
  (popular dedup table); a fetch failure does not.

To add a feed: write a fetcher in ``tools/<name>.py``, add a line to
``DISCOVERY_FEEDS``, append the source name to ``db.RESEARCH_SOURCES``.
No other code changes are needed — the loops, the user-message
rendering, and the persona's ``_DISCOVERY_SOURCES`` derivation all read
the registry.

**Cross-source signal** lives in two parallel mechanisms, both
fed by the sightings log:

- **In-scan merge** — same URL on multiple feeds in this hour, none
  seen before: pick the highest-priority feed as primary, attach the
  others as ``co_sources``. One card, multiple discussion-thread
  links in the header, "Also trending on …" line in the LLM's user
  message.
- **Cross-day uplift** — same URL appears on a *new* feed days after
  it was first seen elsewhere: build an uplift candidate carrying
  the prior sightings + original verdict. Linky writes a fresh card
  with the cross-source uplift block as context, or SKIPs the
  re-evaluation. Throttled at ``_UPLIFT_PER_SCAN_CAP`` per scan.

For each candidate, Linky's ``research-card`` prompt runs once: fetch
the URL, archive recall, read-length, then either a Discord card or one
of two signals — ``SKIP: <reason>`` (discovery sources only — not
interesting) or ``FETCH_FAILED: <reason>`` (any source — couldn't
actually read it, retry next scan). Each card posts as its own
``#research`` message; the message id is recorded in
``linky_research_messages`` so a reply / save-reaction lands on the
right Pinboard bookmark.

The job is unconditional — no window gate, no weekday gate. Most off-
hour scans will have an empty candidate set and PASS silently.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from ..systems.pinboard import client as pinboard
from ..tools import alt_text  # noqa: F401 — keep imports light; reserve for future
from ..tools import avoid_domains, db
from ..tools.content import context
from ..tools.llm import anthropic_client
from ..tools.feeds.feed_registry import DISCOVERY_FEEDS, by_name
from ..tools.url_normalize import dedup_key
from . import _base

logger = logging.getLogger("workshop.jobs.pinboard_scan")

NAME = "pinboard-scan"

# Toread is its own lane (different fetcher signature, different dedup
# table, no SKIP path, different action lines). Keep its cap + feed
# limit at module scope, separate from the discovery registry.
_TOREAD_PER_SCAN_CAP = 10
_TOREAD_FEED_LIMIT = 25

# Cross-source uplift cap. A URL bouncing between feeds over days
# can generate one "re-evaluate this" card per new sighting; without a
# governor, a viral URL hitting three new feeds in a week could fire
# three uplift cards back-to-back. Five per scan is enough to surface
# the genuine signal without flooding `#research`. Sightings are
# *recorded* even when we cap — so we never lose the signal, the
# excess just falls into a future scan. Tunable via the
# ``WORKSHOP_UPLIFT_PER_SCAN_CAP`` env var; matches the pattern used by
# ``WORKSHOP_ALT_VISION_CAP`` and friends.
_UPLIFT_PER_SCAN_CAP_DEFAULT = 5


def _uplift_cap() -> int:
    import os
    raw = (os.environ.get("WORKSHOP_UPLIFT_PER_SCAN_CAP") or "").strip()
    if not raw:
        return _UPLIFT_PER_SCAN_CAP_DEFAULT
    try:
        v = int(raw)
        return v if v >= 0 else _UPLIFT_PER_SCAN_CAP_DEFAULT
    except ValueError:
        return _UPLIFT_PER_SCAN_CAP_DEFAULT

# DISCOVERY_FEEDS lives in tools/feed_registry.py — single source of
# truth that the persona (for `_discovery_sources`) and the schema-
# enum docs both reference. Imported above.

_SKIP_RE = re.compile(r"^\s*SKIP:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)
_FAIL_RE = re.compile(r"^\s*FETCH_FAILED:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


# ---------- per-link user-message rendering ----------


# Per-card resonance snippet length and how many archive hits to fetch.
# Each hit's chunk text is hard-capped at 180 chars in the rendered
# block (the corpus's underlying text is up to 1500 chars; this is just
# a tighter cap for prompt-priming purposes).
_ARCHIVE_RESONANCE_K = 3
_ARCHIVE_SNIPPET_CHARS = 180
_ARCHIVE_QUERY_CHARS = 150


def _archive_query(*, source: str, item: dict[str, Any]) -> str:
    """Build the BM25 query for the archive lookup. For toread items
    Jamie's description (when present) often retrieves better than the
    bare title — combine them. For discovery items, descriptions are
    usually slug-noise, so title only."""
    title = (item.get("title") or "").strip()
    if source == "toread":
        desc = (item.get("description") or "").strip()
        query = f"{title} {desc}".strip()
    else:
        query = title
    return query[:_ARCHIVE_QUERY_CHARS]


def _truncate_snippet(text: str) -> str:
    """Trim a chunk's text to the resonance-snippet limit. Single line."""
    s = " ".join((text or "").split())
    if len(s) <= _ARCHIVE_SNIPPET_CHARS:
        return s
    cut = s[:_ARCHIVE_SNIPPET_CHARS].rsplit(" ", 1)[0]
    return f"{cut}…"


def _render_archive_resonance(*, corpus, source: str, item: dict[str, Any]) -> list[str]:
    """Synchronous BM25 lookup against the archive corpus, formatted as
    a ``## Archive resonance`` block of bullet entries. Empty list if
    the corpus handle is missing (test stubs); a single
    ``(no resonance — fresh territory)`` bullet if the search returned
    nothing positive."""
    if corpus is None:
        return []
    query = _archive_query(source=source, item=item)
    if not query:
        return []
    try:
        hits = corpus.search(query, k=_ARCHIVE_RESONANCE_K)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: archive resonance lookup failed: %s", exc)
        return []
    lines = ["", "## Archive resonance", ""]
    if not hits:
        lines.append("_(no resonance — fresh territory)_")
        return lines
    for hit in hits:
        issue = hit.get("issue_number") or hit.get("issue") or "?"
        date = (hit.get("publish_date") or hit.get("date") or "")[:10]
        section = hit.get("section") or "Issue"
        subject = (hit.get("subject") or "").strip()
        lines.append(f"- #{issue} ({date}) · {section} — \"{subject}\"")
        snippet = _truncate_snippet(hit.get("text", ""))
        if snippet:
            lines.append(f"  > {snippet}")
    return lines


def _label_for(source: str) -> str:
    spec = by_name(DISCOVERY_FEEDS, source)
    return spec.label if spec is not None else source


def _pin_label_for(source: str) -> str:
    spec = by_name(DISCOVERY_FEEDS, source)
    return spec.pin_label if spec is not None else ""


def _signal_line_for(item: dict[str, Any], label: str) -> Optional[str]:
    """Render the per-feed ``{label} signal:`` line if there's a non-zero
    score worth surfacing. Discovery feeds with no vote system (Tildes,
    IndieWeb News) leave score/comments at 0 — return None in that case."""
    score = item.get("score")
    comments = item.get("comment_count")
    if not score:
        return None
    if comments:
        return f"- **{label} signal:** {score} points · {comments} comments"
    return f"- **{label} signal:** {score} points"


def _render_uplift_block(item: dict[str, Any]) -> list[str]:
    """The cross-day uplift context: prior sightings, original verdict,
    and the new sightings discovered this scan. Empty list if the item
    isn't an uplift candidate."""
    if not item.get("_is_uplift"):
        return []
    lines = ["", "## Cross-source uplift", ""]
    history = item.get("uplift_history") or []
    new_sightings = item.get("new_sightings") or []
    if history:
        lines.append("This URL has been seen before:")
        for h in history:
            seen_at = (h.get("seen_at") or "")[:10]
            src_label = _label_for(h.get("source") or "")
            lines.append(f"- {seen_at} ({src_label})")
    for sighting in new_sightings:
        src_label = _label_for(sighting["source"])
        lines.append(f"- TODAY ({src_label}) ← new sighting, this scan")
    verdict = item.get("uplift_verdict") or {}
    # `verdict_source` is the feed that produced the recorded verdict.
    # Legacy rows (written before the column existed) leave it NULL —
    # fall back to the oldest sighting in history as a best-effort
    # label so older URLs render reasonably.
    verdict_source = verdict.get("verdict_source") or (
        history[0].get("source") if history else ""
    )
    if verdict.get("judged_interesting") == 1:
        lines.append("")
        lines.append("**Previous verdict:** card posted on first sighting; "
                     "Jamie may not have bookmarked it the first time.")
    elif verdict.get("judged_interesting") == 0:
        note = (verdict.get("judgment_note") or "").strip() or "(no reason recorded)"
        lines.append("")
        lines.append(f"**Previous verdict:** SKIP'd from "
                     f"{_label_for(verdict_source or '')}: \"{note}\"")
    else:
        lines.append("")
        lines.append("**Previous verdict:** sighting recorded with no verdict yet.")
    return lines


def _render_link_block(*, source: str, item: dict[str, Any]) -> list[str]:
    """The base ``## The link`` block with source / URL / title plus the
    source-specific fields (Pinboard URL + existing description for
    ``toread``; discussion URL / pin-label / tags / signal / submitter
    for discovery sources). One responsibility; no archive resonance,
    no cross-source extras, no uplift history."""
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
        return lines
    label = _label_for(source)
    pin_label = _pin_label_for(source)
    disc = (item.get("discussion_url") or "").strip()
    if disc:
        lines.append(f"- **{label} discussion:** {disc}")
        if pin_label:
            lines.append(f"- **{label} pin label:** {pin_label}")
    tags = ", ".join(item.get("tags") or [])
    if tags:
        lines.append(f"- **{label} tags:** {tags}")
    sig = _signal_line_for(item, label)
    if sig:
        lines.append(sig)
    submitter = (item.get("submitter") or "").strip()
    if submitter:
        lines.append(f"- **Submitter:** {submitter}")
    return lines


def _render_co_sources(item: dict[str, Any]) -> list[str]:
    """In-scan cross-source rows: ``Also trending on …`` summary plus
    per-co-source discussion URL / pin-label / signal lines. Empty list
    when there are no co-sources (single-feed item)."""
    co_sources = item.get("co_sources") or []
    if not co_sources:
        return []
    lines = [
        "- **Also trending on (this scan):** "
        + ", ".join(_label_for(c["source"]) for c in co_sources),
    ]
    for co in co_sources:
        co_label = _label_for(co["source"])
        co_pin = _pin_label_for(co["source"])
        co_disc = (co.get("discussion_url") or "").strip()
        if co_disc:
            lines.append(f"- **{co_label} discussion:** {co_disc}")
            if co_pin:
                lines.append(f"- **{co_label} pin label:** {co_pin}")
        co_sig = _signal_line_for(co, co_label)
        if co_sig:
            lines.append(co_sig)
    return lines


def _format_user_msg(*, source: str, item: dict[str, Any], corpus=None) -> str:
    """The per-link prompt's full input block. Composes four sub-blocks:

    - :func:`_render_link_block` — base ``## The link`` fields
    - :func:`_render_co_sources` — in-scan cross-source extras
    - :func:`_render_archive_resonance` — BM25 hits against the archive
    - :func:`_render_uplift_block` — cross-day uplift history

    Each piece is independently testable; this composer just stitches
    them with a blank-line terminator between the link block and
    everything that follows."""
    parts = (
        _render_link_block(source=source, item=item)
        + _render_co_sources(item)
        + [""]
        + _render_archive_resonance(corpus=corpus, source=source, item=item)
        + _render_uplift_block(item)
    )
    return "\n".join(parts)


def _parse_signal(answer: str) -> tuple[str, str]:
    """Classify Linky's per-link response. Returns ``(kind, payload)``
    where ``kind`` ∈ ``{'skip', 'fail', 'card'}`` and ``payload`` is the
    reason (for skip/fail) or the card text. Empty / PASS responses are
    treated as ``fail`` so we don't mark the URL seen prematurely."""
    text = (answer or "").strip()
    if not text:
        return "fail", "empty response"
    first_line = text.splitlines()[0]
    m = _FAIL_RE.match(first_line)
    if m:
        return "fail", m.group(1)
    m = _SKIP_RE.match(first_line)
    if m:
        return "skip", m.group(1)
    return "card", text


# ---------- candidate gathering (blocking; off the event loop) ----------


def _signal_blob(item: dict[str, Any], source: str) -> dict[str, Any]:
    """Per-source signal carried in ``co_sources`` / ``new_sightings``.
    Just the bits the prompt needs to render multiple discussion links
    and the "Also trending on" line."""
    return {
        "source": source,
        "discussion_url": (item.get("discussion_url") or "").strip(),
        "score": item.get("score") or 0,
        "comment_count": item.get("comment_count") or 0,
    }


def _gather_candidates() -> tuple[
    list[dict[str, Any]],   # toread items
    list[dict[str, Any]],   # fresh discovery items (priority-ordered, co_sources merged)
    list[dict[str, Any]],   # uplift discovery items (already capped)
    dict[str, int],         # raw counts per source (for the "considered" log line)
]:
    """Pull every discovery feed + the toread lane in one blocking pass,
    then classify each discovery item into fresh / uplift / drop:

    - **fresh** — URL not in ``pinboard_popular_seen``. In-scan duplicates
      across feeds collapse into the higher-priority feed's primary
      with the lower-priority feeds' signal blobs in ``co_sources``.
    - **uplift** — URL is in ``pinboard_popular_seen`` but this feed has
      never sighted it. Carry the prior sightings + verdict + the new
      sightings discovered this scan.
    - **drop** — URL already sighted from this feed before. Today's
      silent-dedup behavior; not returned.

    Sightings are NOT recorded here — that's deferred to the per-link
    runtime so a fetch failure can leave the URL unmarked and retried
    next scan. This function is pure classification."""
    try:
        toread = pinboard.toread_public_unresearched(limit=_TOREAD_FEED_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: toread pull failed: %s", exc)
        toread = []

    raw_counts: dict[str, int] = {}
    # Two scan-level maps keyed by dedup_key:
    fresh_by_key: dict[str, dict[str, Any]] = {}
    uplift_by_key: dict[str, dict[str, Any]] = {}

    for spec in DISCOVERY_FEEDS:
        try:
            raw = spec.fetch(spec.feed_limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pinboard-scan: %s feed pull failed: %s", spec.name, exc)
            raw_counts[spec.name] = 0
            continue
        raw_counts[spec.name] = len(raw)

        for raw_item in raw:
            url = (raw_item.get("url") or "").strip()
            if not url or avoid_domains.is_excluded_url(url):
                continue
            key = dedup_key(url)
            if not key:
                continue

            # Has the URL ever been seen by Linky from any feed?
            prior_verdict = db.popular_verdict(url)

            if prior_verdict is None:
                # FRESH URL — never in pinboard_popular_seen.
                if key in fresh_by_key:
                    # In-scan duplicate from a lower-priority feed.
                    fresh_by_key[key].setdefault("co_sources", []).append(
                        _signal_blob(raw_item, spec.name),
                    )
                else:
                    fresh_by_key[key] = {
                        **raw_item,
                        "_source": spec.name,
                        "_url": url,
                        "_is_uplift": False,
                        "co_sources": [],
                    }
                continue

            # URL has been seen before. Has THIS feed seen it before?
            if db.feed_has_seen(url=url, source=spec.name):
                # Silent drop — today's behavior.
                continue

            # Cross-day uplift — new feed sighting on a known URL.
            new_sighting = _signal_blob(raw_item, spec.name)
            if key in uplift_by_key:
                uplift_by_key[key].setdefault("new_sightings", []).append(new_sighting)
            else:
                uplift_by_key[key] = {
                    **raw_item,
                    "_source": spec.name,          # first feed in priority order wins primary
                    "_url": url,
                    "_is_uplift": True,
                    "uplift_history": db.sightings_for(url),
                    "uplift_verdict": prior_verdict,
                    "new_sightings": [new_sighting],
                }

    fresh_items = list(fresh_by_key.values())
    # Uplift candidates capped per scan — sightings get recorded only on
    # the items we actually process, so the excess naturally rolls into
    # the next scan.
    uplift_items = list(uplift_by_key.values())[:_uplift_cap()]
    return toread, fresh_items, uplift_items, raw_counts


# ---------- per-link runtime ----------


async def _research_one(
    *, linky, prompt: str, linky_ctx_block: str, source: str,
    item: dict[str, Any], corpus=None,
) -> tuple[str, str]:
    """Run one per-link LLM call. Returns ``(kind, payload)`` per
    :func:`_parse_signal`. ``corpus`` is the archive ``CorpusHandle``
    used to render the per-card resonance block (omitted in tests)."""
    url = item.get("url") or ""
    item_block = _format_user_msg(source=source, item=item, corpus=corpus)
    user_msg = f"{linky_ctx_block}\n\n{prompt}\n\n{item_block}"
    try:
        answer, _meta = await linky.core(latest=user_msg, history=[], model="sonnet")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pinboard-scan: per-link LLM call failed for %s: %s", url, exc)
        return "fail", f"LLM error: {type(exc).__name__}"
    return _parse_signal(answer)


def _record_sightings_for_item(item: dict[str, Any], primary_source: str) -> None:
    """Record (url, source) sightings for every feed that surfaced this
    item this scan — the primary plus any in-scan co_sources (fresh
    case) or new_sightings (uplift case). Idempotent at the DB level;
    swallows DB errors per-row so one bad row doesn't take down the
    whole scan."""
    url = (item.get("_url") or item.get("url") or "").strip()
    if not url:
        return
    sources = [primary_source]
    for blob in (item.get("co_sources") or []) + (item.get("new_sightings") or []):
        src = blob.get("source")
        if src and src != primary_source:
            sources.append(src)
    for src in sources:
        try:
            db.record_sighting(url=url, source=src)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pinboard-scan: record_sighting failed for (%s, %s): %s",
                url, src, exc,
            )


def _safe_mark_popular_seen(
    url: str, title: str, *, interesting: bool, note: str, source: str,
) -> None:
    try:
        db.mark_popular_seen(
            [{"url": url, "title": title}],
            judged={url: (interesting, note)},
            verdict_source=source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pinboard-scan: mark_popular_seen failed for %s: %s", url, exc,
        )


def _safe_mark_url_researched(
    *, url: str, title: str, summary: str, confidence: str, fit_note: str,
) -> None:
    try:
        db.mark_url_researched(
            url=url, title=title, summary=summary,
            confidence=confidence, fit_note=fit_note,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pinboard-scan: mark_url_researched failed for %s: %s", url, exc,
        )


async def _process_one(
    *, ctx: "_base.JobContext", linky, prompt: str, linky_ctx_block: str,
    source: str, item: dict[str, Any], counters: dict[str, int],
) -> None:
    """Research one candidate end-to-end: LLM call, response classify, post
    if it's a card, record the message + mark seen/researched. Idempotent
    per scan — exceptions are caught and logged, never re-raised.

    Sighting policy:

    - On FAIL (fetch error / empty response): nothing recorded; URL
      retries next scan.
    - On SKIP or CARD: record sightings (primary + co_sources +
      new_sightings) and, for fresh discovery items, mark the verdict
      in ``pinboard_popular_seen``. Uplift items leave the original
      verdict alone — the sightings table tells the cross-source story
      from here on."""
    url = (item.get("url") or "").strip()
    if not url:
        return
    title = item.get("title") or ""
    is_uplift = bool(item.get("_is_uplift"))
    corpus = getattr(getattr(ctx, "deps", None), "corpus", None)
    kind, payload = await _research_one(
        linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
        source=source, item=item, corpus=corpus,
    )
    if kind == "fail":
        # Don't mark seen — retry next scan.
        counters["fail"] += 1
        logger.info("pinboard-scan: %s [%s] -> FETCH_FAILED: %s", source, url, payload[:100])
        return
    if kind == "skip":
        if source == "toread":
            # Toread items shouldn't skip; treat as researched-no-card.
            _safe_mark_url_researched(
                url=url, title=title, summary=f"SKIP: {payload}",
                confidence="⊘", fit_note=payload[:200],
            )
        else:
            _record_sightings_for_item(item, source)
            # Only the FIRST verdict on a URL lands in pinboard_popular_seen
            # (insert-or-ignore). Uplift SKIPs preserve the original
            # verdict — the sightings log captures the new sighting.
            if not is_uplift:
                _safe_mark_popular_seen(
                    url, title, interesting=False, note=payload, source=source,
                )
        counters["skip"] += 1
        logger.info("pinboard-scan: %s [%s] -> SKIP: %s%s",
                    source, url, "(uplift) " if is_uplift else "", payload[:100])
        return
    # kind == "card"
    # Allow Discord to auto-render link previews on the card so the
    # article preview shows under each #research post. The reply /
    # save / brief reactions all preserve the message id either way;
    # embeds don't affect routing.
    msg = await ctx.send_one(
        "DISCORD_CHANNEL_RESEARCH", payload, persona="linky",
        suppress_embeds=False,
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
    if source == "toread":
        _safe_mark_url_researched(
            url=url, title=title, summary=payload[:500],
            confidence="✦", fit_note="card posted",
        )
    else:
        _record_sightings_for_item(item, source)
        if not is_uplift:
            _safe_mark_popular_seen(
                url, title, interesting=True, note="card posted", source=source,
            )
    counters["posted"] += 1
    if is_uplift:
        counters["uplift"] = counters.get("uplift", 0) + 1
    logger.info("pinboard-scan: %s [%s] -> posted card msg=%s%s",
                source, url, msg.id, " (uplift)" if is_uplift else "")


# ---------- the job ----------


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return _base.JobResult(True, "(no Discord — pinboard-scan skipped)", data={"posted": 0})
    linky = team.bots.get("linky")
    if linky is None or getattr(linky, "user", None) is None:
        return _base.JobResult(True, "(Linky unavailable — pinboard-scan skipped)", data={"posted": 0})

    # Whole-job lock so a manual `/workshop links scan` can't overlap with
    # the scheduled `:05` fire (or two manual fires in quick succession).
    # The lock key isn't an asset path — pinboard-scan doesn't write a
    # single file — so we use the sentinel ``job:<name>`` which is just a
    # string the lock table accepts.
    try:
        with _base.job_lock([f"job:{NAME}"], NAME):
            return await _run_locked(ctx, linky)
    except _base.JobLocked as exc:
        logger.info("pinboard-scan: skipping — already running (%s)", exc.holder_desc)
        return _base.JobResult(
            True, f"pinboard-scan already running ({exc.holder_desc}); skipped.",
            data={"posted": 0},
        )


async def _run_locked(ctx: "_base.JobContext", linky) -> "_base.JobResult":
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

    # Gather toread + every discovery feed in one blocking pass.
    toread, fresh_items, uplift_items, raw_counts = await asyncio.to_thread(
        _gather_candidates,
    )
    if not toread and not fresh_items and not uplift_items:
        return _base.JobResult(
            True, "Linky: nothing new in any source — PASS.", data={"posted": 0},
        )

    # Group fresh items by primary source so the per-spec cap applies.
    fresh_by_source: dict[str, list[dict[str, Any]]] = {
        spec.name: [] for spec in DISCOVERY_FEEDS
    }
    for item in fresh_items:
        fresh_by_source[item["_source"]].append(item)

    counters: dict[str, int] = {"posted": 0, "skip": 0, "fail": 0, "uplift": 0}

    with db.AgentRun("linky", trigger="pinboard-scan") as run_:
        # Toread first — Jamie's own picks before random discovery finds.
        for item in toread[:_TOREAD_PER_SCAN_CAP]:
            await _process_one(
                ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                source="toread", item=item, counters=counters,
            )
        # Then fresh discovery items, walking feeds in priority order.
        for spec in DISCOVERY_FEEDS:
            for item in fresh_by_source[spec.name][:spec.per_scan_cap]:
                await _process_one(
                    ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                    source=spec.name, item=item, counters=counters,
                )
        # Finally, uplift candidates — re-evaluations of URLs that
        # appeared on a new feed since their first sighting. Already
        # capped per scan.
        for item in uplift_items:
            await _process_one(
                ctx=ctx, linky=linky, prompt=prompt, linky_ctx_block=linky_ctx_block,
                source=item["_source"], item=item, counters=counters,
            )
        run_.records_written = counters["posted"]

    considered_parts = [f"{len(toread)} toread"]
    for spec in DISCOVERY_FEEDS:
        considered_parts.append(f"{raw_counts.get(spec.name, 0)} {spec.name}")
    if uplift_items:
        considered_parts.append(f"{len(uplift_items)} uplift")
    considered = " + ".join(considered_parts)
    summary_extras = []
    if counters["uplift"]:
        summary_extras.append(f"{counters['uplift']} uplift")
    summary_tail = (
        f"{counters['skip']} skip, {counters['fail']} retry"
        + (f", {', '.join(summary_extras)}" if summary_extras else "")
    )
    if counters["posted"] == 0:
        return _base.JobResult(
            True,
            f"Linky: considered {considered}; no cards posted ({summary_tail}).",
            data={"posted": 0, **counters},
        )
    return _base.JobResult(
        True,
        f"Linky: posted {counters['posted']} card(s) ({summary_tail}).",
        data={"posted": counters["posted"], **counters},
    )
