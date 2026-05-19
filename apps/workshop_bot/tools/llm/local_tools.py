"""Local-helper tools for the workshop-bot agent loop.

Each tool is a Python function plus an Anthropic JSON schema. The loop
dispatches by name. Functions take (deps, **kwargs) and return JSON-
serializable data; serialization happens in the loop.

Capped string lengths keep tool results from blowing the context window.
A single tool result over ~50KB will be truncated when serialized.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from .. import db, issue_items as issue_items_mod, s3, support_state, web
from ..content import archive, draft, issue
from .tool_registry import ToolRegistry, active_persona, active_react_target

logger = logging.getLogger("workshop.tools")

REPO = Path(__file__).resolve().parents[3]
SECTION_RE_TEMPLATE = r"(?im)^##+\s*{section}\s*[^\n]*\n([\s\S]*?)(?=^##+\s|\Z)"
TEXT_PREVIEW_CHARS = 1500
ISSUE_BODY_CAP = 24_000


# ---------- archive tools ----------

def t_search_archive(deps, query: str, k: int = 8) -> list[dict[str, Any]]:
    """BM25 search over archive chunks. Cheap. Use first to find what's relevant."""
    chunks = deps.corpus.search(query, k=int(k))
    return [
        {
            "issue": c.get("issue_number"),
            "date": (c.get("publish_date") or "")[:10],
            "subject": c.get("subject"),
            "section": c.get("section") or "Issue",
            "text": (c.get("text") or "")[:TEXT_PREVIEW_CHARS].strip(),
        }
        for c in chunks
    ]


def t_retrieve_archive(deps, query: str, k: int = 8) -> list[dict[str, Any]] | dict[str, Any]:
    """Semantic archive retrieval via Thingy's /retrieve (Bedrock Cohere
    embed → vector search → Cohere rerank). Returns the same shape as
    ``archive__search`` so callers can swap freely. Use this for THEME
    / CONCEPT lookups ("end-to-end messaging"); use ``archive__search``
    for VOCABULARY-PRESERVING lookups (a person's name, a product name,
    a specific phrase). Falls back to an error dict on retrieval failure
    so the model can recover (e.g. retry with ``archive__search``)
    rather than crashing the turn."""
    # Local import — keeps the heavyweight tool dependency tree out of
    # the top-of-module surface and matches how compose_closer imports it.
    from .. import thingy_retrieve

    try:
        passages = thingy_retrieve.retrieve(query, k=int(k))
    except thingy_retrieve.ThingyRetrieveError as exc:
        return {
            "error": f"semantic retrieval unavailable: {exc}",
            "hint": "fall back to archive__search for the same query",
        }
    return [
        {
            "issue": p.get("issue_number"),
            "date": (p.get("publish_date") or "")[:10],
            "subject": p.get("subject"),
            "section": p.get("section") or "Issue",
            "text": (p.get("text") or "")[:TEXT_PREVIEW_CHARS].strip(),
            "score": p.get("score"),
        }
        for p in passages
    ]


def t_get_issue(deps, number: int | str) -> dict[str, Any] | str:
    """Full body of one issue."""
    try:
        n = int(str(number).split("-", 1)[0])
    except ValueError:
        return f"could not parse issue number from {number!r}"
    issue = archive.read_issue(n)
    if issue is None:
        return f"no archive file for #{n}"
    fm = issue.get("frontmatter") or {}
    body = (issue.get("body") or "")[:ISSUE_BODY_CAP]
    return {
        "number": issue["number"],
        "subject": fm.get("subject"),
        "publish_date": (fm.get("publish_date") or "")[:10],
        "topics": fm.get("topics") or [],
        "body": body,
        "body_truncated": len(issue.get("body") or "") > ISSUE_BODY_CAP,
    }


def t_get_section(deps, number: int | str, section: str) -> dict[str, Any] | str:
    """Pull one named section (`Notable`, `Briefly`, `Featured`, `Microposts`, etc.)."""
    issue = archive.read_issue(int(str(number).split("-", 1)[0]))
    if issue is None:
        return f"no archive file for #{number}"
    body = issue.get("body") or ""
    pattern = SECTION_RE_TEMPLATE.format(section=re.escape(section))
    match = re.search(pattern, body)
    if not match:
        return {"number": issue["number"], "section": section, "text": "", "found": False}
    text = match.group(1).strip()
    return {
        "number": issue["number"],
        "section": section,
        "text": text[:ISSUE_BODY_CAP],
        "found": True,
    }


def t_list_recent_issues(deps, limit: int = 10) -> list[dict[str, Any]]:
    """Last N issues (highest number first) with subject + abstract."""
    issues = sorted(
        deps.corpus.corpus["issues"],
        key=lambda i: archive.latest_issue_number([i]) or 0,
        reverse=True,
    )[: int(limit)]
    return [
        {
            "number": i.get("number"),
            "date": (i.get("publish_date") or "")[:10],
            "subject": i.get("subject"),
            "topics": (i.get("topics") or [])[:6],
            "abstract": (i.get("summary") or {}).get("abstract", "") or "",
        }
        for i in issues
    ]


