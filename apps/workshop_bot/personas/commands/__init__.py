"""Slash-command surface for workshop_bot.

Per-persona trees, each registered on its own Discord bot:

- ``/eddy``  — editor + lead (editorial verbs, status, follow-ups,
  ad-hoc editorial commands)
- ``/linky`` — link curator (scan, follow-ups)
- ``/marky`` — promotion + campaigns + engagement
- ``/patty`` — supporter steward (CTA, goals, follow-ups)
- ``/scout`` — producer (production slate, ops status)

There is no longer a single ``/workshop`` tree — each persona owns its
own commands. Scout owns production state transitions under
``/scout issue …``; Eddy keeps the editorial ``/eddy issue …`` verbs.
"""

from .eddy import register_eddy_commands
from .linky import register_linky_commands
from .marky import register_marky_commands
from .patty import register_patty_commands
from .scout import register_scout_commands

__all__ = [
    "register_eddy_commands",
    "register_linky_commands",
    "register_marky_commands",
    "register_patty_commands",
    "register_scout_commands",
]
