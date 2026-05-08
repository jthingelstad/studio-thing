"""Linky — Pinboard curation."""

from __future__ import annotations

from .base import PersonaBot


class LinkyBot(PersonaBot):
    persona = "linky"
    name = "Linky"
    home_channel_env = "DISCORD_CHANNEL_RESEARCH"
    empty_greeting = "Hey — want a curation pass, or asking about a specific link?"
    preferred_model = "sonnet"
