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
            ToolDef(
                name="sources",
                description=(
                    "Aggregate the per-hit `source` field over a trailing "
                    "window. Tinylytics auto-extracts `?ref=<x>` and "
                    "`?utm_source=<x>` from landing URLs into this field. "
                    "Use this — NOT `referrers` — to answer 'where did "
                    "DenseDiscovery / LinkedIn / etc. traffic land this "
                    "week.' Returns {days, hits_seen, with_source, "
                    "by_source, by_path, samples}. The API has no "
                    "group_by=source so this paginates raw hits."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 30"},
                        "limit": {"type": "integer", "description": "default 20"},
                    },
                },
                handler=lambda deps, days=30, limit=20, **_kw: client.sources(
                    days=int(days), limit=int(limit)
                ),
            ),
            ToolDef(
                name="leaderboard",
                description=(
                    "All-time top paths on the site (cached server-side, "
                    "no date window). Pass prefix='/archive/' to scope to "
                    "issue pages. Each entry has path, total_hits, "
                    "unique_hits, percentage. Use to recognize evergreen "
                    "issues vs. recent spikes."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "prefix": {
                            "type": "string",
                            "description": "partial path filter, e.g. '/archive/'",
                        },
                        "limit": {"type": "integer", "description": "default 20"},
                    },
                },
                handler=lambda deps, prefix=None, limit=20, **_kw: client.leaderboard(
                    prefix=prefix, limit=int(limit)
                ),
            ),
            ToolDef(
                name="user_journeys",
                description=(
                    "Recent visitor journeys over the trailing window: per "
                    "visitor, the pages they hit, entry/exit, duration, "
                    "referrer, country. Use to answer 'what do people read "
                    "after landing from X' or to spot multi-page sessions. "
                    "Returns {user_journeys, summary} where summary has "
                    "total_visitors and bounce_rate."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 7"},
                        "limit": {"type": "integer", "description": "default 20"},
                    },
                },
                handler=lambda deps, days=7, limit=20, **_kw: client.user_journeys(
                    days=int(days), limit=int(limit)
                ),
            ),
            ToolDef(
                name="kudos",
                description=(
                    "Recent kudos (heart-button taps on per-issue archive "
                    "pages) over the trailing window. Each entry has id, "
                    "uid, path, created_at. Complements top_pages — kudos "
                    "is intent-to-signal, not just attention."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 30"},
                        "limit": {"type": "integer", "description": "default 50"},
                    },
                },
                handler=lambda deps, days=30, limit=50, **_kw: client.kudos(
                    days=int(days), limit=int(limit)
                ),
            ),
            ToolDef(
                name="insights",
                description=(
                    "Latest daily AI insights generated by Tinylytics: "
                    "summary text, signals (page breakouts, referrer surges, "
                    "traffic shifts), traffic patterns, recommendations. "
                    "Updated daily ~01:00 in the account timezone. Use as "
                    "an opening orientation before pulling specific tools."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.insights(),
            ),
            ToolDef(
                name="uptime",
                description=(
                    "Site uptime + SSL/domain expiry monitor. Returns "
                    "current uptime %, last_check_at, last_status_code, "
                    "ssl.expires_at, domain.expires_at. Use to confirm the "
                    "site is healthy before drawing conclusions about a "
                    "traffic dip."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.uptime(),
            ),
        ]
