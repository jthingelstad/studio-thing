"""Web app routes. Page one: Scout's production slate, reusing `jobs.scout_slate.snapshot()` (the
same reader behind `/scout slate`). Future pages (blog/podcast drafting) slot in here."""

from __future__ import annotations

import asyncio
import html
import re

from aiohttp import web

from ..jobs import scout_slate
from .render import render

# The slate lines are Discord-flavored markdown; render a safe subset for the web.
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_ITALIC = re.compile(r"(?<![*\w])\*(?!\*)(.+?)(?<!\*)\*(?![*\w])")


def _fmt(line: str) -> str:
    s = html.escape(line)
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _ITALIC.sub(r"<em>\1</em>", s)
    s = _CODE.sub(r"<code>\1</code>", s)
    return s


async def healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok\n")


async def slate_page(request: web.Request) -> web.Response:
    lines, data = await asyncio.to_thread(scout_slate.snapshot)
    rows = [{"html": _fmt(line), "child": line.startswith(("  ", " ")) or "└" in line}
            for line in lines]
    return render("slate.html", request, rows=rows, data=data)


def add_routes(app: web.Application) -> None:
    app.add_routes([
        web.get("/healthz", healthz),
        web.get("/", slate_page),
    ])
