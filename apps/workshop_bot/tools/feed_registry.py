"""Discovery-feed registry — the data definition for Linky's `pinboard-scan` job.

Every discovery feed (Pinboard popular, Lobsters hottest, Hacker News
front page, Tildes ~tech, IndieWeb News, …) is one ``FeedSpec`` entry
in a tuple. The job iterates the tuple; nothing else in the job is
feed-specific. To add a feed:

1. Write a ``tools/<name>.py`` fetcher that returns
   ``list[{url, title, [discussion_url], [score], [comment_count], [submitter], [tags]}]``
   when called as ``fetch(limit=N)``.
2. Add one ``FeedSpec(...)`` entry to ``DISCOVERY_FEEDS`` in
   ``jobs/pinboard_scan.py`` (or wherever the canonical tuple lives).
3. Add the source name to ``db.RESEARCH_SOURCES`` (one-line update).

There are no per-feed constants in the job, no per-feed branches in
``_format_user_msg``, and no scattered "is this feed in the discovery
set?" checks. The registry is the single source of truth.

The Toread lane is *not* in this registry — it has a different fetcher
signature (no `limit` semantics that match), a different dedup table
(`pinboard_research_done`, not `pinboard_popular_seen`), and different
card-action semantics (no SKIP path, no save-reaction-create path).
Toread stays separately wired in the job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


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
    """

    name: str
    label: str
    pin_label: str
    fetch: Callable[[int], list[dict[str, Any]]]
    per_scan_cap: int = 10
    feed_limit: int = 25
    primary_priority: int = 0


def by_name(feeds: tuple[FeedSpec, ...], name: str) -> FeedSpec | None:
    """Look up a spec by ``name`` in ``feeds`` (typically
    ``DISCOVERY_FEEDS``). Returns ``None`` for ``name == "toread"`` or
    any other non-discovery source — callers branch on ``None`` to mean
    "not a discovery feed."""
    for spec in feeds:
        if spec.name == name:
            return spec
    return None
