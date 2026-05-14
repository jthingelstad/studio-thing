"""``/linky`` slash tree.

Linky owns link curation. ``/linky scan`` manually re-fires the
hourly ``pinboard-scan`` job; ``/linky followup …`` manages Linky's
own commitments. Ad-hoc commands (``/linky research``, ``/linky
pile``, ``/linky stats``) added in commit 6.

Commands populated in commits 3 and 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_linky_commands(bot: "PersonaBot") -> app_commands.CommandTree:
    """Attach the ``/linky`` command tree to Linky's bot. Populated in commit 3."""
    tree = app_commands.CommandTree(bot)
    return tree
