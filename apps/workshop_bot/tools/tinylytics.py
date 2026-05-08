"""Backward-compat shim — the canonical Tinylytics client now lives at
``apps/workshop_bot/systems/tinylytics/client.py``.

Existing call sites (``agent_tools.py``'s ``t_fetch_tinylytics`` /
``t_fetch_tinylytics_ref`` handlers, ``scheduler/handlers.py``) keep
importing ``from .tinylytics import safe_summary, top_pages`` etc.
through this shim until the workshop-bot redesign Phase 5 cleanup
deletes the file.
"""

from __future__ import annotations

from ..systems.tinylytics.client import (  # noqa: F401 — re-exports for shim
    API_BASE,
    DEFAULT_TIMEOUT,
    events,
    ref_traffic,
    referrers,
    safe_summary,
    stats,
    top_pages,
)
