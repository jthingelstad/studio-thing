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
                    "referrers. Returns partial data on partial failure."
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
                    "entry has path, views, unique_views."
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
                    "Top external referrers (HTTP `Referer` header, e.g. "
                    "`linkedin.com`) over the trailing window. NOT for "
                    "`?ref=` campaign attribution — use `sources` for that. "
                    "`referrer` null = direct visit; empty string = header "
                    "stripped."
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
                    "Top per-hit `source` values over a trailing window. "
                    "Tinylytics auto-extracts `?ref=<x>` and `?utm_source=<x>` "
                    "from landing URLs into this field. Use this — NOT "
                    "`referrers` — for ref-tag traffic attribution. Returns "
                    "{days, by_source, total_sources}."
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
                    "All-time top paths on the site (cached, no date "
                    "window). Pass prefix='/archive/' to scope to issue "
                    "pages. Each entry has path, total_hits, unique_hits, "
                    "percentage."
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
                    "Recent visitor journeys: per-visitor pages, entry/exit, "
                    "duration, referrer, country. Returns {user_journeys, "
                    "summary} (summary has total_visitors and bounce_rate)."
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
                    "uid, path, created_at."
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
                    "Tinylytics' daily AI summary for the site: signals "
                    "(page breakouts, referrer surges), traffic patterns, "
                    "recommendations. Subscription-gated."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.insights(),
            ),
            ToolDef(
                name="uptime",
                description=(
                    "Site uptime + SSL/domain expiry. Returns uptime %, "
                    "last_check_at, last_status_code, ssl.expires_at, "
                    "domain.expires_at. Subscription-gated."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.uptime(),
            ),
        ]