def t_quote_search(deps, phrase: str, limit: int = 8) -> list[dict[str, Any]]:
    """Exact substring search across all issue bodies. Use to verify a phrase actually appears."""
    needle = (phrase or "").lower()
    if not needle:
        return []
    hits: list[dict[str, Any]] = []
    archive_dir = REPO / "apps" / "site" / "archive"
    for path in sorted(archive_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        idx = text.lower().find(needle)
        if idx < 0:
            continue
        # Pull a small window around the hit.
        start = max(0, idx - 120)
        end = min(len(text), idx + len(needle) + 120)
        snippet = text[start:end].replace("\n", " ").strip()
        try:
            number = int(path.stem.split("-", 1)[0])
        except ValueError:
            number = path.stem
        hits.append({"issue": number, "snippet": f"…{snippet}…"})
        if len(hits) >= int(limit):
            break
    return hits


# ---------- Patty ----------

def t_get_support_state(deps) -> str:
    """Current nonprofit, supporter count, amount raised, past nonprofits."""
    return support_state.render_state(support_state.read())


# ---------- web ----------

def t_fetch_url(deps, url: str, max_chars: int = 12_000) -> dict[str, Any]:
    """Fetch a URL and return readable text. Use for Linky to actually read what
    a bookmark is about before recommending it."""
    return web.fetch_text(url, max_chars=int(max_chars))


def t_read_length(deps, url: str) -> dict[str, Any]:
    """Fetch a URL and bucket how long it is to read — short / medium / long
    / unknown — plus the word count."""
    return web.read_length(str(url))


# ---------- current issue window (operator-set) ----------

# Canonical implementations live in `tools/issue.py`. Jamie sets the
# active window via the ``/eddy issue start`` slash command; agents
# read it here via ``issue__current_window`` (active row) and
# ``issue__list_windows`` (historical metadata).
t_current_issue_window = issue.t_current_issue_window
t_list_issue_windows = issue.t_list_issue_windows


# ---------- memory (universal) ----------

def t_remember(
    deps,
    content: str,
    kind: str = "observation",
    key: Optional[str] = None,
    related_issue: Optional[int] = None,
    expires_in_days: Optional[int] = None,
) -> dict[str, Any]:
    """Save a note to long-term memory. Notes are visible to all teammates
    and persist across sessions. ``kind`` is one of:
      preference / observation / todo / context / theme.
    Use ``key`` for a short retrieval label (e.g. ``"jamie:ai-fatigue"``)."""
    if kind not in db.NOTE_KINDS:
        return {"error": f"kind must be one of {list(db.NOTE_KINDS)}"}
    expires_at: Optional[str] = None
    if expires_in_days is not None:
        from datetime import datetime, timedelta, timezone
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=int(expires_in_days))
        ).strftime("%Y-%m-%d %H:%M:%S")
    # Persona name comes from the calling persona via deps.
    note_id = db.insert_agent_note(
        agent_name=active_persona.get() or "unknown",
        kind=kind,
        content=content,
        key=key,
        related_issue=int(related_issue) if related_issue is not None else None,
        expires_at=expires_at,
    )
    return {"id": note_id, "kind": kind, "key": key, "saved": True}


def t_recall(
    deps,
    query: Optional[str] = None,
    kind: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 20,
    include_resolved: bool = False,
) -> list[dict[str, Any]]:
    """Read notes from long-term memory. Default is your own active notes;
    pass ``agent_name="*"`` to see everyone's, or a specific persona name
    to see one teammate's. ``query`` does a substring match across content
    and key."""
    if agent_name == "*":
        agent_name = None
    elif not agent_name:
        agent_name = active_persona.get()
    return db.query_agent_notes(
        agent_name=agent_name,
        kind=kind,
        query=query,
        include_resolved=bool(include_resolved),
        limit=int(limit),
    )


def t_forget_note(deps, note_id: int, status: str = "resolved") -> dict[str, Any]:
    """Mark a note as resolved or stale. Notes are never hard-deleted —
    they fall off ``recall`` results unless ``include_resolved=true``."""
    if status not in ("resolved", "stale", "active"):
        return {"error": "status must be resolved, stale, or active"}
    ok = db.update_agent_note_status(int(note_id), status)
    return {"id": int(note_id), "status": status, "updated": ok}


# ---------- follow-ups (universal — the targeted heartbeat) ----------

def t_followup_schedule(
    deps,
    note: str,
    when: Optional[str] = None,
    in_days: Optional[int] = None,
    at_issue: Optional[int] = None,
) -> dict[str, Any]:
    """Schedule a follow-up for yourself — the only thing that will actually
    bring a commitment back. Exactly one trigger: ``when`` (ISO date/datetime),
    ``in_days`` (relative offset, fires ~6pm that many days out), or
    ``at_issue`` (fires once that issue is in flight)."""
    from ...jobs.follow_up import FollowUpError, create, trigger_desc  # lazy: avoid an import cycle
    try:
        row = create(
            persona=active_persona.get() or "eddy", note=note,
            when=when, in_days=in_days, at_issue=at_issue, created_by=active_persona.get(),
        )
    except FollowUpError as exc:
        return {"error": str(exc)}
    return {"id": row.get("id"), "persona": row.get("persona"), "fires": trigger_desc(row), "note": row.get("note")}


def t_followup_list(deps) -> list[dict[str, Any]]:
    """Your pending follow-ups — id, when each fires, and the note."""
    from ...jobs.follow_up import trigger_desc  # lazy: avoid an import cycle
    return [
        {"id": r["id"], "fires": trigger_desc(r), "note": r["note"]}
        for r in db.open_follow_ups(persona=active_persona.get())
    ]


