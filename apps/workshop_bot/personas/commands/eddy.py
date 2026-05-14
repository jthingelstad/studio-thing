"""``/eddy`` slash tree.

Eddy is the editor + lead persona. He hosts the issue-assembly artifact
verbs (`/eddy issue start | update | status | final | haiku | subject |
publish`), the cross-cutting bot-health snapshot (`/eddy status`), his
own follow-ups (`/eddy followup …`), and ad-hoc editorial commands
(`/eddy review`, `/eddy archive`).

Commands populated in commits 2 (existing migration) and 5 (new
commands). For now this is a stub so ``commands.__init__`` can import
the register function without raising.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_eddy_commands(bot: "PersonaBot") -> app_commands.CommandTree:
    """Attach the ``/eddy`` command tree to Eddy's bot. Populated in commit 2."""
    tree = app_commands.CommandTree(bot)
    return tree
