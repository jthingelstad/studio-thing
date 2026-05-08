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
                    "weekly.thingelstad.com: stats + top pages + referrers "
                    "+ custom events (donate, membership). Use to ground "
                    "'what's working lately'. Returns partial data even if "
                    "individual endpoints fail."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "trailing window in days; default 7",
                        },
                    },
                },
                handler=lambda deps, days=7, **_kw: client.safe_summary(
                    days=int(days)
                ),
            ),
            ToolDef(
                name="ref_traffic",
                description=(
                    "Aggregate page hits attributed to a ?ref=<tag> URL "
                    "over a trailing window. Pass the ref tag (e.g. "
                    "'dd-2026-05-15') and the lookback in days. Returns "
                    "total hits and the per-path breakdown."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string"},
                        "days": {"type": "integer", "description": "default 14"},
                    },
                    "required": ["tag"],
                },
                handler=lambda deps, tag, days=14, **_kw: client.ref_traffic(
                    tag=tag, days=int(days)
                ),
            ),
            ToolDef(
                name="top_pages",
                description=(
                    "Highest-traffic pages over the trailing window. Each "
                    "entry has path/hits. Use to see which issues or "
                    "topic pages are getting traction right now."
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
                    "where readers are coming from off-site. Use to spot "
                    "an inbound link or platform pickup."
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
            ToolDef(
                name="events",
                description=(
                    "Recent custom events fired by the site (donate, "
                    "membership, etc.). Trailing window. Each entry "
                    "carries the event name + timestamp + any payload."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 7"},
                        "limit": {"type": "integer", "description": "default 50"},
                    },
                },
                handler=lambda deps, days=7, limit=50, **_kw: client.events(
                    days=int(days), limit=int(limit)
                ),
            ),
        ]
