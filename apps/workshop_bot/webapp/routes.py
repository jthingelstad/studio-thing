"""Web app routes.

- ``/``                       Scout's production slate (read-only, reuses
                             ``jobs.scout_slate.snapshot()``).
- ``/productions``           the productions registry — add / edit projects of
                             any type (the shared working space's first CRUD).

Forms POST to handlers that route through the same ``db`` helpers + jobs the
Discord surface uses, so the web app and the agents edit the same rows. Identity
is guaranteed by the server middleware; writes additionally require a same-origin
POST (the only residual CSRF vector behind the tailnet + Tailscale-identity gate).
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re

from aiohttp import web

from ..jobs import (
    _base, production_ops, production_state, publish, put_to_bed, scout_slate, start_issue,
)
from ..tools import content_store, db, issue_items, s3
from ..tools.content import production_types as ptypes
from . import server
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


def _login(request: web.Request) -> str:
    """The signed-in Tailscale login (guaranteed present by the middleware)."""
    return request.headers.get(server.IDENTITY_HEADER, "")


def _same_origin(request: web.Request) -> bool:
    """Reject cross-origin POSTs. There's no cookie/session to anchor a CSRF
    token on (the gate is the tailnet + identity header), so an Origin/Referer
    allowlist closes the one residual vector at near-zero cost. A same-origin
    form post (or a non-browser client) typically omits Origin → allowed."""
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if not origin:
        return True
    return origin.startswith(f"https://{request.host}") or origin.startswith(
        f"http://{request.host}"
    )


# ---------- the slate (page one, unchanged) ----------


async def healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok\n")


async def slate_page(request: web.Request) -> web.Response:
    lines, data = await asyncio.to_thread(scout_slate.snapshot)
    rows = [{"html": _fmt(line), "child": line.startswith(("  ", " ")) or "└" in line}
            for line in lines]
    return render("slate.html", request, rows=rows, data=data)


# ---------- productions registry (add / edit) ----------

# Ordered (key, label) for the type selector / list grouping.
_TYPE_ORDER = ("newsletter", "article", "podcast", "project")
_PHASES_JSON = json.dumps({k: list(ptypes.phases_for(k)) for k in _TYPE_ORDER})


def _details_from_form(data) -> dict:
    """Collect per-type detail fields (any ``detail_*`` input) into a dict."""
    out = {}
    for key, val in data.items():
        if key.startswith("detail_") and isinstance(val, str) and val.strip():
            out[key[len("detail_"):]] = val.strip()
    return out


async def productions_list(request: web.Request) -> web.Response:
    # The working space shows in-flight productions by default; the shipped
    # archive (every put-to-bed newsletter, backfilled) is tucked behind ?all=1
    # so the page doesn't drown in 14 years of done issues.
    show_all = request.query.get("all") == "1"
    rows = await asyncio.to_thread(db.list_productions, limit=2000)
    groups = []
    for key in _TYPE_ORDER:
        pt = ptypes.PRODUCTION_TYPES[key]
        items = [r for r in rows if r["production_type"] == key]
        active = [r for r in items if r["status"] == "active"]
        shipped = len(items) - len(active)
        groups.append({
            "key": key, "label": pt.label, "surface": pt.surface,
            "rows": items if show_all else active, "shipped": shipped,
        })
    return render("productions.html", request, groups=groups, show_all=show_all)


def _render_form(request, *, mode, row=None, error=None, status=200):
    types = [(k, ptypes.PRODUCTION_TYPES[k].label) for k in _TYPE_ORDER]
    return render(
        "production_form.html", request,
        status=status, mode=mode, row=row, error=error,
        types=types, phases_json=_PHASES_JSON,
    )


async def production_new_form(request: web.Request) -> web.Response:
    return _render_form(request, mode="new")


async def production_edit_form(request: web.Request) -> web.Response:
    pid = request.match_info["pid"]
    row = await asyncio.to_thread(db.get_production, pid)
    if not row:
        raise web.HTTPNotFound(text=f"no such production: {pid}")
    return _render_form(request, mode="edit", row=row)


async def production_create(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    data = await request.post()
    login = _login(request)
    ptype = data.get("production_type", "")
    title = (data.get("title") or "").strip()
    if ptype not in ptypes.PRODUCTION_TYPES:
        return _render_form(request, mode="new", error="Unknown production type.", status=400)
    if not title:
        return _render_form(request, mode="new", error="Title is required.", status=400)

    if ptype == "newsletter":
        # Define the newsletter as *planned* — a DB row only, no workspace.
        # "Start working" (on the project page) seeds the pipeline later.
        try:
            seq = int(data.get("seq") or 0)
        except (TypeError, ValueError):
            return _render_form(request, mode="new", error="Issue number must be an integer.", status=400)
        pub_date = (data.get("pub_date") or "").strip()
        day_count = int(data.get("day_count") or 7)
        ctx = _base.JobContext(deps=request.app.get(server.DEPS), trigger="web")
        res = await start_issue.define(ctx, number=seq, pub_date=pub_date,
                                       day_count=day_count, set_by=login or "web")
        if not res.ok:
            return _render_form(request, mode="new", error=res.message, status=400)
        raise web.HTTPFound(f"/productions/WT{seq}")

    phase = data.get("phase") or ptypes.default_phase(ptype)
    if not ptypes.is_valid_phase(ptype, phase):
        return _render_form(request, mode="new", error=f"Invalid phase for {ptype}.", status=400)
    seq_raw = data.get("seq")
    seq = int(seq_raw) if seq_raw else None
    row = await asyncio.to_thread(
        db.create_production,
        production_type=ptype, title=title, seq=seq, phase=phase,
        due_at=(data.get("due_at") or None),
        details=(_details_from_form(data) or None),
        created_by=login,
    )
    raise web.HTTPFound(f"/productions/{row['id']}/edit")


async def production_update(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    pid = request.match_info["pid"]
    data = await request.post()
    login = _login(request)
    row = await asyncio.to_thread(db.get_production, pid)
    if not row:
        raise web.HTTPNotFound(text=f"no such production: {pid}")
    ptype = row["production_type"]
    title = (data.get("title") or "").strip() or None
    phase = data.get("phase") or None

    try:
        if ptype == "newsletter":
            # Phase changes go through the window (set_issue_phase mirrors the
            # registry); the live publish state stays authoritative in issue_windows.
            if phase and phase != row["phase"]:
                await asyncio.to_thread(db.set_issue_phase, int(row["seq"]), phase)
            await asyncio.to_thread(db.update_production, pid, title=title, updated_by=login)
        else:
            if phase and phase != row["phase"]:
                await asyncio.to_thread(db.set_production_phase, pid, phase, updated_by=login)
            await asyncio.to_thread(
                db.update_production, pid,
                title=title,
                due_at=(data.get("due_at") or None),
                status=(data.get("status") or None),
                details=(_details_from_form(data) or None),
                updated_by=login,
            )
    except ValueError as exc:
        return _render_form(request, mode="edit", row=row, error=str(exc), status=400)
    raise web.HTTPFound("/productions")


# ---------- the production page (the work surface) ----------

# Newsletter authored content blocks editable on the page (name, label).
_NEWSLETTER_BLOCKS = [
    ("intro.md", "Intro"), ("outro.md", "Outro"), ("haiku.md", "Haiku"),
    ("thesis.md", "Thesis"), ("echoes.md", "Echoes"),
    ("cta-1.md", "CTA · slot 1"), ("cta-2.md", "CTA · slot 2"), ("thanks-1.md", "Thanks"),
]
# Saving these re-fires update-draft so the rendered draft refreshes.
_REFIRE = {"intro.md", "outro.md", "haiku.md", "cover.json"}
# Authored content blocks for the non-newsletter types.
_GENERIC_BLOCKS = {
    "article": [("body.md", "Body")],
    "podcast": [("script.md", "Script"), ("notes.md", "Show notes")],
    "project": [("notes.md", "Notes")],
}


def _ctx(request):
    return _base.JobContext(deps=request.app.get(server.DEPS), trigger="web")


def _json_content(get_value: str) -> dict:
    try:
        return json.loads(get_value) if (get_value or "").strip() else {}
    except (ValueError, TypeError):
        return {}


def _newsletter_page_data(row) -> dict:
    n = int(row["seq"])
    phase = row["phase"]
    state = (production_state.publish_state(n) if phase in ("publish", "share")
             else production_state.build_state(n))
    blocks = [{"name": name, "label": label, "value": content_store.read_issue(n, name) or ""}
              for name, label in _NEWSLETTER_BLOCKS]
    return {
        "row": row, "ptype": "newsletter", "n": n, "phase": phase, "state": state,
        "blocks": blocks,
        "cover": _json_content(content_store.read_issue(n, "cover.json") or ""),
        "meta": _json_content(content_store.read_issue(n, "metadata.json") or ""),
        "currently": db.currently_get_entries(n),
        "currently_types": [t["label"] for t in db.currently_list_types()],
        "comments": issue_items.list_open_comments(n),
        "review_url": s3.issue_file_url(n, "draft.html"),
        "phases": list(ptypes.phases_for("newsletter")),
    }


def _generic_page_data(row) -> dict:
    pid = row["id"]
    blocks = [{"name": name, "label": label, "value": content_store.get(pid, name) or ""}
              for name, label in _GENERIC_BLOCKS.get(row["production_type"], [])]
    return {
        "row": row, "ptype": row["production_type"], "phase": row["phase"], "blocks": blocks,
        "phases": list(ptypes.phases_for(row["production_type"])),
    }


async def production_page(request: web.Request) -> web.Response:
    pid = request.match_info["pid"]
    row = await asyncio.to_thread(db.get_production, pid)
    if not row:
        raise web.HTTPNotFound(text=f"no such production: {pid}")
    builder = _newsletter_page_data if row["production_type"] == "newsletter" else _generic_page_data
    data = await asyncio.to_thread(builder, row)
    return render("production.html", request, **data)


async def _load_row(request):
    row = await asyncio.to_thread(db.get_production, request.match_info["pid"])
    if not row:
        raise web.HTTPNotFound(text=f"no such production: {request.match_info['pid']}")
    return row


async def production_start(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    if row["production_type"] != "newsletter":
        raise web.HTTPBadRequest(text="only newsletters have a workspace")
    await start_issue.start_working(_ctx(request), int(row["seq"]), set_by=_login(request))
    raise web.HTTPFound(f"/productions/{row['id']}")


async def production_atom_save(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    data = await request.post()
    name = (data.get("name") or "").strip()
    if not name:
        raise web.HTTPBadRequest(text="missing name")
    value = data.get("value") or ""
    await asyncio.to_thread(content_store.set, row["id"], name, value, by=f"web:{_login(request)}")
    if row["production_type"] == "newsletter" and name in _REFIRE:
        _base.schedule_update_draft_refire(_ctx(request), int(row["seq"]))
    raise web.HTTPFound(f"/productions/{row['id']}")


async def production_cover_save(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    if row["production_type"] != "newsletter":
        raise web.HTTPBadRequest(text="not a newsletter")
    data = await request.post()
    cover = {k: (data.get(k) or "").strip() for k in ("caption", "location", "timestamp", "alt")}
    await asyncio.to_thread(content_store.set, row["id"], "cover.json",
                            json.dumps(cover, indent=2), by=f"web:{_login(request)}")
    _base.schedule_update_draft_refire(_ctx(request), int(row["seq"]))
    raise web.HTTPFound(f"/productions/{row['id']}")


async def production_meta_save(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    if row["production_type"] != "newsletter":
        raise web.HTTPBadRequest(text="not a newsletter")
    data = await request.post()
    n = int(row["seq"])
    login = _login(request)

    def _save():
        meta = _json_content(content_store.read_issue(n, "metadata.json") or "")
        meta["subject"] = (data.get("subject") or "").strip()
        meta["description"] = (data.get("description") or "").strip()
        content_store.write_issue(n, "metadata.json", json.dumps(meta, indent=2), by=f"web:{login}")

    await asyncio.to_thread(_save)
    raise web.HTTPFound(f"/productions/{row['id']}")


async def production_currently(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    if row["production_type"] != "newsletter":
        raise web.HTTPBadRequest(text="not a newsletter")
    n = int(row["seq"])
    data = await request.post()
    op = data.get("op", "set")
    try:
        if op == "clear":
            await asyncio.to_thread(db.currently_clear_entry, n, data.get("label", ""))
        else:
            await asyncio.to_thread(db.currently_set_entry, n,
                                    data.get("label", ""), data.get("value", ""))
    except Exception:  # noqa: BLE001 — CurrentlyError etc; redirect back regardless
        logging.getLogger("workshop.webapp").warning("currently op failed for %s", row["id"])
    raise web.HTTPFound(f"/productions/{row['id']}")


async def production_phase(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    data = await request.post()
    target = (data.get("phase") or "").strip()
    ctx = _ctx(request)
    try:
        if row["production_type"] == "newsletter":
            n, cur = int(row["seq"]), row["phase"]
            if target == "publish" and cur == "build":
                await production_ops.mark_built(ctx, n)
            elif target == "build" and cur == "publish":
                await production_ops.reopen(ctx, n)
            elif target == "build" and cur in ("planned", "write"):
                await start_issue.start_working(ctx, n, set_by=_login(request))
            else:
                await asyncio.to_thread(db.set_issue_phase, n, target)
        else:
            await asyncio.to_thread(db.set_production_phase, row["id"], target,
                                    updated_by=_login(request))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    raise web.HTTPFound(f"/productions/{row['id']}")


async def production_publish(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    row = await _load_row(request)
    if row["production_type"] != "newsletter":
        raise web.HTTPBadRequest(text="not a newsletter")
    data = await request.post()
    leg = data.get("leg", "")
    ctx = _ctx(request)
    legs = {
        "email": publish.publish_buttondown,
        "website": publish.publish_website,
        "podcast": publish.publish_audio,
        "all": publish.publish_all,
    }
    if leg == "bed":
        await put_to_bed.run(ctx)
    elif leg in legs:
        await legs[leg](ctx)
    raise web.HTTPFound(f"/productions/{row['id']}")


# ---------- the seeds garden ----------

async def seeds_page(request: web.Request) -> web.Response:
    clusters, ungrouped = await asyncio.to_thread(_seeds_garden_data)
    return render("seeds.html", request, clusters=clusters, ungrouped=ungrouped)


def _seeds_garden_data():
    clusters = []
    for c in db.seed_cluster_list(status="open"):
        full = db.seed_cluster_get(c["id"])
        clusters.append(full)
    ungrouped = [s for s in db.seed_list(status="open") if s.get("cluster_id") is None]
    return clusters, ungrouped


async def seeds_add(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    data = await request.post()
    body = (data.get("body") or "").strip()
    if body:
        title = (data.get("title") or "").strip() or None
        await asyncio.to_thread(db.seed_add, body, title=title, source="web",
                                created_by=_login(request))
    raise web.HTTPFound("/seeds")


async def seeds_graduate(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    data = await request.post()
    cluster_id = data.get("cluster_id")
    ptype = data.get("production_type", "article")
    title = (data.get("title") or "").strip()
    if cluster_id and title:
        from ..tools.llm import local_tools
        await asyncio.to_thread(local_tools.t_seeds_graduate, None, ptype, title,
                                int(cluster_id))
    raise web.HTTPFound("/seeds")


# ---------- in-web chat (work with the agents on one screen) ----------

_CHAT_TASKS: set = set()
_CHAT_PERSONAS = ("eddy", "scout", "linky", "marky", "patty")


def _chat_context_block(context_key: str) -> str:
    """Tell the agent what it's working on, injected ahead of Jamie's message."""
    if context_key == "seeds":
        clusters = db.seed_cluster_list(status="open")
        loose = [s for s in db.seed_list(status="open") if s.get("cluster_id") is None]
        return (f"## Context — Jamie's seeds garden\nYou're tending the idea garden: "
                f"{len(loose)} unclustered seeds, {len(clusters)} clusters. Use the seeds__* "
                f"tools to curate / cluster / connect to his archive / route to a type. "
                f"Remember: Jamie writes the prose; you develop the ideas.")
    row = db.get_production(context_key)
    if not row:
        return ""
    names = content_store.list(row["id"])
    return (f"## Context — production {row['id']} ({row['production_type']}, "
            f"phase {row['phase']})\nTitle: {row['title']}. Content blocks: "
            f"{', '.join(names) or '(none yet)'}. Use production_content__* / tasks__* to "
            f"work it. Jamie writes the prose; you develop, research, structure, and edit.")


async def _run_agent_chat(app, context_key: str, persona: str, message: str, prior: list) -> None:
    log = logging.getLogger("workshop.webapp.chat")
    try:
        deps = app.get(server.DEPS)
        team = getattr(deps, "team", None) if deps is not None else None
        bots = getattr(team, "bots", None) if team is not None else None
        bot = bots.get(persona) if isinstance(bots, dict) else (bots.get(persona) if bots else None)
        if bot is None:
            await asyncio.to_thread(
                db.chat_add, context_key, "assistant",
                "_(the agents aren't reachable from the web app right now — talk to them in Discord)_",
                persona=persona)
            return
        ctx_block = await asyncio.to_thread(_chat_context_block, context_key)
        history = [{"role": m["role"], "content": m["content"]} for m in prior]
        latest = f"{ctx_block}\n\n{message}" if ctx_block else message
        reply, _meta = await bot.core(latest=latest, history=history)
        await asyncio.to_thread(db.chat_add, context_key, "assistant",
                                reply or "_(no reply)_", persona=persona)
    except Exception as exc:  # noqa: BLE001
        log.exception("chat agent run failed for %s/%s", context_key, persona)
        await asyncio.to_thread(db.chat_add, context_key, "assistant",
                                f"_(error running {persona}: {type(exc).__name__})_", persona=persona)


async def chat_post(request: web.Request) -> web.Response:
    if not _same_origin(request):
        raise web.HTTPForbidden(text="bad origin")
    data = await request.post()
    context_key = (data.get("context_key") or "").strip()
    message = (data.get("message") or "").strip()
    persona = (data.get("persona") or "eddy").strip().lower()
    if not context_key or not message:
        raise web.HTTPBadRequest(text="missing context_key or message")
    # A leading @persona overrides the picker.
    if message.startswith("@"):
        head, _, rest = message[1:].partition(" ")
        if head.lower() in _CHAT_PERSONAS:
            persona, message = head.lower(), rest.strip() or message
    if persona not in _CHAT_PERSONAS:
        persona = "eddy"
    prior = await asyncio.to_thread(db.chat_list, context_key)
    await asyncio.to_thread(db.chat_add, context_key, "user", message)
    task = asyncio.create_task(_run_agent_chat(request.app, context_key, persona, message, prior))
    _CHAT_TASKS.add(task)
    task.add_done_callback(_CHAT_TASKS.discard)
    return web.json_response({"ok": True, "persona": persona})


async def chat_get(request: web.Request) -> web.Response:
    context_key = request.query.get("context_key", "")
    since = int(request.query.get("since") or 0)
    msgs = await asyncio.to_thread(db.chat_list, context_key, since_id=since)
    return web.json_response({"messages": msgs})


def add_routes(app: web.Application) -> None:
    app.add_routes([
        web.get("/healthz", healthz),
        web.get("/", slate_page),
        web.get("/chat", chat_get),
        web.post("/chat", chat_post),
        web.get("/seeds", seeds_page),
        web.post("/seeds/add", seeds_add),
        web.post("/seeds/graduate", seeds_graduate),
        web.get("/productions", productions_list),
        web.get("/productions/new", production_new_form),
        web.post("/productions/new", production_create),
        web.get("/productions/{pid}", production_page),
        web.get("/productions/{pid}/edit", production_edit_form),
        web.post("/productions/{pid}/edit", production_update),
        web.post("/productions/{pid}/start", production_start),
        web.post("/productions/{pid}/atom", production_atom_save),
        web.post("/productions/{pid}/cover", production_cover_save),
        web.post("/productions/{pid}/meta", production_meta_save),
        web.post("/productions/{pid}/currently", production_currently),
        web.post("/productions/{pid}/phase", production_phase),
        web.post("/productions/{pid}/publish", production_publish),
    ])