def t_followup_cancel(deps, followup_id: int) -> dict[str, Any]:
    """Cancel one of your pending follow-ups by id (from ``followup__list``)."""
    if db.get_follow_up(int(followup_id)) is None:
        return {"error": f"no follow-up #{followup_id}"}
    ok = db.cancel_follow_up(int(followup_id), persona=active_persona.get())
    return {"id": int(followup_id), "cancelled": ok}


# ---------- S3 issue workspace (universal) ----------

def t_workspace_list_all(deps) -> dict[str, Any]:
    """List every issue workspace folder in S3 with file counts and
    last-modified timestamps. The highest issue number is the issue
    currently being assembled."""
    return s3.list_workspaces()


def t_workspace_list_files(deps, issue_number: int) -> dict[str, Any]:
    """List the per-issue files in the S3 workspace
    (``s3://files.thingelstad.com/weekly-thing/{N}/``)."""
    try:
        return s3.list_issue(int(issue_number))
    except s3.S3PathError as exc:
        return {"error": str(exc)}


def t_workspace_read(deps, issue_number: int, filename: str) -> dict[str, Any]:
    """Read one file from the per-issue S3 workspace. Text only — binary
    objects (photos) are reported but not returned. Filename must be a
    bare component (no slashes, no '..')."""
    try:
        return s3.read_issue_file(int(issue_number), filename)
    except s3.S3PathError as exc:
        return {"error": str(exc)}


def t_workspace_write(
    deps, issue_number: int, filename: str, content: str
) -> dict[str, Any]:
    """Write one file to the per-issue S3 workspace. Use for the issue
    text/JSON assets the assemble pipeline reads (e.g. ``intro.md``,
    ``currently.md``, ``metadata.json``, ``cta-1.md``). 256KB max per
    file. Allowed extensions: md, txt, json, yaml, yml, csv, html.
    Filename must be a bare component."""
    try:
        return s3.write_issue_file(int(issue_number), filename, content)
    except s3.S3PathError as exc:
        return {"error": str(exc)}


# ---------- currently (per-issue ## Currently section) ----------

# The mutating tools (`set`, `clear`, `add_type`, `reorder`) refire
# `update-draft` as a background task so the preview reflects the change
# without blocking the agent's reply. Fire-and-forget is fine — the
# refire's outcome lands in agent_runs; the user-facing message has
# already gone out.


def _currently_refire(issue_number: int) -> bool:
    """Schedule ``update-draft`` for ``issue_number`` if an event loop is
    running. Returns True when a task was scheduled (best-effort)."""
    try:
        from ...jobs import _base as _jobs_base
    except Exception:  # noqa: BLE001
        return False
    try:
        _jobs_base.schedule_update_draft_refire(
            _jobs_base.JobContext(trigger="agent-tool"), int(issue_number),
        )
    except Exception:  # noqa: BLE001
        return False
    return True


def _active_issue_number() -> Optional[int]:
    win = db.get_active_issue_window()
    return int(win["issue_number"]) if win else None


def t_currently_list_types(deps, include_inactive: bool = False) -> list[dict[str, Any]]:
    """The pool of canonical Currently labels — what types Currently entries
    can hang off of (Listening, Watching, Installing, …). Use this before
    ``currently__set`` to confirm a label exists; if it doesn't, call
    ``currently__add_type`` first. Carries ``last_used_issue`` so you can
    see which types have shown up recently vs gone cold."""
    return db.currently_list_types(include_inactive=bool(include_inactive))


def t_currently_list_entries(
    deps, issue_number: Optional[int] = None,
) -> dict[str, Any]:
    """The active issue's filled Currently entries (or another issue's if
    ``issue_number`` is given), ordered by ``position`` (render order in
    the published issue). Empty list = nothing's set yet."""
    n: Optional[int] = None
    if issue_number is not None:
        try:
            n = int(issue_number)
        except (TypeError, ValueError):
            return {"error": f"issue_number must be an int (got {issue_number!r})"}
    if n is None:
        n = _active_issue_number()
        if n is None:
            return {"error": "no active issue window — Jamie starts one via /eddy issue start"}
    entries = db.currently_get_entries(n)
    return {
        "issue_number": n,
        "count": len(entries),
        "entries": [
            {
                "label": r["type_label"],
                "value": r["value"],
                "position": r["position"],
                "updated_at": r.get("updated_at"),
            }
            for r in entries
        ],
    }


def t_currently_set(deps, label: str, value: str) -> dict[str, Any]:
    """Set one Currently entry for the active in-flight issue. On INSERT
    the new entry appends with the next ``position`` (insertion order);
    on UPDATE the existing position is preserved. The value may include
    markdown links — pass them through verbatim (Jamie's voice; don't
    paraphrase). Refires ``update-draft`` so the preview refreshes.

    If the ``label`` isn't a known canonical type, this errors — call
    ``currently__add_type`` first when Jamie mentions a brand-new type
    (e.g. "Printing")."""
    n = _active_issue_number()
    if n is None:
        return {"error": "no active issue window — Jamie starts one via /eddy issue start"}
    try:
        res = db.currently_set_entry(n, label, value)
    except db.CurrentlyError as exc:
        return {"error": str(exc)}
    refired = _currently_refire(n)
    return {
        "ok": True,
        "issue_number": n,
        "label": res["label"],
        "position": res["position"],
        "refired_update_draft": refired,
    }


