"""Tool registry for the workshop-bot agent loop.

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
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import (
    archive,
    db,
    draft,
    issue,
    s3,
    support_state,
    web,
)
from ..systems._base import SystemServer

logger = logging.getLogger("workshop.tools")

# The agent loop sets this before each tool execution so per-persona
# tools (`memory__remember`, `memory__recall`) can attribute their work
# to the calling persona without leaning on a shared, mutable Deps object.
active_persona: ContextVar[str] = ContextVar("active_persona", default="unknown")

# Mention/peer/team handlers set this so ``react__add`` knows which
# Discord message to attach the emoji to. ``None`` means the persona
# was not invoked from a Discord message (e.g. heartbeat) and the
# react tool should refuse with a clear error.
active_react_target: ContextVar[Optional[tuple[int, int]]] = ContextVar(
    "active_react_target", default=None
)

REPO = Path(__file__).resolve().parents[3]
SECTION_RE_TEMPLATE = r"(?im)^##+\s*{section}\s*[^\n]*\n([\s\S]*?)(?=^##+\s|\Z)"
TEXT_PREVIEW_CHARS = 1500
ISSUE_BODY_CAP = 24_000


@dataclass(frozen=True)
class Tool:
    name: str
    spec: dict[str, Any]
    func: Callable[..., Any]
    source: str = "local"  # "local" or "system:<name>"
    # Personas that can see this tool. ``None`` (the default) means
    # unrestricted — every persona sees it. A frozenset means only those
    # personas see it (e.g. Stripe is restricted to ``{"patty"}`` so
    # donor data never enters Eddy/Linky/Marky's tool surface).
    restricted_to: Optional[frozenset[str]] = None


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
# active window via the ``/workshop issue start`` slash command; agents
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
    from ..jobs.follow_up import FollowUpError, create, trigger_desc  # lazy: avoid an import cycle
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
    from ..jobs.follow_up import trigger_desc  # lazy: avoid an import cycle
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
            "error": "No active issue window. Jamie sets it via /workshop issue start."
        }
    try:
        return draft.section_status(int(window["issue_number"]))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


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
            "BM25 lexical search over Weekly Thing archive chunks. Default first stop for broad topics, "
            "themes, and evidence gathering. Iterate — refine the query based on what comes back."
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
            "working directory: draft.md, final.md, publish.md, intro.md, "
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
            "Picks should match your persona: Eddy 📝👀🤔, Linky 🔗📚⭐, "
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
}


FUNCS: dict[str, Callable[..., Any]] = {
    "archive__search": t_search_archive,
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
    "draft__section_status": t_draft_section_status,
    "react__add": t_react_add,
}


# ---------- ToolRegistry ----------


class ToolRegistry:
    """Composes external-system tools and local helpers into one namespace.

    Tool names follow ``<system>__<action>`` — ``archive__search``,
    ``memory__remember``, ``workspace__read``, ``buttondown__list_subscribers``.
    The double-underscore separator is API-safe (Anthropic enforces
    ``^[a-zA-Z0-9_-]{1,128}$`` on custom tool names) so the same name is
    used in the registry, the API, and prompts — no boundary translation.

    Local helpers live in ``FUNCS`` / ``SPECS`` keyed by their full name;
    external systems are added by ``register_system(server)`` from
    ``apps/workshop_bot/systems/``.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # Enforced API-safe tool names. Anthropic's regex is
    # ``^[a-zA-Z0-9_-]{1,128}$`` — we additionally forbid the dotted
    # form so an accidental rename ("archive.search") fails loudly at
    # boot rather than at the first API call.
    _NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

    def register(
        self,
        name: str,
        spec: dict[str, Any],
        func: Callable[..., Any],
        source: str = "local",
        restricted_to: Optional[frozenset[str]] = None,
    ) -> None:
        if not self._NAME_RE.match(name):
            raise ValueError(
                f"tool name {name!r} is not API-safe; expected "
                f"<system>__<action> using [a-zA-Z0-9_-]"
            )
        if name in self._tools:
            raise ValueError(f"duplicate tool registration: {name!r}")
        spec_with_name = dict(spec)
        spec_with_name["name"] = name
        self._tools[name] = Tool(
            name=name,
            spec=spec_with_name,
            func=func,
            source=source,
            restricted_to=restricted_to,
        )

    def register_system(self, server: SystemServer) -> None:
        # Systems may declare a `restricted_to` attribute (a set/iterable
        # of persona names) to scope visibility — e.g. StripeServer sets
        # ``restricted_to = {"patty"}`` so donor data never reaches
        # Eddy/Linky/Marky's tool surface.
        restricted_raw = getattr(server, "restricted_to", None)
        restricted = (
            frozenset(restricted_raw) if restricted_raw is not None else None
        )
        for tdef in server.list_tools():
            full = f"{server.name}__{tdef.name}"
            spec = {
                "name": full,
                "description": tdef.description,
                "input_schema": tdef.input_schema,
            }
            self.register(
                full,
                spec,
                tdef.handler,
                source=f"system:{server.name}",
                restricted_to=restricted,
            )

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all_specs(self) -> list[dict[str, Any]]:
        return [dict(t.spec) for t in self._tools.values()]

    def all_names(self) -> list[str]:
        """Every registered tool name, ignoring per-persona restrictions.
        Use ``names_for(persona)`` for the persona-scoped surface that
        the agent loop should actually see."""
        return list(self._tools.keys())

    def names_for(self, persona: str) -> list[str]:
        """Tool names visible to ``persona``. Filters out tools whose
        ``restricted_to`` set doesn't include this persona.
        """
        return [
            n
            for n, t in self._tools.items()
            if t.restricted_to is None or persona in t.restricted_to
        ]

    def dispatch(
        self,
        name: str,
        deps: Any,
        args: dict[str, Any],
        persona: str,
    ) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool {name!r}")
        # Per-persona scoping. Mirrors the same check in
        # ``agent_loop._execute_tool`` so both call paths (this
        # synchronous dispatcher and the async loop's direct
        # ``tool.func`` invocation) enforce restrictions identically.
        if tool.restricted_to is not None and persona not in tool.restricted_to:
            raise PermissionError(
                f"tool {name!r} is not visible to persona {persona!r}"
            )
        token = active_persona.set(persona)
        try:
            return tool.func(deps, **(args or {}))
        finally:
            active_persona.reset(token)


def register_local_helpers(registry: ToolRegistry) -> None:
    """Register the local-helper tools (everything in ``FUNCS`` / ``SPECS``).

    External systems (``buttondown``, ``pinboard``, ``stripe``,
    ``tinylytics``) are added separately via ``registry.register_system``
    from ``bot.py``.
    """
    for name in sorted(FUNCS):
        spec = SPECS[name]
        registry.register(name, spec, FUNCS[name], source="local")
