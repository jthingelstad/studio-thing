"""Discovery-feed registry — the data definition for Linky's `pinboard-scan` job.

Every discovery feed (Pinboard popular, Lobsters hottest, Hacker News
front page, Tildes ~tech, IndieWeb News, …) is one ``FeedSpec`` entry
in :data:`DISCOVERY_FEEDS`. The job iterates the tuple; nothing else
in the job is feed-specific. To add a feed:

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
from . import hackernews, indieweb_news, lobsters, tildes


class CoSource(TypedDict, total=False):
    """One co-source entry attached to a candidate item.

    Shape carried in ``item["co_sources"]`` (fresh items, in-scan
    duplicates from lower-priority feeds) and ``item["new_sightings"]``
    (uplift items, new feed sightings of a previously-seen URL). The
    ``source`` field is required; the rest are optional and missing for
    feeds that don't expose votes / threads (Pinboard popular,
    Tildes ~tech atom feed when score=0)."""

    source: str
    discussion_url: str
    score: int
    comment_count: int


@dataclass(frozen=True)
class FeedSpec:
    """One discovery feed. The ``fetch`` callable should be a thin lambda
    that delegates to the actual module function (e.g.
    ``lambda limit: lobsters.hottest(limit=limit)``); the indirection lets
    tests patch the module attribute and have the patch take effect at
    call time without rewriting the spec.

    Fields:

    - ``name``     — stable identifier; used as the ``source`` string in
      ``linky_research_messages``, ``pinboard_popular_seen`` audits, and
      everywhere the prompt sees a source label.
    - ``label``    — display string for the LLM's user message and
      "Also trending on …" rendering (e.g. "Hacker News").
    - ``pin_label``— the short tag rendered in the card header link
      (e.g. "HN", "lobste.rs", "tildes"). Empty when the feed has no
      meaningful discussion thread to link to (e.g. Pinboard popular).
    - ``fetch``    — ``(limit: int) -> list[dict]``; raises on upstream
      failure (the job catches and degrades to ``[]`` per spec).
    - ``per_scan_cap``  — max cards from this feed per scan.
    - ``feed_limit``    — how many items to ask the fetcher for.
    - ``primary_priority`` — higher wins cross-source merge; the card's
      ``📖 · source`` footer reflects the primary.
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
# patch ``pinboard.popular`` / ``lobsters.hottest`` / etc. directly and
# the spec picks up the patch without rewriting.
#
# Priority order in the tuple matters for two things: it's the
# iteration order in the job's loops (toread is handled separately,
# but discovery feeds fire in this order), and the highest
# ``primary_priority`` wins when cross-source merging picks a primary.
# See the substance-gradient rationale in CLAUDE.md.
# Most discovery feeds are currently DISABLED while we tune Linky's
# signal-to-noise ratio. The active set is Pinboard popular + the
# (separately-wired) toread lane; everything else stays defined so the
# wiring is intact when we re-enable them gradually. Flip ``enabled``
# to True on a feed when it's ready to come back online.
DISCOVERY_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec(
        name="indieweb_news", label="IndieWeb News", pin_label="indieweb",
        fetch=lambda limit: indieweb_news.top(limit=limit),
        per_scan_cap=10, feed_limit=20, primary_priority=50,
        enabled=False,
    ),
    FeedSpec(
        name="tildes", label="Tildes ~tech", pin_label="tildes",
        fetch=lambda limit: tildes.top(limit=limit),
        per_scan_cap=10, feed_limit=25, primary_priority=40,
        enabled=False,
    ),
    FeedSpec(
        name="lobsters", label="Lobsters", pin_label="lobste.rs",
        fetch=lambda limit: lobsters.hottest(limit=limit),
        per_scan_cap=10, feed_limit=25, primary_priority=30,
        enabled=False,
    ),
    FeedSpec(
        name="hackernews", label="Hacker News", pin_label="HN",
        fetch=lambda limit: hackernews.top(limit=limit),
        per_scan_cap=10, feed_limit=25, primary_priority=20,
        enabled=False,
    ),
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
