"""Persistent button View for the Share card (`#promotion`, registered on Marky).

Per-issue syndication launchpad for the last-published issue. Standing campaign
management stays in `/marky campaign …` — not here.
"""

from __future__ import annotations

import discord

from ...jobs import daily_metrics, promotion_prep, share_card
from ._card_base import launch


class ShareCardView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Draft promo", emoji="📝", style=discord.ButtonStyle.secondary,
                       custom_id=share_card.BTN_DRAFT, row=0)
    async def _draft(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, promotion_prep.run, "promotion-prep",
                     started="📝 Drafting LinkedIn + r/WeeklyThing copy in #promotion (never auto-posts).",
                     refresh=lambda ctx: share_card.post_or_update(ctx))

    @discord.ui.button(label="Refresh metrics", emoji="📊", style=discord.ButtonStyle.secondary,
                       custom_id=share_card.BTN_METRICS, row=0)
    async def _metrics(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, daily_metrics.run, "daily-metrics",
                     started="📊 Polling campaign traffic + growth…",
                     refresh=lambda ctx: share_card.post_or_update(ctx))

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary,
                       custom_id=share_card.BTN_REFRESH, row=0)
    async def _refresh(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, lambda ctx: share_card.post_or_update(ctx), "share-refresh",
                     started="🔄 Refreshing the Share card…", refresh=None)


def build_view(state: dict) -> "ShareCardView":
    return ShareCardView()
