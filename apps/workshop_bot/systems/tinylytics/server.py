"""TinylyticsServer — registry-facing tool surface for tinylytics."""

from __future__ import annotations

from .._base import ToolDef
from . import client


class TinylyticsServer:
    name = "tinylytics"

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="summary",
                description=(
                    "Trailing-window engagement summary for "
                    "weekly.thingelstad.com: total hits + top pages + top "
                    "referrers. Use to ground 'what's working lately'. "
                    "Returns partial data even if individual endpoints fail."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "trailing window in days; default 7, max 730",
                        },
                    },
                },
                handler=lambda deps, days=7, **_kw: client.summary(days=int(days)),
            ),
            ToolDef(
                name="top_pages",
                description=(
                    "Highest-traffic pages over the trailing window. Each "
                    "entry has path, views, unique_views. Use to see which "
                    "issues or topic pages are getting traction right now."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 7"},
                        "limit": {"type": "integer", "description": "default 20"},
                    },
                },
                handler=lambda deps, days=7, limit=20, **_kw: client.top_pages(
                    days=int(days), limit=int(limit)
                ),
            ),
            ToolDef(
                name="referrers",
                description=(
                    "Top external referrers over the trailing window — "
                    "where readers are coming from off-site. Each entry has "
                    "referrer + hit_count. Use to spot an inbound link or "
                    "platform pickup. Note: a `referrer` of null means "
                    "direct visit; empty string means the referrer header "
                    "was stripped."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 7"},
                        "limit": {"type": "integer", "description": "default 20"},
                    },
                },
                handler=lambda deps, days=7, limit=20, **_kw: client.referrers(
                    days=int(days), limit=int(limit)
                ),
            ),
        ]
