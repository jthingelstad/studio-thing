"""Slash-command surface for workshop_bot.

Per-persona trees:
- ``/eddy`` — editor + lead (issue assembly verbs, bot-health, ad-hoc review)
- ``/linky`` — link curator (scan, research, pile, stats)
- ``/marky`` — promotion + campaigns + engagement
- ``/patty`` — supporter steward (CTA, goals, donations)

Each persona owns its own tree, registered on its own Discord bot. The
old single ``/workshop …`` tree (hosted on Eddy) is currently still
registered alongside the per-persona trees during the migration; it
gets removed in commit 4.

Re-exports:
- ``register_workshop_commands`` — the legacy single-tree register
  (delegates to :mod:`.workshop`). Removed in commit 4.
- ``register_<persona>_commands`` — the four per-persona register fns.
"""

from .workshop import register_workshop_commands
from .eddy import register_eddy_commands
from .linky import register_linky_commands
from .marky import register_marky_commands
from .patty import register_patty_commands

__all__ = [
    "register_workshop_commands",
    "register_eddy_commands",
    "register_linky_commands",
    "register_marky_commands",
    "register_patty_commands",
]
