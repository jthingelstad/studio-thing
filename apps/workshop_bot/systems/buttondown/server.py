"""ButtondownServer — registry-facing tool surface for the buttondown system.

The registry prefixes each tool's action name with ``buttondown__`` so
the model sees ``buttondown__list_subscribers``, ``buttondown__counts``,
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
                    "Top-level subscriber counts: total, premium, "
                    "unsubscribed."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.counts(),
            ),
            ToolDef(
                name="list_subscribers",
                description=(
                    "Most recent subscribers, newest first. Hashed email + "
                    "domain only — raw addresses never reach the model. "
                    "Optional `type` filter: 'premium', 'unsubscribed'."
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
                    "Recently churned subscribers. Same hashed shape as "
                    "list_subscribers."
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
                    "Aggregated `source` attribution counts over a trailing "
                    "window. Returns {days, subscribers_seen, by_source}."
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
                name="attribution_summary",
                description=(
                    "Aggregated `metadata.ref` campaign attribution — "
                    "answers 'is this campaign converting to **subscribers**?'. "
                    "Different question from `tinylytics__sources` (traffic). "
                    "Returns {by_ref, by_landing, samples} with hashed-email "
                    "samples."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "default 30"},
                    },
                },
                handler=lambda deps, days=30, **_kw: client.attribution_summary(
                    days=int(days)
                ),
            ),
            ToolDef(
                name="subscriber_growth",
                description=(
                    "Net subscriber delta over the trailing window plus "
                    "cohort-by-source. Returns {added, churned, net, "
                    "by_source}."
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
                    "Last N sent emails: id, subject, send timestamps, plus "
                    "inline engagement counters. No body."
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
                    "Per-email engagement counters by Buttondown id. NOTE: "
                    "no per-link click breakdown — `clicks` is a single "
                    "integer over the whole email."
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
