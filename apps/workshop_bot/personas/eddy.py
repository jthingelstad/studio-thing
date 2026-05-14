"""Eddy — editor.

Eddy hosts the ``/eddy`` slash tree (issue assembly, status,
follow-ups). During the migration in commits 1–3 he also hosts the
legacy ``/workshop`` tree alongside — both groups live on the same
``CommandTree``. The legacy tree is removed in commit 4. The base
class :class:`PersonaBot` syncs the tree on ``on_ready``.
"""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_eddy_commands, register_workshop_commands


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
