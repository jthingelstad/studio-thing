"""StripeServer — registry-facing tool surface for the stripe system."""

from __future__ import annotations

from .._base import ToolDef
from . import client


class StripeServer:
    name = "stripe"

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="balance",
                description=(
                    "Current Stripe balance — available + pending + total in "
                    "USD. The total reads as 'amount raised so far' for the "
                    "current support cycle. No arguments."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.balance(),
            ),
            ToolDef(
                name="recent_donations",
                description=(
                    "Last N successful donations, newest first. Each record "
                    "has id, amount_usd, created_at, donor_hash, donor_domain, "
                    "ref_tag (if set on charge metadata), payment_intent. "
                    "Donor name and email are hashed before reaching you — "
                    "never raw PII."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "default 25"},
                    },
                },
                handler=lambda deps, limit=25, **_kw: client.recent_donations(
                    limit=int(limit)
                ),
            ),
            ToolDef(
                name="donations_by_month",
                description=(
                    "Trailing N months of donations aggregated by month. "
                    "Returns {months: [{month: 'YYYY-MM', count, total_usd}]}. "
                    "Use to spot a month-over-month trend (cohort size, "
                    "amount-per-donor) without paging through every charge."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "months": {
                            "type": "integer",
                            "description": "trailing window in months; default 12",
                        },
                    },
                },
                handler=lambda deps, months=12, **_kw: client.donations_by_month(
                    months=int(months)
                ),
            ),
            ToolDef(
                name="donations_by_ref",
                description=(
                    "Aggregate donations by `metadata.ref` over the trailing "
                    "window. Returns {days, total_count, total_usd, by_ref: "
                    "{<ref>: {count, total_usd}}}. Charges without a ref are "
                    "bucketed under '(no-ref)'. NOTE: returns mostly '(no-ref)' "
                    "until the donate flow (Stripe Payment Link) is configured "
                    "to set `ref` on Checkout Session metadata."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "trailing window in days; default 90",
                        },
                    },
                },
                handler=lambda deps, days=90, **_kw: client.donations_by_ref(
                    days=int(days)
                ),
            ),
            ToolDef(
                name="year_to_date",
                description=(
                    "Current-calendar-year donation totals + the configured "
                    "nonprofit. Returns {year, count, total_usd, average_usd, "
                    "current_nonprofit}. Use as the single tool for the "
                    "Thursday member.json progress update."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.year_to_date(),
            ),
        ]
