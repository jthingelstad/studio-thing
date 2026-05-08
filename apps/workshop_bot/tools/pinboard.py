"""Backward-compat shim — the canonical Pinboard client now lives at
``apps/workshop_bot/systems/pinboard/client.py``.

Existing call sites (``agent_tools.py``'s ``t_fetch_pinboard*`` /
``t_read_stored_bookmarks`` handlers, ``scheduler/handlers.py``) keep
importing ``from .pinboard import recent_posts, all_unread, ...``
through this shim until the workshop-bot redesign Phase 5 cleanup
deletes the file.
"""

from __future__ import annotations

from ..systems.pinboard.client import (  # noqa: F401 — re-exports for shim
    API_BASE,
    POPULAR_FEED,
    all_unread,
    bookmark_url,
    normalize_post,
    popular,
    recent_posts,
    tag_summary,
)
