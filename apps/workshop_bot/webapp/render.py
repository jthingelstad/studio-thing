"""Jinja2 rendering for the web app. Templates live in templates/; autoescape on. `render(...)`
injects the common context (the signed-in Tailscale login) so routes pass only page-specific data."""

from __future__ import annotations

from pathlib import Path

import jinja2
from aiohttp import web

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template: str, request: web.Request, *, status: int = 200, **ctx) -> web.Response:
    # The identity is validated by the server middleware; read it back off the Tailscale header.
    ctx.setdefault("login", request.headers.get("Tailscale-User-Login", ""))
    body = _env.get_template(template).render(**ctx)
    return web.Response(text=body, content_type="text/html", status=status)
