"""Runtime bot registry.

The name is kept for compatibility with existing imports, but Studio now
registers only Eddy. The registry gives local tools such as ``react__add`` a
safe way to find the active Discord client for the current persona.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import PersonaBot


class TeamRegistry:
    def __init__(self) -> None:
        self.bots: dict[str, "PersonaBot"] = {}

    def register(self, bot: "PersonaBot") -> None:
        self.bots[bot.persona] = bot
