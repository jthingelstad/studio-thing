"""Tool registry for the workshop-bot agent loop.

Each tool is a Python function plus an Anthropic JSON schema. The loop
dispatches by name. Functions take (deps, **kwargs) and return JSON-
serializable data; serialization happens in the loop.

Capped string lengths keep tool results from blowing the context window.
A single tool result over ~50KB will be truncated when serialized.
"""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import (
    archive,
    db,
    inbox,
    issue,
    persona_s3,
    s3,
    support_state,
    web,
)
from ..systems._base import SystemServer

logger = logging.getLogger("workshop.tools")

# The agent loop sets this before each tool execution so memory tools
# (`remember`, `recall`) can attribute notes to the calling persona
# without leaning on a shared, mutable Deps object.
active_persona: ContextVar[str] = ContextVar("active_persona", default="unknown")

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


# ---------- current issue resolver ----------

# Canonical implementation lives in `tools/issue.py` so the registry can
# expose it under the dotted ``issue.current_number`` namespace; we
# re-export it here for backward compatibility with the flat
# ``FUNCS`` / ``SPECS`` lookup pattern.
t_current_issue_number = issue.t_current_issue_number


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


# ---------- S3 issue workspace (universal) ----------

def t_s3_list_issue_workspaces(deps) -> dict[str, Any]:
    """List every issue workspace folder in S3 with file counts and
    last-modified timestamps. The highest issue number is the issue
    currently being assembled."""
    return s3.list_workspaces()


def t_s3_list_issue(deps, issue_number: int) -> dict[str, Any]:
    """List the per-issue files in the S3 workspace
    (``s3://files.thingelstad.com/weekly-thing/issues/{N}/``)."""
    try:
        return s3.list_issue(int(issue_number))
    except s3.S3PathError as exc:
        return {"error": str(exc)}


def t_s3_read_issue_file(deps, issue_number: int, filename: str) -> dict[str, Any]:
    """Read one file from the per-issue S3 workspace. Text only — binary
    objects (photos) are reported but not returned. Filename must be a
    bare component (no slashes, no '..')."""
    try:
        return s3.read_issue_file(int(issue_number), filename)
    except s3.S3PathError as exc:
        return {"error": str(exc)}


def t_s3_write_issue_file(
    deps, issue_number: int, filename: str, content: str
) -> dict[str, Any]:
    """Write one file to the per-issue S3 workspace. Use for files that
    need to be picked up by the iOS Shortcuts assemble pipeline (e.g.
    ``patty-cta.json``, ``marky-meta.json``, ``linky-curation.md``).
    256KB max per file. Allowed extensions: md, txt, json, yaml, yml,
    csv, html. Filename must be a bare component."""
    try:
        return s3.write_issue_file(int(issue_number), filename, content)
    except s3.S3PathError as exc:
        return {"error": str(exc)}


# ---------- S3 persona scratchpad (universal) ----------

def t_persona_list(deps, prefix: Optional[str] = None) -> dict[str, Any]:
    """List files in this persona's private scratchpad on S3. Optionally
    scope to a sub-prefix (e.g. ``"campaigns"``). Returns paths relative
    to the persona root."""
    try:
        return persona_s3.list_persona(active_persona.get(), prefix=prefix)
    except persona_s3.S3PathError as exc:
        return {"error": str(exc)}


def t_persona_read(deps, path: str) -> dict[str, Any]:
    """Read one file from this persona's private scratchpad. ``path`` is
    relative to the persona root and may contain subdirectories
    (``campaigns/dd-2026-05-15.json``, ``notes/2026-05-08.md``). Text
    only — binary objects are reported but not returned."""
    try:
        return persona_s3.read_persona_file(active_persona.get(), path)
    except persona_s3.S3PathError as exc:
        return {"error": str(exc)}


def t_persona_write(deps, path: str, content: str) -> dict[str, Any]:
    """Write one file under this persona's private scratchpad. ``path`` is
    relative to the persona root and may contain subdirectories. 256KB
    max per file. Allowed extensions: md, txt, json, yaml, yml, csv,
    html. Use this to maintain campaign ledgers, drafts, multi-step
    notes — anything that needs to survive across hosts and process
    restarts."""
    try:
        return persona_s3.write_persona_file(active_persona.get(), path, content)
    except persona_s3.S3PathError as exc:
        return {"error": str(exc)}


