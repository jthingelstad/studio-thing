"""Backward-compat shim — the canonical Buttondown client now lives at
``apps/workshop_bot/systems/buttondown/client.py``.

Existing call sites (``agent_tools.py``'s ``t_fetch_buttondown_subscribers``
handler, ``scheduler/handlers.py`` reports) keep importing
``from .buttondown import recent_subscribers`` etc. through this shim
until the workshop-bot redesign Phase 5 cleanup deletes the file.
"""

from __future__ import annotations

from ..systems.buttondown.client import (  # noqa: F401 — re-exports for shim
    API_BASE,
    counts,
    recent_subscribers,
    recent_unsubscribes,
)