def t_currently_clear(deps, label: str) -> dict[str, Any]:
    """Delete one Currently entry for the active in-flight issue.
    Renumbers remaining entries contiguously. Refires
    ``update-draft``."""
    n = _active_issue_number()
    if n is None:
        return {"error": "no active issue window — Jamie starts one via /eddy issue start"}
    deleted = db.currently_clear_entry(n, label)
    refired = _currently_refire(n) if deleted else False
    return {
        "ok": True,
        "issue_number": n,
        "label": (label or "").strip(),
        "deleted": deleted,
        "refired_update_draft": refired,
    }


def t_currently_add_type(deps, label: str) -> dict[str, Any]:
    """Add a new canonical Currently type (e.g. "Printing"). Idempotent
    once it exists. Use when Jamie mentions a type that isn't in
    ``currently__list_types`` yet."""
    try:
        row = db.currently_add_type(label)
    except db.CurrentlyError as exc:
        return {"error": str(exc)}
    return {"ok": True, "label": row["label"]}


def t_currently_reorder(deps, labels: list[str]) -> dict[str, Any]:
    """Reorder the active issue's Currently entries to the given
    permutation of filled labels — positions 1..N. The list must be a
    *strict permutation* of every currently-filled label for the issue
    (a missing or extra label is refused). Use when an issue has 3+
    entries and a particular sequence reads better — narrative
    grouping, strongest first, or a deliberate shuffle. Refires
    ``update-draft``."""
    n = _active_issue_number()
    if n is None:
        return {"error": "no active issue window — Jamie starts one via /eddy issue start"}
    if not isinstance(labels, list) or not labels:
        return {"error": "`labels` must be a non-empty list of label strings"}
    try:
        applied = db.currently_reorder(n, labels)
    except db.CurrentlyError as exc:
        return {"error": str(exc)}
    refired = _currently_refire(n)
    return {
        "ok": True,
        "issue_number": n,
        "applied_order": applied,
        "refired_update_draft": refired,
    }


def t_currently_suggest_stale(deps, k: int = 3) -> list[dict[str, Any]]:
    """Top-K active Currently types ordered by recency — never-used
    first, then least-recent. Each entry carries ``gap_issues`` (issues
    since last use; ``None`` for never-used). Use to pick a fresh type
    to ask Jamie about when opening the week's Currently conversation."""
    try:
        kk = max(1, int(k))
    except (TypeError, ValueError):
        kk = 3
    return db.currently_suggest_stale(_active_issue_number(), k=kk)


# ---------- draft completeness (in-flight issue) ----------

def t_draft_section_status(deps) -> dict[str, Any]:
    """Section + asset completeness for the in-flight issue's ``draft.md``:
    per-section item counts and 'present' flags (Notable/Briefly/Journal),
    standalone-asset presence (intro/currently/haiku/cover/final/metadata),
    word count, the list of what's still missing for ship, and a
    ``ship_ready`` flag. Deterministic — read it, don't recompute it."""
    window = db.get_active_issue_window()
    if window is None:
        return {
            "error": "No active issue window. Jamie sets it via /eddy issue start."
        }
    try:
        return draft.section_status(int(window["issue_number"]))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------- editorial comments ----------

def t_editorial_get_comment(deps, handle: str) -> dict[str, Any]:
    """Fetch one editorial review comment by its stable handle
    (``E349-N1``, ``E349-X3``, ``E349-W2``, etc.).

    Returns the comment body + scope + verdict, the anchored item
    (when the comment is item-scoped — title, url, body preview,
    section, position), the row's age, and a ``replaced_by_handle``
    pointer when this comment has been superseded by a later review.

    Resolve a comment handle when Jamie asks about it ("tell me more
    about E349-N1", "what was that about E349-X2", etc.). The handle
    namespace is per-issue: a future ``@eddy tell me about E350-N1``
    will resolve against issue 350's comments, not 349's, because
    handles include the issue number.
    """
    raw = (handle or "").strip().upper()
    if not raw:
        return {"error": "handle is required (e.g. 'E349-N1')"}
    row = issue_items_mod.get_comment_by_handle(raw)
    if row is None:
        return {"error": f"no editorial comment with handle {raw!r}"}
    out: dict[str, Any] = {
        "handle": row["handle"],
        "issue_number": row["issue_number"],
        "scope": row["scope"],
        "verdict": row["verdict"],
        "section": row.get("section"),
        "anchor_text": row.get("anchor_text"),
        "body_md": row.get("body_md"),
        "reasoning_md": row.get("reasoning_md"),
        "created_at": row.get("created_at"),
        "superseded": bool(row.get("replaced_by_id")),
    }
    # If this row was superseded, surface the replacement's handle so
    # the user can follow the chain ("E349-N1 was superseded by E349-N4").
    if row.get("replaced_by_id"):
        try:
            with db.connect() as conn:
                r = conn.execute(
                    "SELECT handle FROM editorial_comments WHERE id = ?",
                    (int(row["replaced_by_id"]),),
                ).fetchone()
                if r is not None:
                    out["replaced_by_handle"] = r["handle"]
        except Exception:  # noqa: BLE001
            pass
    # Item context — only fetched when the comment anchors to a specific
    # row. Section/issue/hygiene-scoped comments have no item to attach.
    if row.get("item_id"):
        item = issue_items_mod.get_item(int(row["item_id"]))
        if item is not None:
            body = (item.get("body_md") or "")
            out["item"] = {
                "id": item["id"],
                "section": item["section"],
                "position": item["position"],
                "is_promoted": bool(item.get("is_promoted")),
                "url": item.get("url"),
                "title": item.get("title"),
                "body_preview": body[:600] + ("…" if len(body) > 600 else ""),
            }
    return out