# ---------- specs (Anthropic format) ----------

SPECS: dict[str, dict[str, Any]] = {
    "archive.search": {
        "name": "archive.search",
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
    "archive.get_issue": {
        "name": "archive.get_issue",
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
    "archive.get_section": {
        "name": "archive.get_section",
        "description": (
            "Pull one named section from one issue (e.g. 'Notable', 'Briefly', 'Featured', 'Microposts'). "
            "Cheaper than archive.get_issue when you only need that section."
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
    "archive.list_recent": {
        "name": "archive.list_recent",
        "description": (
            "Last N issues by number (newest first), with date, subject, topics, and abstract. "
            "Use to ground 'the latest', 'last few', 'recent' references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "default 10"}},
        },
    },
    "archive.quote_search": {
        "name": "archive.quote_search",
        "description": (
            "Exact substring search across issue bodies. Use to verify a specific phrase or product name "
            "actually appears in the archive — do not infer presence from archive.search hits alone."
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
    "site.support_state": {
        "name": "site.support_state",
        "description": (
            "Current support program state: this year's nonprofit, supporter count, amount raised, "
            "past nonprofits. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "web.fetch_url": {
        "name": "web.fetch_url",
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
    "memory.remember": {
        "name": "memory.remember",
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
    "memory.recall": {
        "name": "memory.recall",
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
    "memory.forget": {
        "name": "memory.forget",
        "description": (
            "Mark a memory note as resolved (the todo is done) or stale (no longer "
            "applicable). Notes are never hard-deleted; resolved/stale notes drop out of "
            "default memory.recall results."
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
    "issue.current_number": {
        "name": "issue.current_number",
        "description": (
            "Resolve the in-flight issue number — the one Jamie is assembling "
            "this week. **The in-flight issue is NOT in your archive corpus** "
            "(archive.search / archive.get_issue won't find it; it's a draft). "
            "This tool combines two signals: the highest workspace folder in S3 "
            "and the highest published issue in the corpus. Use when Jamie says "
            "'the current issue', 'this weekend's issue', or 'the one I'm working on'. "
            "No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "s3_issues.list_workspaces": {
        "name": "s3_issues.list_workspaces",
        "description": (
            "List every issue workspace folder in S3 (under "
            "s3://files.thingelstad.com/weekly-thing/issues/). Returns each issue's "
            "number, file count, and most-recent modification time. The highest "
            "issue number is the issue currently being assembled — call "
            "`issue.current_number` for the resolved working number, or use this "
            "when you need the per-folder modification times. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "s3_issues.list": {
        "name": "s3_issues.list",
        "description": (
            "List the per-issue files in the S3 workspace at "
            "s3://files.thingelstad.com/weekly-thing/issues/{N}/. This is where "
            "Jamie's iOS Shortcuts read/write draft.md, photo.jpg, photo-caption.txt, "
            "metadata.json, and where you write outputs the assemble pipeline picks up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"issue_number": {"type": "integer"}},
            "required": ["issue_number"],
        },
    },
    "s3_issues.read_file": {
        "name": "s3_issues.read_file",
        "description": (
            "Read one file from the per-issue S3 workspace. Text only — binary "
            "objects like photo.jpg are reported but their bytes aren't returned. "
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
    "s3_issues.write_file": {
        "name": "s3_issues.write_file",
        "description": (
            "Write one file to the per-issue S3 workspace. Use to drop outputs "
            "the Shortcuts assemble pipeline picks up — e.g. patty-cta.json, "
            "marky-meta.json, linky-curation.md. 256KB cap per file. Allowed "
            "extensions: md, txt, json, yaml, yml, csv, html. The path is "
            "scoped to weekly-thing/issues/{issue_number}/ — you can't write "
            "outside that prefix."
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
    "s3_personas.list": {
        "name": "s3_personas.list",
        "description": (
            "List files in your private S3 scratchpad. This is your own "
            "persistent file space — separate from the per-issue workspace, "
            "and not visible to other personas. Optionally pass a `prefix` "
            "to scope to a sub-folder (e.g. \"campaigns\", \"notes\")."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "Optional sub-folder under your scratchpad to list.",
                },
            },
        },
    },
    "s3_personas.read_file": {
        "name": "s3_personas.read_file",
        "description": (
            "Read one file from your private S3 scratchpad. The `path` is "
            "relative to your scratchpad root and may contain subdirectories "
            "(e.g. \"campaigns/dd-2026-05-15.json\", \"notes/2026-05-08.md\"). "
            "Text only — binary objects are reported but not returned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "s3_personas.write_file": {
        "name": "s3_personas.write_file",
        "description": (
            "Write one file under your private S3 scratchpad. Use this to "
            "maintain campaign ledgers, drafts, multi-step thinking, anything "
            "that needs to survive across hosts and restarts. The `path` is "
            "relative to your scratchpad root and may contain subdirectories. "
            "256KB cap per file. Allowed extensions: md, txt, json, yaml, yml, "
            "csv, html. Other personas cannot read or overwrite your files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
}


FUNCS: dict[str, Callable[..., Any]] = {
    "archive.search": t_search_archive,
    "archive.get_issue": t_get_issue,
    "archive.get_section": t_get_section,
    "archive.list_recent": t_list_recent_issues,
    "archive.quote_search": t_quote_search,
    "site.support_state": t_get_support_state,
    "web.fetch_url": t_fetch_url,
    "issue.current_number": t_current_issue_number,
    "memory.remember": t_remember,
    "memory.recall": t_recall,
    "memory.forget": t_forget_note,
    "s3_issues.list_workspaces": t_s3_list_issue_workspaces,
    "s3_issues.list": t_s3_list_issue,
    "s3_issues.read_file": t_s3_read_issue_file,
    "s3_issues.write_file": t_s3_write_issue_file,
    "s3_personas.list": t_persona_list,
    "s3_personas.read_file": t_persona_read,
    "s3_personas.write_file": t_persona_write,
}


def get(name: str) -> Tool:
    return Tool(name=name, spec=SPECS[name], func=FUNCS[name])


def get_many(names: list[str]) -> list[Tool]:
    return [get(n) for n in names]


# ---------- ToolRegistry ----------


class ToolRegistry:
    """Composes external-system tools and local helpers into one namespace.

    Tool names follow ``<system>.<action>`` (dotted) — ``archive.search``,
    ``memory.remember``, ``inbox.post``, ``buttondown.list_subscribers``.
    Local helpers live in ``FUNCS`` / ``SPECS`` keyed by their dotted name;
    external systems are added by ``register_system(server)`` from
    ``apps/workshop_bot/systems/``.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        spec: dict[str, Any],
        func: Callable[..., Any],
        source: str = "local",
    ) -> None:
        if name in self._tools:
            raise ValueError(f"duplicate tool registration: {name!r}")
        spec_with_name = dict(spec)
        spec_with_name["name"] = name
        self._tools[name] = Tool(
            name=name, spec=spec_with_name, func=func, source=source
        )

    def register_system(self, server: SystemServer) -> None:
        for tdef in server.list_tools():
            full = f"{server.name}.{tdef.name}"
            spec = {
                "name": full,
                "description": tdef.description,
                "input_schema": tdef.input_schema,
            }
            self.register(full, spec, tdef.handler, source=f"system:{server.name}")

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all_specs(self) -> list[dict[str, Any]]:
        return [dict(t.spec) for t in self._tools.values()]

    def all_names(self) -> list[str]:
        return list(self._tools.keys())

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
        token = active_persona.set(persona)
        try:
            return tool.func(deps, **(args or {}))
        finally:
            active_persona.reset(token)


def register_local_helpers(registry: ToolRegistry) -> None:
    """Register the local-helper tools (everything in ``FUNCS`` / ``SPECS``
    plus the inbox tools).

    External systems (``buttondown``, ``pinboard``, ``stripe``,
    ``tinylytics``) are added separately via ``registry.register_system``
    from ``bot.py``.
    """
    for name in sorted(FUNCS):
        spec = SPECS[name]
        registry.register(name, spec, FUNCS[name], source="local")
    for name, spec in inbox.tool_specs().items():
        registry.register(name, spec, inbox.tool_handlers()[name], source="local")
