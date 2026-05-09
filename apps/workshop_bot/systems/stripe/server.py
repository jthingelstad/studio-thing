"""StripeServer — registry-facing tool surface for the stripe system."""

from __future__ import annotations

from .._base import ToolDef
from . import client


class StripeServer:
    name = "stripe"
    # Donor data is privacy-sensitive. Patty is the only persona that
    # ever reaches for Stripe (Thursday member.json composition,
    # daily heartbeat). The other personas don't see these tools at
    # all — registry filtering enforces it. If campaign attribution
    # ever needs Stripe data, hand off to Patty via `inbox__post`.
    restricted_to = {"patty"}

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="balance",
                description=(
                    "Stripe balance: available + pending + total in USD. "
                    "Total reads as 'amount raised so far' for the current "
                    "cycle."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.balance(),
            ),
            ToolDef(
                name="recent_donations",
                description=(
                    "Last N successful donations. Each record: id, "
                    "amount_usd, created_at, donor_hash, donor_domain, "
                    "ref_tag, payment_intent. Donor name + email hashed — "
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
                    "Returns {months: [{month: 'YYYY-MM', count, total_usd}]}."
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
                    "window. Returns {days, total_count, total_usd, by_ref}. "
                    "NOTE: returns mostly '(no-ref)' until the donate flow "
                    "(Stripe Payment Link) is configured to set `ref` on "
                    "Checkout Session metadata."
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
                    "Current-calendar-year donation totals + configured "
                    "nonprofit. Returns {year, count, total_usd, average_usd, "
                    "current_nonprofit}."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=lambda deps, **_kw: client.year_to_date(),
            ),
        ]