def t_editorial_list_open(deps, issue_number: Optional[int] = None) -> dict[str, Any]:
    """List open (not-yet-superseded) editorial comments for an issue.

    Defaults to the in-flight issue when ``issue_number`` is omitted.
    Returns ``{issue_number, count, comments: [{handle, scope, verdict,
    section, snippet}]}``. Snippet is the first ~140 chars of body.

    Useful for ``"what did you flag on this issue?"`` style questions —
    the LLM can use the result to either summarize or follow up with
    ``editorial__get_comment(handle)`` for specific entries.
    """
    n: Optional[int] = None
    if issue_number is not None:
        try:
            n = int(issue_number)
        except (TypeError, ValueError):
            return {"error": f"issue_number must be an int (got {issue_number!r})"}
    if n is None:
        window = db.get_active_issue_window()
        if window is None:
            return {"error": "no active issue window; pass issue_number explicitly"}
        n = int(window["issue_number"])
    rows = issue_items_mod.list_open_comments(n)
    return {
        "issue_number": n,
        "count": len(rows),
        "comments": [
            {
                "handle": r["handle"],
                "scope": r["scope"],
                "verdict": r["verdict"],
                "section": r.get("section"),
                "snippet": ((r.get("body_md") or "")[:140]
                            + ("…" if len(r.get("body_md") or "") > 140 else "")),
            }
            for r in rows
        ],
    }


# ---------- Discord reactions ----------

def t_react_add(deps, emoji: str) -> dict[str, Any]:
    """Add a single emoji reaction to the message currently being responded to.

    Routed through this persona's Discord client so the reaction shows
    under the persona's avatar. Reads ``active_react_target`` (set by
    the mention/peer/team handler) and ``active_persona`` from
    ContextVars; refuses cleanly when neither is in context (heartbeat
    path, eval scripts).
    """
    target = active_react_target.get()
    if target is None:
        return {"error": "no message in context to react to"}
    if not isinstance(emoji, str) or not emoji.strip():
        return {"error": "emoji must be a non-empty string"}

    persona = active_persona.get()
    team = getattr(deps, "team", None)
    if team is None:
        return {"error": "team registry unavailable"}
    bot = team.bots.get(persona)
    if bot is None or bot.user is None or getattr(bot, "loop", None) is None:
        return {"error": f"persona {persona!r} unavailable"}

    channel_id, message_id = target

    async def _do() -> None:
        ch = bot.get_partial_messageable(channel_id)
        msg = ch.get_partial_message(message_id)
        await msg.add_reaction(emoji)

    try:
        fut = asyncio.run_coroutine_threadsafe(_do(), bot.loop)
        fut.result(timeout=8)
    except Exception as exc:  # noqa: BLE001
        logger.exception("react__add %s by %s failed", emoji, persona)
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"ok": True, "emoji": emoji}


# ---------- specs (Anthropic format) ----------

