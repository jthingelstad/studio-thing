"""Eddy — editor."""

from __future__ import annotations

from ..tools import agent_tools
from .base import PersonaBot


class EddyBot(PersonaBot):
    persona = "eddy"
    name = "Eddy"
    home_channel_env = "DISCORD_CHANNEL_EDITORIAL"
    tools = tuple(agent_tools.UNIVERSAL)
    empty_greeting = "Hey — what are we looking at?"
    # Eddy gets the deepest editorial work; default to Opus per README intent.
    preferred_model = "opus"
