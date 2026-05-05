"""Patty — supporter steward."""

from __future__ import annotations

from ..tools import agent_tools
from .base import PersonaBot


class PattyBot(PersonaBot):
    persona = "patty"
    name = "Patty"
    home_channel_env = "DISCORD_CHANNEL_SUPPORTERS"
    tools = tuple(agent_tools.UNIVERSAL) + ("get_support_state",)
    empty_greeting = "Hey — want me to draft a CTA, or thinking about something else?"
    preferred_model = "sonnet"
