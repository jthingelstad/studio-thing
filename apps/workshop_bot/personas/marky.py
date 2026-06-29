"""Marky — promotion."""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_marky_commands


class MarkyBot(PersonaBot):
    persona = "marky"
    name = "Marky"
    home_channel_env = "DISCORD_CHANNEL_PROMOTION"
    empty_greeting = "Hey — what are you working on?"
    preferred_model = "sonnet"
    slash_commands_summary = (
        "/marky commands: prep · metrics · engagement · referrers · "
        "campaign {add,edit,report,copy,sunset} · followup"
    )

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_marky_commands(self)
        # No persistent views — the Share card was retired. Inherits the base
        # (empty) persistent_views.
