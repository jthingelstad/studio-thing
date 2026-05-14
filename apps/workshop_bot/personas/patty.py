"""Patty — supporter steward."""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_patty_commands


class PattyBot(PersonaBot):
    persona = "patty"
    name = "Patty"
    home_channel_env = "DISCORD_CHANNEL_SUPPORTERS"
    empty_greeting = "Hey — want me to draft a CTA, or thinking about something else?"
    preferred_model = "sonnet"
    slash_commands_summary = (
        "/patty commands: cta · goal {set,done} · progress · nonprofit · supporters · followup"
    )

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_patty_commands(self)
