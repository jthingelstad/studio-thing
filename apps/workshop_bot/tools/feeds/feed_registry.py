"""Discovery-feed registry — the data definition for Linky's `pinboard-scan` job.

Every discovery feed is one ``FeedSpec`` entry in :data:`DISCOVERY_FEEDS`.
The job iterates the tuple; nothing else in the job is feed-specific. To
add a feed:

1. Write a ``tools/<name>.py`` fetcher that returns
   ``list[{url, title, [discussion_url], [score], [comment_count], [submitter], [tags]}]``
   when called as ``fetch(limit=N)``.
2. Add one ``FeedSpec(...)`` entry to :data:`DISCOVERY_FEEDS` below.
3. Add the source name to ``db.RESEARCH_SOURCES`` (one-line update).

There are no per-feed constants in the job, no per-feed branches in
``_format_user_msg``, and no scattered "is this feed in the discovery
set?" checks. The registry is the single source of truth.

The Toread lane is *not* in this registry — it has a different fetcher
signature (no `limit` semantics that match), a different dedup table
(`pinboard_research_done`, not `pinboard_popular_seen`), and different
card-action semantics (no SKIP path, no save-reaction-create path).
Toread stays separately wired in the job.

This module also defines :class:`CoSource` — the dict shape carried in
``co_sources`` and ``new_sightings`` lists on candidate items, so
downstream consumers (the user-message renderer, the sightings
recorder) can rely on a typed contract instead of bare
``dict[str, Any]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypedDict

# Imports at module scope — the fetcher modules are all leaf nodes
# (only depend on ``requests`` and stdlib), so importing them here
# can't introduce a cycle through the workshop_bot package.
from ...systems.pinboard import client as pinboard


class CoSource(TypedDict, total=False):
    """One co-source entry attached to a candidate item.

    Shape carried in ``item["co_sources"]`` (fresh items, in-scan
    duplicates from lower-priority feeds) and ``item["new_sightings"]``
    (uplift items, new feed sightings of a previously-seen URL). With
    one active feed today this is dormant, but the typed shape remains
    for future feeds."""

    source: str
    discussion_url: str
    score: int
    comment_count: int


@dataclass(frozen=True)
class FeedSpec:
    """One discovery feed. The ``fetch`` callable should be a thin lambda
    that delegates to the actual module function (e.g.
    ``lambda limit: pinboard.popular(limit=limit)``); the indirection
    lets tests patch the module attribute and have the patch take effect
    at call time without rewriting the spec.

    Fields:

    - ``name``     — stable identifier; used as the ``source`` string in
      ``linky_research_messages``, ``pinboard_popular_seen`` audits, and
      everywhere the prompt sees a source label.
    - ``label``    — display string for the LLM's user message.
    - ``pin_label``— the short tag rendered in the card header link
      Empty when the feed has no meaningful discussion thread to link to.
    - ``fetch``    — ``(limit: int) -> list[dict]``; raises on upstream
      failure (the job catches and degrades to ``[]`` per spec).
    - ``per_scan_cap``  — max cards from this feed per scan.
    - ``feed_limit``    — how many items to ask the fetcher for.
    - ``primary_priority`` — higher wins cross-source merge if more feeds
      are added later.
    - ``enabled`` — when False, ``pinboard-scan`` skips this feed at
      iteration time. The spec stays in :data:`DISCOVERY_FEEDS` so the
      label / pin_label / priority history is preserved (legacy
      ``pinboard_popular_seen`` rows still reference the source name);
      flip back to True to re-enable. Keep this in sync with what's
      actually wired — a disabled feed shouldn't have downstream code
      expecting fresh data from it.
    """

    name: str
    label: str
    pin_label: str
    fetch: Callable[[int], list[dict[str, Any]]]
    per_scan_cap: int = 10
    feed_limit: int = 25
    primary_priority: int = 0
    enabled: bool = True


def by_name(feeds: tuple[FeedSpec, ...], name: str) -> FeedSpec | None:
    """Look up a spec by ``name`` in ``feeds`` (typically
    :data:`DISCOVERY_FEEDS`). Returns ``None`` for ``name == "toread"`` or
    any other non-discovery source — callers branch on ``None`` to mean
    "not a discovery feed."""
    for spec in feeds:
        if spec.name == name:
            return spec
    return None


# The discovery-feed registry. Each spec is one source. Lambdas in
# ``fetch`` re-resolve the module attribute at call time, so tests can
# patch ``pinboard.popular`` directly and the spec picks up the patch
# without rewriting.
#
# Priority order in the tuple matters for two things: it's the
# iteration order in the job's loops (toread is handled separately,
# but discovery feeds fire in this order), and the highest
# ``primary_priority`` wins when cross-source merging picks a primary.
# The active set is intentionally just **Pinboard popular**. The toread
# lane (Jamie's own public-toread pile) is separately wired in the job.
# Keep this registry generic so future feeds can be added by one new
# ``FeedSpec`` instead of changing the scan loop.
DISCOVERY_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec(
        name="popular", label="Pinboard popular", pin_label="",
        fetch=lambda limit: pinboard.popular(limit=limit),
        per_scan_cap=10, feed_limit=30, primary_priority=10,
    ),
)


def active_feeds(feeds: tuple[FeedSpec, ...] = DISCOVERY_FEEDS) -> list[FeedSpec]:
    """Return the subset of ``feeds`` with ``enabled=True``. The job
    iterates this rather than ``DISCOVERY_FEEDS`` directly so a disabled
    feed never fires a fetcher / never produces cards / never has its
    URLs marked seen — but the spec stays in the registry so a future
    re-enable doesn't require resurrecting anything."""
    return [f for f in feeds if f.enabled]
