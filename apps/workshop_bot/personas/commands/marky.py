"""``/marky`` slash tree.

Marky owns promotion + campaigns + engagement metrics. ``/marky
{prep,metrics}`` manually re-fire the promotion-prep and daily-metrics
jobs; ``/marky campaign {add,edit,report,copy,sunset}`` manages the
campaign ledger; ``/marky followup …`` manages her own commitments.
Ad-hoc commands (``/marky engagement``, ``/marky referrers``) added
in commit 6.

Commands populated in commits 3 and 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_marky_commands(bot: "PersonaBot") -> app_commands.CommandTree:
    """Attach the ``/marky`` command tree to Marky's bot. Populated in commit 3."""
    tree = app_commands.CommandTree(bot)
    return tree
