"""ButtondownServer — registry-facing tool surface for the buttondown system.

The registry prefixes each tool's action name with ``buttondown.`` so
the model sees ``buttondown.list_subscribers``, ``buttondown.counts``,
etc.
"""

from __future__ import annotations

from typing import Any, Optional

from .._base import ToolDef
from . import client


class ButtondownServer:
    name = "buttondown"

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="counts",
                description=(
                    "Top-level subscriber counts for the newsletter: total, "
                    "premium, unsubscribed. Cheap — three single-row API "
                    "calls. No arguments."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.counts(),
            ),
            ToolDef(
                name="list_subscribers",
                description=(
                    "Most recent subscribers, newest first. Returns "
                    "normalized records with hashed email + email domain "
                    "(raw email addresses never reach the model). Pass "
                    "type='premium' or type='unsubscribed' to filter."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "default 25"},
                        "type": {
                            "type": "string",
                            "description": "optional Buttondown subscriber type filter",
                        },
                    },
                },
                handler=_handle_list_subscribers,
            ),
            ToolDef(
                name="recent_unsubscribes",
                description=(
                    "Recently churned subscribers, newest first. Same "
                    "normalized shape as list_subscribers. Email addresses "
                    "are hashed before reaching you."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "default 25"},
                    },
                },
                handler=lambda deps, limit=25, **_kw: client.recent_unsubscribes(
                    limit=int(limit)
                ),
            ),
            ToolDef(
                name="subscriber_sources",
                description=(
                    "Aggregated source attribution counts over a trailing "
                    "window. Returns {days, subscribers_seen, by_source} "
                    "where by_source is a dict like {'embed': 42, 'api': "
                    "13, …}. Use to ground 'where are signups coming from?' "
                    "instead of guessing."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 30"},
                    },
                },
                handler=lambda deps, days=30, **_kw: client.subscriber_sources(
                    days=int(days)
                ),
            ),
            ToolDef(
                name="subscriber_growth",
                description=(
                    "Net subscriber delta over the trailing window plus a "
                    "cohort-by-source breakdown. Returns {added, churned, "
                    "net, by_source}. Pair with subscriber_sources for the "
                    "full picture."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 30"},
                    },
                },
                handler=lambda deps, days=30, **_kw: client.subscriber_growth(
                    days=int(days)
                ),
            ),
            ToolDef(
                name="list_recent_emails",
                description=(
                    "Last N sent emails: id, subject, publish_date, status, "
                    "and inline engagement counters (recipients, deliveries, "
                    "opens, clicks, unsubscriptions). No body. Use to scan "
                    "what landed and what didn't before reaching for "
                    "email_engagement on a specific id."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "default 25"},
                    },
                },
                handler=lambda deps, limit=25, **_kw: client.list_recent_emails(
                    limit=int(limit)
                ),
            ),
            ToolDef(
                name="email_engagement",
                description=(
                    "Per-email engagement counters for one sent email by "
                    "Buttondown id. Returns the analytics dict (recipients, "
                    "deliveries, opens, clicks, unsubscriptions, "
                    "subscriptions, replies). NOTE: Buttondown does not "
                    "expose a per-link click breakdown — `clicks` is a "
                    "single integer over the whole email."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "email_id": {"type": "string"},
                    },
                    "required": ["email_id"],
                },
                handler=lambda deps, email_id, **_kw: client.email_engagement(
                    email_id=email_id
                ),
            ),
        ]


def _handle_list_subscribers(
    deps: Any,
    limit: int = 25,
    type: Optional[str] = None,  # noqa: A002 — model-facing arg
    **_kw: Any,
) -> list[dict[str, Any]]:
    return client.recent_subscribers(limit=int(limit), type_filter=type)
