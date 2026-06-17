"""Persistent button View for the Publish card (`#production`, registered on Scout).

Shared envelope (subject/description) + CTA pick, then the gated per-channel 🚀
ship buttons. Gating disables a ship button until its channel is ready.
"""

from __future__ import annotations

import discord

from ...jobs import compose_cta, compose_haiku, compose_meta, publish as publish_job, publish_card, put_to_bed, share_card
from ._card_base import launch

_GATED = frozenset({
    publish_card.BTN_RECOMPOSE,
    publish_card.BTN_EMAIL, publish_card.BTN_WEBSITE, publish_card.BTN_PODCAST, publish_card.BTN_ALL,
})


class PublishCardView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    # ── row 0: envelope + CTA ───────────────────────────────────────────
    @discord.ui.button(label="Subject + Desc", style=discord.ButtonStyle.secondary,
                       custom_id=publish_card.BTN_META, row=0)
    async def _meta(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, compose_meta.run, "subject",
                     started="Subject options posting in #editorial — pick there; description follows.",
                     refresh=publish_card.post_or_update)

    @discord.ui.button(label="Haiku", style=discord.ButtonStyle.secondary,
                       custom_id=publish_card.BTN_HAIKU, row=0)
    async def _haiku(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, compose_haiku.run, "haiku",
                     started="Haiku options posting in #editorial — pick there.",
                     refresh=publish_card.post_or_update)

    @discord.ui.button(label="CTA", style=discord.ButtonStyle.secondary,
                       custom_id=publish_card.BTN_CTA, row=0)
    async def _cta(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, compose_cta.run, "cta",
                     started="CTA framings posting in #supporters — pick there.",
                     refresh=publish_card.post_or_update)

    @discord.ui.button(label="Retry composes", emoji="🔁", style=discord.ButtonStyle.secondary,
                       custom_id=publish_card.BTN_RECOMPOSE, row=0)
    async def _recompose(self, interaction, button):  # type: ignore[no-untyped-def]
        # Re-fires whichever of compose-thesis / compose-echoes failed
        # silently at mark-built. Disabled unless recompose_needed.
        await launch(interaction, publish_card.recompose, "recompose",
                     started="🔁 Re-running compose-thesis / compose-echoes…",
                     refresh=publish_card.post_or_update)

    # ── row 1: ship (gated) ─────────────────────────────────────────────
    @discord.ui.button(label="Email", emoji="🚀", style=discord.ButtonStyle.success,
                       custom_id=publish_card.BTN_EMAIL, row=1)
    async def _email(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, publish_job.publish_buttondown, "publish buttondown",
                     started="📨 Publishing to Buttondown…", refresh=publish_card.post_or_update)

    @discord.ui.button(label="Website", emoji="🚀", style=discord.ButtonStyle.success,
                       custom_id=publish_card.BTN_WEBSITE, row=1)
    async def _website(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, publish_job.publish_website, "publish website",
                     started="🌐 Committing the website archive…", refresh=publish_card.post_or_update)

    @discord.ui.button(label="Podcast", emoji="🚀", style=discord.ButtonStyle.success,
                       custom_id=publish_card.BTN_PODCAST, row=1)
    async def _podcast(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, publish_job.publish_audio, "publish audio",
                     started="🎙️ Rendering audio — progress posts in #editorial.",
                     refresh=publish_card.post_or_update)

    @discord.ui.button(label="Ship all", emoji="🚀", style=discord.ButtonStyle.success,
                       custom_id=publish_card.BTN_ALL, row=1)
    async def _all(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, publish_job.publish_all, "publish all",
                     started="🚀 Shipping all — audio → buttondown → website.",
                     refresh=publish_card.post_or_update)

    # ── row 2: close out ────────────────────────────────────────────────
    @discord.ui.button(label="Put to bed", emoji="🛏️", style=discord.ButtonStyle.secondary,
                       custom_id=publish_card.BTN_BED, row=2)
    async def _bed(self, interaction, button):  # type: ignore[no-untyped-def]
        # put-to-bed closes the window + clears the build/publish cards itself,
        # then the issue moves to Share — refresh the Share card.
        await launch(interaction, put_to_bed.run, "put-to-bed",
                     started="🛏️ Filing the issue and closing the window…",
                     refresh=lambda ctx: share_card.post_or_update(ctx))


def build_view(state: dict) -> "PublishCardView":
    view = PublishCardView()
    gates = (state or {}).get("gates", {})
    for child in view.children:
        cid = getattr(child, "custom_id", None)
        if cid in _GATED:
            child.disabled = not gates.get(cid, False)
    return view
