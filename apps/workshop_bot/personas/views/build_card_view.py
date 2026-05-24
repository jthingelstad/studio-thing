"""Persistent button View for the Build card (`#editorial`, registered on Eddy).

Content-author actions + the Mark-built transition. Subject/Description/CTA and
the ship buttons live on the *Publish* card — Build never surfaces them.
"""

from __future__ import annotations

import discord

from ...jobs import build_card, create_final, update_draft
from ._card_base import EditPickerView, is_owner, launch

# Atoms editable from the Build card (the content atoms; haiku + thesis +
# echoes + CTA atoms are Publish concerns).
_BUILD_EDIT_ASSETS = ("intro", "outro", "cover")


class BuildCardView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary,
                       custom_id=build_card.BTN_REFRESH, row=0)
    async def _on_refresh(self, interaction, button):  # type: ignore[no-untyped-def]
        # Don't rename to `_refresh` — that shadows `discord.ui.View._refresh`,
        # the method discord.py calls on MESSAGE_UPDATE; the resolved Button
        # then isn't callable and the gateway poll loop crashes.
        await launch(interaction, update_draft.run, "refresh",
                     started="🔄 Refreshing the draft — the card updates in place.",
                     refresh=build_card.post_or_update)

    @discord.ui.button(label="Reorder", style=discord.ButtonStyle.secondary,
                       custom_id=build_card.BTN_REORDER, row=0)
    async def _reorder(self, interaction, button):  # type: ignore[no-untyped-def]
        await launch(interaction, create_final.run, "reorder",
                     started="Reorder proposal posting in #editorial — react ✅/❌/🔄 there.",
                     refresh=build_card.post_or_update)

    @discord.ui.button(label="Edit…", emoji="✏️", style=discord.ButtonStyle.secondary,
                       custom_id=build_card.BTN_EDIT, row=1)
    async def _edit(self, interaction, button):  # type: ignore[no-untyped-def]
        if not is_owner(interaction):
            await interaction.response.send_message("This is Jamie's console.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Edit which atom?", view=EditPickerView(_BUILD_EDIT_ASSETS), ephemeral=True
        )

    @discord.ui.button(label="Mark built", emoji="✅", style=discord.ButtonStyle.success,
                       custom_id=build_card.BTN_MARK_BUILT, row=2)
    async def _mark_built(self, interaction, button):  # type: ignore[no-untyped-def]
        # mark_built finalizes this card + posts the Publish card itself, so no
        # build-card refresh afterward.
        await launch(interaction, build_card.mark_built, "mark-built",
                     started="✅ Marking built — opening Publish + requesting the CTA from Patty…",
                     refresh=None)


def build_view(state: dict) -> "BuildCardView":
    """A Build view with **Mark built** disabled until the required content is
    present (the three sections + intro + cover + haiku)."""
    view = BuildCardView()
    ready = bool((state or {}).get("build_ready"))
    for child in view.children:
        if getattr(child, "custom_id", None) == build_card.BTN_MARK_BUILT:
            child.disabled = not ready
    return view
