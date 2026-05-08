"""Marky — promotion."""

from __future__ import annotations

from ..tools import agent_tools
from .base import PersonaBot


class MarkyBot(PersonaBot):
    persona = "marky"
    name = "Marky"
    home_channel_env = "DISCORD_CHANNEL_PROMOTION"
    tools = tuple(agent_tools.UNIVERSAL) + (
        "fetch_tinylytics",
        "fetch_tinylytics_ref",
        "fetch_buttondown_subscribers",
    )
    empty_greeting = "Hey — what are you working on?"
    preferred_model = "sonnet"
