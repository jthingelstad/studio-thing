"""Shared button-View machinery for the per-phase publishing cards.

Each phase card (Build / Publish / Share) is a persistent `discord.ui.View`
whose buttons **launch the existing job** in the background and then refresh
that phase's card — mirroring the slash tree's interactive-job pattern so a
long job never holds the 15-min interaction token. This module holds the
owner-guard, the launch-and-refresh plumbing, and the small ephemeral
edit-asset picker; the per-card view modules only declare their buttons.
"""

from __future__ import annotations

import asyncio
import logging
import os

import discord

from ...jobs import _base as jobs_base
from ...jobs import edit_asset

logger = logging.getLogger("workshop.views.cards")

# Hold strong refs to in-flight background tasks so the loop doesn't GC them.
_BG_TASKS: set[asyncio.Task] = set()


def is_owner(interaction) -> bool:
    """True if the clicker is Jamie (or no owner configured — dev)."""
    owner = (os.environ.get("DISCORD_OWNER_USER_ID") or "").strip()
    if not owner:
        return True
    return str(getattr(getattr(interaction, "user", None), "id", "")) == owner


def ctx_from(interaction) -> "jobs_base.JobContext":
    return jobs_base.JobContext(deps=getattr(interaction.client, "deps", None), trigger="card")


async def _run_and_refresh(client, coro_factory, label: str, refresh) -> None:
    """Run a job to completion in the background, then refresh the card.
    Failures are logged, not raised — the card still refreshes so the operator
    sees the new state. ``refresh`` is an async fn taking ``ctx`` (or None)."""
    ctx = jobs_base.JobContext(deps=getattr(client, "deps", None), trigger="card")
    try:
        await coro_factory(ctx)
    except jobs_base.JobLocked as exc:
        logger.info("cards: %s already running — %s", label, exc.holder_desc)
    except Exception:  # noqa: BLE001
        logger.exception("cards: %s failed", label)
    if refresh is not None:
        try:
            await refresh(ctx)
        except Exception:  # noqa: BLE001
            logger.exception("cards: refresh after %s failed", label)


async def launch(interaction, coro_factory, label: str, *, started: str, refresh=None) -> None:
    """Owner-guard, ack the click immediately, then run the job + refresh the
    card in the background."""
    if not is_owner(interaction):
        try:
            await interaction.response.send_message("This is Jamie's console.", ephemeral=True)
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        await interaction.response.send_message(started, ephemeral=True)
    except Exception:  # noqa: BLE001
        logger.exception("cards: couldn't ack %s click", label)
    task = asyncio.create_task(_run_and_refresh(interaction.client, coro_factory, label, refresh))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


class EditPickerView(discord.ui.View):
    """Transient ephemeral picker: one button per editable atom; clicking pops
    the existing edit-asset modal. Not persistent (short timeout) — it only
    lives for the few seconds between the Edit click and the pick."""

    def __init__(self, assets) -> None:
        super().__init__(timeout=180)
        for asset in assets:
            if asset not in edit_asset.ASSET_CHOICES:
                continue
            btn = discord.ui.Button(
                label=asset, style=discord.ButtonStyle.secondary, custom_id=f"cardedit:{asset}"
            )
            btn.callback = self._make_cb(asset)
            self.add_item(btn)

    def _make_cb(self, asset: str):
        async def _cb(interaction) -> None:
            if not is_owner(interaction):
                await interaction.response.send_message("Jamie only.", ephemeral=True)
                return
            modal, err = edit_asset.build_modal(ctx_from(interaction), asset_key=asset)
            if modal is None:
                await interaction.response.send_message(err or "❌ couldn't open the editor.", ephemeral=True)
                return
            await interaction.response.send_modal(modal)

        return _cb
