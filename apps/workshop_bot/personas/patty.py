"""Patty — supporter steward."""

from __future__ import annotations

from .base import PersonaBot


class PattyBot(PersonaBot):
    persona = "patty"
    name = "Patty"
    home_channel_env = "DISCORD_CHANNEL_SUPPORTERS"
    empty_greeting = "Hey — want me to draft a CTA, or thinking about something else?"
    preferred_model = "sonnet"