SPECS: dict[str, dict[str, Any]] = {
    "archive__search": {
        "name": "archive__search",
        "description": (
            "BM25 LEXICAL search over Weekly Thing archive chunks. Use when the query is a SPECIFIC "
            "PHRASE, person, or product name — anything where the exact words matter. Cheap, fast, "
            "always available. For thematic / conceptual lookups (where the words may differ from "
            "the meaning) prefer archive__retrieve. Iterate — refine the query based on what comes back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "description": "max results, default 8"},
            },
            "required": ["query"],
        },
    },
    "archive__retrieve": {
        "name": "archive__retrieve",
        "description": (
            "SEMANTIC archive retrieval via Bedrock Cohere embed + Cohere rerank against the "
            "pre-embedded corpus. Use for THEME / CONCEPT / IDEA queries — finds matches by meaning, "
            "not by shared words. The right pick when the user asks 'what has Jamie written about X' "
            "where X is a concept (privacy, agent collaboration, slow software) rather than a literal "
            "string. Slower and more expensive than archive__search (~1s round trip, ~$0.001/call) — "
            "use the lexical search first when an exact phrase will do. Returns the same shape as "
            "archive__search; on retrieval failure returns an error dict so you can fall back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "description": "max results, default 8"},
            },
            "required": ["query"],
        },
    },
    "archive__get_issue": {
        "name": "archive__get_issue",
        "description": (
            "Return one full issue (front matter + body, truncated if very long). "
            "Use when you need full context for a specific issue you already have a number for."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": ["integer", "string"]}},
            "required": ["number"],
        },
    },
    "archive__get_section": {
        "name": "archive__get_section",
        "description": (
            "Pull one named section from one issue (e.g. 'Notable', 'Briefly', 'Featured', 'Microposts'). "
            "Cheaper than archive__get_issue when you only need that section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": ["integer", "string"]},
                "section": {"type": "string"},
            },
            "required": ["number", "section"],
        },
    },
    "archive__list_recent": {
        "name": "archive__list_recent",
        "description": (
            "Last N issues by number (newest first), with date, subject, topics, and abstract. "
            "Use to ground 'the latest', 'last few', 'recent' references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "default 10"}},
        },
    },
    "archive__quote_search": {
        "name": "archive__quote_search",
        "description": (
            "Exact substring search across issue bodies. Use to verify a specific phrase or product name "
            "actually appears in the archive — do not infer presence from archive__search hits alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phrase": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["phrase"],
        },
    },
    "site__support_state": {
        "name": "site__support_state",
        "description": (
            "Current support program state: this year's nonprofit, supporter count, amount raised, "
            "past nonprofits. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "web__fetch_url": {
        "name": "web__fetch_url",
        "description": (
            "Fetch a URL and return readable text (title + extracted body). Use to actually "
            "read what a bookmark is about — Pinboard's title and tags often aren't enough "
            "to judge fit. Truncates long pages; binary content rejected; ~12KB cap on text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "description": "default 12000"},
            },
            "required": ["url"],
        },
    },
    "web__read_length": {
        "name": "web__read_length",
        "description": (
            "Fetch a URL and bucket how long it is to read: 'short' (<~800 words), 'medium', "
            "'long' (>~2500 words), or 'unknown' if it can't be fetched (paywall, login, "
            "binary). Returns {url, bucket, word_count}. Cheaper to reason over than fetching "
            "the whole body when you only need the length (e.g. gauging a toread pile)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "memory__remember": {
        "name": "memory__remember",
        "description": (
            "Save a note to long-term memory — visible to all teammates and persists across "
            "sessions. Use for: preferences Jamie has expressed, observations to carry "
            "forward, todos for yourself, themes you're tracking, context that mattered. "
            "`kind` is one of: preference, observation, todo, context, theme. `key` is an "
            "optional short retrieval label (e.g. 'jamie:ai-fatigue')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["preference", "observation", "todo", "context", "theme"],
                },
                "key": {"type": "string"},
                "related_issue": {"type": "integer"},
                "expires_in_days": {"type": "integer"},
            },
            "required": ["content"],
        },
    },
    "memory__recall": {
        "name": "memory__recall",
        "description": (
            "Read notes from long-term memory. Default scope is your own active notes; "
            "set `agent_name` to a teammate's name to read theirs, or '*' to read everyone's. "
            "`query` does substring search across content and key. Use to surface relevant "
            "preferences/themes/todos before answering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string"},
                "agent_name": {"type": "string"},
                "limit": {"type": "integer", "description": "default 20"},
                "include_resolved": {"type": "boolean"},
            },
        },
    },
    "memory__forget": {
        "name": "memory__forget",
        "description": (
            "Mark a memory note as resolved (the todo is done) or stale (no longer "
            "applicable). Notes are never hard-deleted; resolved/stale notes drop out of "
            "default memory__recall results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["resolved", "stale", "active"]},
            },
            "required": ["note_id"],
        },
    },
    "followup__schedule": {
        "name": "followup__schedule",
        "description": (
            "Schedule a follow-up for yourself — the ONLY thing that will actually bring a "
            "commitment back; there is no other reminder or heartbeat. Use it whenever you tell "
            "Jamie you'll revisit something at a specific time or once the issue reaches a "
            "number. Give a clear `note` (what you're following up on, written so future-you "
            "understands it without this conversation) and exactly one trigger: `when` — an ISO "
            "date `YYYY-MM-DD` (taken as ~6pm that day) or datetime `YYYY-MM-DDTHH:MM` (compute "
            "it from today's date in your context); `in_days` — a relative offset that fires "
            "~6pm that many days out (`1` = tomorrow evening, `30` = roughly next month); or "
            "`at_issue` — an issue number, fires once that issue is the in-flight one. When it "
            "comes due, you're handed the note + current context and post a check-in in your "
            "channel. `followup__list` / `followup__cancel` to manage them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "What you're following up on — self-contained."},
                "when": {"type": "string", "description": "ISO date YYYY-MM-DD or datetime YYYY-MM-DDTHH:MM."},
                "in_days": {"type": "integer", "description": "Relative offset in days (1 = tomorrow evening)."},
                "at_issue": {"type": "integer", "description": "Fire once this issue number is in flight."},
            },
            "required": ["note"],
        },
    },
    "followup__list": {
        "name": "followup__list",
        "description": "List your pending follow-ups — id, when each fires, and the note.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "followup__cancel": {
        "name": "followup__cancel",
        "description": "Cancel one of your pending follow-ups by id (from followup__list).",
        "input_schema": {
            "type": "object",
            "properties": {"followup_id": {"type": "integer"}},
            "required": ["followup_id"],
        },
    },
    "issue__current_window": {
        "name": "issue__current_window",
        "description": (
            "Return the active in-flight issue window — the one Jamie is "
            "assembling this week. Returns {issue_number, pub_date, end_date, "
            "start_date, day_count, set_at, set_by}. **The in-flight issue is "
            "NOT in your archive corpus** (archive__search / archive__get_issue "
            "won't find it; it's a draft). Date semantics: pub_date is the "
            "Saturday it ships; end_date = pub_date - 1 day is the content "
            "cutoff; start_date = end_date - day_count days is the prior "
            "issue's cutoff (so a normal issue covers the 7 days from "
            "start_date+1 through end_date). Returns {error: ...} when Jamie "
            "hasn't set a window yet. Use when Jamie says 'the current "
            "issue', 'this weekend's issue', or 'the one I'm working on'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "issue__list_windows": {
        "name": "issue__list_windows",
        "description": (
            "List recent issue windows (newest issue number first). Same "
            "shape as issue__current_window plus an is_active flag. Use to "
            "answer 'when did issue #N ship?' or 'what content window did "
            "the last double issue cover?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "default 12"},
            },
        },
    },
    "workspace__list_all": {
        "name": "workspace__list_all",
        "description": (
            "List every per-issue workspace folder in S3 (under "
            "s3://files.thingelstad.com/weekly-thing/). Returns each issue's "
            "number, file count, and most-recent modification time. Note: this "
            "prefix is shared with the published archive, so every shipped issue "
            "shows up here too — the highest-numbered folder is the in-flight "
            "issue. Use this when you need per-folder modification times or want "
            "to see what's been staged for past issues. For the active in-flight "
            "issue's number and dates, call `issue__current_window` (the "
            "operator-set source of truth). No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "workspace__list_files": {
        "name": "workspace__list_files",
        "description": (
            "List the files in one per-issue workspace folder at "
            "s3://files.thingelstad.com/weekly-thing/{N}/. This is the issue's "
            "working directory: draft.md, final.md, buttondown.md, intro.md, "
            "currently.md, haiku.md, metadata.json, cta-*.md (text assets the "
            "jobs write) alongside cover.jpg, cover-large.jpg, journal/ photos, "
            "and audio MP3s (binaries written by other pipelines)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"issue_number": {"type": "integer"}},
            "required": ["issue_number"],
        },
    },
    "workspace__read": {
        "name": "workspace__read",
        "description": (
            "Read one file from a per-issue workspace folder. Text only — binary "
            "objects like cover.jpg are reported but their bytes aren't returned. "
            "Filename must be a bare component (no slashes, no '..')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "filename": {
                    "type": "string",
                    "description": "e.g. 'draft.md', 'metadata.json'",
                },
            },
            "required": ["issue_number", "filename"],
        },
    },
    "workspace__write": {
        "name": "workspace__write",
        "description": (
            "Write one text/JSON file to a per-issue workspace folder. Use for "
            "the issue assets the assemble pipeline reads — intro.md, currently.md, "
            "metadata.json, cta-1.md, etc. 256KB cap per file. Allowed extensions: "
            "md, txt, json, yaml, yml, csv, html. The path is scoped to "
            "weekly-thing/{issue_number}/ — you can't write outside that prefix, "
            "and the text-only extension allowlist prevents clobbering binaries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "filename": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["issue_number", "filename", "content"],
        },
    },
    "currently__list_types": {
        "name": "currently__list_types",
        "description": (
            "The pool of canonical Currently labels — what types a Currently "
            "entry can hang off of (Listening, Watching, Installing, …). Use "
            "before `currently__set` to confirm a label exists; if it doesn't, "
            "call `currently__add_type` first. Each row carries "
            "`last_used_issue` so you can see which types are fresh vs cold. "
            "Active-only by default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include retired types. Default false.",
                },
            },
        },
    },
    "currently__list_entries": {
        "name": "currently__list_entries",
        "description": (
            "The filled Currently entries for an issue, in render order. "
            "Defaults to the active in-flight issue. Returns {issue_number, "
            "count, entries:[{label, value, position, updated_at}]}. Empty "
            "list = nothing's set yet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "Optional. Defaults to the in-flight issue.",
                },
            },
        },
    },
    "currently__set": {
        "name": "currently__set",
        "description": (
            "Set one Currently entry for the active in-flight issue. On INSERT "
            "the new entry appends with the next position (insertion order); "
            "on UPDATE the existing position is preserved. The value may "
            "contain markdown links — pass them through verbatim in Jamie's "
            "voice (don't paraphrase or summarise). If the `label` isn't a "
            "known canonical type, this errors — call `currently__add_type` "
            "first when Jamie mentions a brand-new type (e.g. 'Printing'). "
            "Refires `update-draft` so the preview reflects the change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Canonical type, e.g. 'Listening'. Case-insensitive match against currently_types.",
                },
                "value": {
                    "type": "string",
                    "description": "The Currently entry text. Markdown OK; preserve Jamie's voice.",
                },
            },
            "required": ["label", "value"],
        },
    },
    "currently__clear": {
        "name": "currently__clear",
        "description": (
            "Delete one Currently entry for the active in-flight issue. "
            "Remaining entries renumber contiguously. Refires "
            "`update-draft`. Idempotent — clearing a missing entry returns "
            "{ok: true, deleted: false} without error."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
    },
    "currently__add_type": {
        "name": "currently__add_type",
        "description": (
            "Add a new canonical Currently type (e.g. 'Printing'). Idempotent "
            "for an exact match — duplicates (case-insensitive) are refused "
            "with a friendly error. Use when Jamie mentions a type not in "
            "`currently__list_types` yet, then call `currently__set` to fill "
            "the value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
    },
    "currently__reorder": {
        "name": "currently__reorder",
        "description": (
            "Reorder the active issue's Currently entries to the given "
            "permutation of filled labels — positions 1..N. Must be a STRICT "
            "permutation of every currently-filled label for the issue (a "
            "missing or extra label is refused). Use when an issue has 3+ "
            "entries and a particular sequence reads better — narrative "
            "grouping, strongest first, or a deliberate shuffle. Refires "
            "`update-draft`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Strict permutation of currently-filled labels.",
                },
            },
            "required": ["labels"],
        },
    },
    "currently__suggest_stale": {
        "name": "currently__suggest_stale",
        "description": (
            "Top-K active Currently types ordered by recency — never-used "
            "first, then least-recent. Each entry carries `gap_issues` "
            "(issues since last use; null for never-used). Use to pick a "
            "fresh type to ask Jamie about when opening the week's Currently "
            "conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "k": {"type": "integer", "description": "max picks, default 3"},
            },
        },
    },
    "draft__section_status": {
        "name": "draft__section_status",
        "description": (
            "Deterministic completeness report for the in-flight issue's "
            "draft.md: per-section item counts + 'present' flags for "
            "Notable / Briefly / Journal, presence of the standalone assets "
            "(intro.md, currently.md, haiku.md, cover.jpg, final.md, "
            "metadata.json, cta-*.md), word count, the list of what's still "
            "missing for ship, and a ship_ready flag. Read this rather than "
            "eyeballing the draft and counting headings yourself. Returns "
            "{error: ...} if no issue is in flight. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "react__add": {
        "name": "react__add",
        "description": (
            "Add a single emoji reaction to the message you're currently "
            "responding to (mention, peer message, or team-round trigger). "
            "Posts under your persona's avatar — Eddy's react shows as Eddy. "
            "Especially useful in `#workshop`: when a peer's message lands "
            "but you wouldn't add anything in prose, drop a brief reaction "
            "and PASS instead of staying invisible. Use sparingly — one "
            "reaction per message, only when the emoji is your honest take. "
            "Picks should match your persona: Eddy 📝👀🤔, Linky 🔗📚⏩, "
            "Marky 📈🔥, Patty 🤝💚 — but anything fitting works. Returns "
            "{ok, emoji} on success, {error: …} if there's no message in "
            "context (heartbeat path) or Discord rejects the emoji."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "emoji": {
                    "type": "string",
                    "description": "Single Discord emoji (unicode, e.g. 👀). Custom guild emoji as <:name:id>.",
                },
            },
            "required": ["emoji"],
        },
    },
    "editorial__get_comment": {
        "name": "editorial__get_comment",
        "description": (
            "Fetch one editorial review comment by its handle "
            "(e.g. 'E349-N1', 'E349-X3'). Returns the comment body + "
            "scope + verdict, the anchored item (when item-scoped), "
            "and the replacement handle when this comment has been "
            "superseded by a later review. Use when Jamie asks "
            "about a specific handle ('tell me about E349-N1')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Editorial handle, e.g. 'E349-N1'. Case-insensitive.",
                },
            },
            "required": ["handle"],
        },
    },
    "editorial__list_open": {
        "name": "editorial__list_open",
        "description": (
            "List open (not-yet-superseded) editorial comments for an "
            "issue with their handles + short snippets. Defaults to "
            "the in-flight issue. Useful for 'what did you flag on "
            "this issue?' — follow up with editorial__get_comment(handle) "
            "for any entry you want the full body for."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "Optional. Defaults to in-flight issue.",
                },
            },
        },
    },
}


