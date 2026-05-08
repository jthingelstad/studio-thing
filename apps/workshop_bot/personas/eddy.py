"""Eddy — editor.

Eddy also hosts the ``/workshop`` slash-command surface. Slash commands
are per Discord application token, so we register on exactly one bot
rather than fanning out to all four. See ``personas/commands.py``.
"""

from __future__ import annotations

import logging
import os

import discord

from .base import Deps, PersonaBot
from .commands import register_workshop_commands

logger = logging.getLogger("workshop.eddy")


class EddyBot(PersonaBot):
    persona = "eddy"
    name = "Eddy"
    home_channel_env = "DISCORD_CHANNEL_EDITORIAL"
    empty_greeting = "Hey — what are we looking at?"
    # Eddy gets the deepest editorial work; default to Opus per README intent.
    preferred_model = "opus"

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_workshop_commands(self)

    async def on_ready(self) -> None:  # type: ignore[override]
        await super().on_ready()
        guild_id = (os.environ.get("DISCORD_SERVER_ID") or "").strip()
        try:
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                # Copy global commands into the guild and sync there for
                # instant availability — guild-scoped sync skips Discord's
                # ~1h global propagation.
                self.command_tree.copy_global_to(guild=guild)
                synced = await self.command_tree.sync(guild=guild)
            else:
                synced = await self.command_tree.sync()
            logger.info(
                "eddy: command tree synced (%d command(s)%s)",
                len(synced),
                f", guild={guild_id}" if guild_id else "",
            )
        except Exception:  # noqa: BLE001
            logger.exception("eddy: command tree sync failed")
