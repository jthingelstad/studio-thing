"""Read current support program state for Patty's CTA generation.

Source files:
- apps/site/_data/support.json — current/past nonprofits, donate URL
- apps/site/_data/stats.json — subscriber count, premium count, raised amount
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SUPPORT_PATH = REPO / "apps" / "site" / "_data" / "support.json"
STATS_PATH = REPO / "apps" / "site" / "_data" / "stats.json"


def read() -> dict[str, Any]:
    support: dict[str, Any] = {}
    stats: dict[str, Any] = {}
    if SUPPORT_PATH.exists():
        support = json.loads(SUPPORT_PATH.read_text(encoding="utf-8"))
    if STATS_PATH.exists():
        stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    return {"support": support, "stats": stats}


def render_state(state: dict[str, Any]) -> str:
    """Render to a compact human-readable block for the LLM."""
    support = state.get("support") or {}
    stats = state.get("stats") or {}
    current = support.get("current") or {}
    past = support.get("past") or []

    lines = ["# Current support program state", ""]
    if current:
        name = current.get("nonprofit", "")
        short = current.get("short_name", "")
        year = current.get("year", "")
        url = current.get("url", "")
        desc = current.get("description", "")
        head = f"Current nonprofit ({year}): {name}" + (f" ({short})" if short else "")
        lines.append(head)
        if url:
            lines.append(f"URL: {url}")
        if desc:
            lines.append(f"About: {desc}")
    if past:
        names = [
            f"{p.get('nonprofit', '')} ({p.get('year', '')}, raised ${p.get('amount_raised', 0):.2f})"
            for p in past
        ]
        lines.append("Past nonprofits: " + "; ".join(names))
    if stats:
        if "subscriber_count" in stats:
            lines.append(f"Total subscribers: {stats['subscriber_count']}")
        if "premium_subscriber_count" in stats:
            lines.append(f"Supporting members: {stats['premium_subscriber_count']}")
        if "amount_raised" in stats:
            lines.append(f"Raised this year: ${stats['amount_raised']:.2f}")
    donate = current.get("stripe_donate_url") or ""
    if donate:
        lines.append(f"Donate URL: {donate}")
    return "\n".join(lines)
