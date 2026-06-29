"""The web app server: an aiohttp app run in the workshop_bot process, bound to loopback and exposed
tailnet-only via `tailscale serve`. Auth = the Tailscale identity header.

Security model: the app binds 127.0.0.1 only, so the ONLY path to it is the Tailscale serve proxy,
which injects `Tailscale-User-Login` for the authenticated tailnet user. A direct request to the
loopback port carries no such header, so requiring it (and matching the allowed login) rejects both
non-tailnet access and any other tailnet user. No tokens, no cookies needed.
"""

from __future__ import annotations

import logging
import os

from aiohttp import web

from .routes import add_routes

log = logging.getLogger("workshop.webapp")

# The header Tailscale `serve` injects for tailnet requests (verified live, 2026-06-28).
IDENTITY_HEADER = "Tailscale-User-Login"

# Typed app key for the bot's deps handle (aiohttp 3.14 wants AppKey, not a str key).
DEPS: web.AppKey = web.AppKey("deps", object)

_runner: web.AppRunner | None = None


def _port() -> int:
    return int(os.environ.get("WORKSHOP_WEBAPP_PORT") or 8770)


def _allowed_login() -> str:
    # The tailnet is just Jamie; default to his login. Empty string = allow any authenticated
    # tailnet user (header present).
    return os.environ.get("TAILSCALE_ALLOWED_LOGIN", "jthingelstad@github")


@web.middleware
async def _identity_mw(request: web.Request, handler):
    if request.path == "/healthz":
        return await handler(request)  # local liveness check, no identity
    login = request.headers.get(IDENTITY_HEADER, "")
    allowed = _allowed_login()
    if not login or (allowed and login != allowed):
        return web.Response(status=403, text="Forbidden — Tailscale identity required.\n")
    return await handler(request)  # routes read the identity from the header (render.py)


async def start_webapp(deps=None) -> None:
    """Start the loopback aiohttp server (idempotent). Call once from the bot's
    run loop. ``deps`` (the bot's corpus/team/registry handle) is stored on the
    app so web handlers can run jobs that post to Discord (the front-door
    behaviour — a web action still announces in #production etc.)."""
    global _runner
    if _runner is not None:
        return
    app = web.Application(middlewares=[_identity_mw])
    app[DEPS] = deps
    add_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", _port())
    await site.start()
    _runner = runner  # module-global keeps it alive
    log.info("workshop webapp on 127.0.0.1:%d (tailnet-only via tailscale serve :8443; allowed=%s)",
             _port(), _allowed_login() or "(any tailnet user)")
