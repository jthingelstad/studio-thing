"""Eddy — editor.

Eddy hosts the ``/eddy`` slash tree (issue assembly, status,
follow-ups, ad-hoc editorial commands). Each persona owns its own
slash tree; ``PersonaBot.on_ready`` syncs ``self.command_tree`` if
present.
"""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_eddy_commands


class EddyBot(PersonaBot):
    persona = "eddy"
    name = "Eddy"
    home_channel_env = "DISCORD_CHANNEL_EDITORIAL"
    empty_greeting = "Hey — what are we looking at?"
    # Eddy gets the deepest editorial work; default to Opus per README intent.
    preferred_model = "opus"

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_eddy_commands(self)
