"""Slash-command surface for workshop_bot.

Per-persona trees, each registered on its own Discord bot:

- ``/eddy``  — editor + lead (issue assembly verbs, status, follow-ups,
  ad-hoc editorial commands)
- ``/linky`` — link curator (scan, follow-ups)
- ``/marky`` — promotion + campaigns + engagement
- ``/patty`` — supporter steward (CTA, goals, follow-ups)

There is no longer a single ``/workshop`` tree — each persona owns its
own commands. Eddy still carries cross-cutting verbs (``/eddy status``,
the ``/eddy issue …`` artifact subgroup) as the lead persona.
"""

from .eddy import register_eddy_commands
from .linky import register_linky_commands
from .marky import register_marky_commands
from .patty import register_patty_commands

__all__ = [
    "register_eddy_commands",
    "register_linky_commands",
    "register_marky_commands",
    "register_patty_commands",
]
