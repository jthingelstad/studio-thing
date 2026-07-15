"""Eddy — the active Studio assistant."""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_eddy_commands


class EddyBot(PersonaBot):
    persona = "eddy"
    name = "Eddy"
    home_channel_env = "DISCORD_CHANNEL_EDITORIAL"
    empty_greeting = "Hey — what are we looking at?"
    # Sonnet is the default for all of Eddy's general work — mentions,
    # reorder, composition (envelope: subject/haiku/description; echoes),
    # follow-ups. Two editorial-review surfaces override up to Opus:
    # ``eddy-review`` (the on-demand editorial pass) and ``review-text``
    # (``/eddy review <text>``). See each job's
    # ``bot.core(..., model="opus")`` callsite.
    preferred_model = "sonnet"
    slash_commands_summary = (
        "/eddy commands: issue {echoes,reorder,haiku,subject} · edit · currently · "
        "status · review · archive · followup"
    )

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_eddy_commands(self)

    # The Studio web app owns long-lived issue controls. Eddy only hosts
    # narrow chat helpers, so it inherits the base empty persistent_views.
