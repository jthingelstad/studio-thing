"""Private (tailnet-only) web app for the workshop — Jamie's own operator surface.

Runs in-process inside the workshop_bot process (aiohttp, ships with discord.py), exposed via
`tailscale serve` (NOT funnel) so it's reachable only from Jamie's tailnet devices, never the public
internet. Auth is Tailscale's own identity header — no tokens, no cookies (see server.py). Page one
is the current newsletter issue, or the issue list when nothing is active.
"""

from .server import start_webapp  # noqa: F401

__all__ = ["start_webapp"]
