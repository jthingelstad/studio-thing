"""Scout — producer.

Scout owns the production slate: what's in flight, which stage each
production is in, who needs to act next, what's blocked. The editorial
work (thesis, ordering, tone, fit) stays with Eddy; the research, link
judgement, promotion framing, and supporter fit stay with Linky, Marky,
and Patty respectively. Scout coordinates them around concrete
productions.

This file is Scout's persona shell. Part 1 (additive only) ships
read-only ``/scout status`` and ``/scout slate``. The production-
management migration from Eddy (phase-card lifecycle, ``/eddy issue``
state-transition slash subgroup) ships in a follow-up after WT350
publishes.
"""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_scout_commands


class ScoutBot(PersonaBot):
    persona = "scout"
    name = "Scout"
    home_channel_env = "DISCORD_CHANNEL_PRODUCTION"
    empty_greeting = "Hey — looking at the slate, or asking about a specific production?"
    preferred_model = "sonnet"
    slash_commands_summary = (
        "/scout commands: status · slate"
    )

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_scout_commands(self)