FUNCS: dict[str, Callable[..., Any]] = {
    "archive__search": t_search_archive,
    "archive__retrieve": t_retrieve_archive,
    "archive__get_issue": t_get_issue,
    "archive__get_section": t_get_section,
    "archive__list_recent": t_list_recent_issues,
    "archive__quote_search": t_quote_search,
    "site__support_state": t_get_support_state,
    "web__fetch_url": t_fetch_url,
    "web__read_length": t_read_length,
    "issue__current_window": t_current_issue_window,
    "issue__list_windows": t_list_issue_windows,
    "memory__remember": t_remember,
    "memory__recall": t_recall,
    "memory__forget": t_forget_note,
    "followup__schedule": t_followup_schedule,
    "followup__list": t_followup_list,
    "followup__cancel": t_followup_cancel,
    "workspace__list_all": t_workspace_list_all,
    "workspace__list_files": t_workspace_list_files,
    "workspace__read": t_workspace_read,
    "workspace__write": t_workspace_write,
    "currently__list_types": t_currently_list_types,
    "currently__list_entries": t_currently_list_entries,
    "currently__set": t_currently_set,
    "currently__clear": t_currently_clear,
    "currently__add_type": t_currently_add_type,
    "currently__reorder": t_currently_reorder,
    "currently__suggest_stale": t_currently_suggest_stale,
    "draft__section_status": t_draft_section_status,
    "react__add": t_react_add,
    "editorial__get_comment": t_editorial_get_comment,
    "editorial__list_open": t_editorial_list_open,
}


def register_local_helpers(registry: ToolRegistry) -> None:
    """Register the local-helper tools (everything in ``FUNCS`` / ``SPECS``).

    External systems (``buttondown``, ``pinboard``, ``stripe``,
    ``tinylytics``) are added separately via ``registry.register_system``
    from ``bot.py``.
    """
    for name in sorted(FUNCS):
        spec = SPECS[name]
        registry.register(name, spec, FUNCS[name], source="local")
