"""Marky — promotion."""

from __future__ import annotations

from .base import PersonaBot


class MarkyBot(PersonaBot):
    persona = "marky"
    name = "Marky"
    home_channel_env = "DISCORD_CHANNEL_PROMOTION"
    empty_greeting = "Hey — what are you working on?"
    preferred_model = "sonnet"
