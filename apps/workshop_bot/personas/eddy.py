"""Eddy — editor.

Eddy hosts the ``/eddy`` slash tree (issue assembly, status,
follow-ups) and — during the migration in commits 1–3 — also hosts the
legacy ``/workshop`` tree alongside. Both register on the same
``CommandTree`` because slash commands are per Discord application
token and Eddy's bot owns this one. The legacy tree is removed in
commit 4.
"""

from __future__ import annotations

import logging
import os

import discord

from .base import Deps, PersonaBot
from .commands import register_eddy_commands, register_workshop_commands

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
        # /workshop and /eddy on the same tree during the migration.
        # Commit 4 removes register_workshop_commands.
        self.command_tree = register_workshop_commands(self)
        register_eddy_commands(self, tree=self.command_tree)

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
