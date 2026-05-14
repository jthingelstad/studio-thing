"""``/patty`` slash tree.

Patty is the supporter steward. ``/patty cta`` runs the per-issue
membership-CTA composer; ``/patty goal {set,done}`` opens and closes
goal milestones; ``/patty followup …`` manages her own commitments.
Ad-hoc commands (``/patty progress``, ``/patty nonprofit``, ``/patty
supporters``) added in commit 6.

Commands populated in commits 3 and 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_patty_commands(bot: "PersonaBot") -> app_commands.CommandTree:
    """Attach the ``/patty`` command tree to Patty's bot. Populated in commit 3."""
    tree = app_commands.CommandTree(bot)
    return tree
