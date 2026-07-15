"""Slash-command surface for Eddy.

Studio now runs one assistant. ``/eddy`` keeps the ad-hoc and repair
commands; normal issue work happens in the web app.
"""

from .eddy import register_eddy_commands

__all__ = [
    "register_eddy_commands",
]
