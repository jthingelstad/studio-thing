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

from . import archive, buttondown, db, persona_s3, pinboard, s3, support_state, tinylytics, web

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


# ---------- Linky ----------

def t_fetch_pinboard(deps, count: int = 50) -> list[dict[str, Any]]:
    """Live fetch from Pinboard (and persist to SQLite)."""
    raw = pinboard.recent_posts(count=int(count))
    posts = [pinboard.normalize_post(p) for p in raw]
    for p in posts:
        db.upsert_link_candidate(
            url=p["url"],
            title=p["title"],
            description=p["description"],
            pinboard_tags=p["tags"],
            pinboard_added=p["added"],
        )
    return posts


def t_fetch_pinboard_unread(deps, limit: int = 100, tag: Optional[str] = None) -> list[dict[str, Any]]:
    """Pinboard items Jamie has marked ``to read`` — the queue Linky is here to
    help drain. Persists to SQLite like ``fetch_pinboard``."""
    raw = pinboard.all_unread(limit=int(limit), tag=tag)
    posts = [pinboard.normalize_post(p) for p in raw]
    for p in posts:
        db.upsert_link_candidate(
            url=p["url"],
            title=p["title"],
            description=p["description"],
            pinboard_tags=p["tags"],
            pinboard_added=p["added"],
        )
    return posts


def t_read_stored_bookmarks(deps, limit: int = 30) -> list[dict[str, Any]]:
    """Most recent bookmarks already in SQLite (no live API call)."""
    rows = db.recent_link_candidates(limit=int(limit))
    for row in rows:
        url = row.get("url") or ""
        if url:
            row["pinboard_url"] = pinboard.bookmark_url(url)
    return rows


def t_fetch_pinboard_popular(deps, limit: int = 30) -> list[dict[str, Any]]:
    """Pinboard's site-wide popular feed — the discovery surface Jamie scans
    manually. Use to suggest interesting items he might not have seen yet."""
    return pinboard.popular(limit=int(limit))


def t_fetch_url(deps, url: str, max_chars: int = 12_000) -> dict[str, Any]:
    """Fetch a URL and return readable text. Use for Linky to actually read what
    a bookmark is about before recommending it."""
    return web.fetch_text(url, max_chars=int(max_chars))


# ---------- current issue resolver ----------

def t_current_issue_number(deps) -> dict[str, Any]:
    """Resolve which issue is being assembled this week.

    Combines two signals:
      - the highest issue folder in S3 (where Jamie's iOS Shortcuts stage drafts)
      - the highest published issue in the archive corpus (the reference baseline)

    The working issue is **not** in the archive corpus — it's a draft. Use
    this when Jamie says "the current issue", "this weekend's issue", or
    "the one I'm working on" so you don't accidentally treat the most
    recently *published* issue as the in-flight one.
    """
    try:
        ws = s3.list_workspaces()
        s3_max = ws.get("current_issue_number")
    except Exception as exc:  # noqa: BLE001
        s3_max = None
        ws = {"error": f"{type(exc).__name__}: {exc}"}

    published_latest = None
    if deps is not None and getattr(deps, "corpus", None) is not None:
        published_latest = deps.corpus.latest_issue_number

    # If S3 has a workspace newer than the archive, that's the in-flight issue.
    # Otherwise the in-flight issue is published_latest + 1 and no workspace
    # has been created yet.
    if s3_max is not None and (published_latest is None or s3_max > published_latest):
        working = s3_max
        has_workspace = True
    elif published_latest is not None:
        working = published_latest + 1
        has_workspace = False
    else:
        working = None
        has_workspace = False

    return {
        "working_issue_number": working,
        "has_s3_workspace": has_workspace,
        "s3_max_workspace": s3_max,
        "published_latest_issue": published_latest,
        "note": (
            "The working issue is the in-flight draft — it is NOT in your "
            "archive corpus yet. search_archive / get_issue won't find it."
        ),
    }


# ---------- Marky ----------

def t_fetch_tinylytics(deps, days: int = 7) -> dict[str, Any]:
    """Trailing-window engagement summary: top pages, referrers, custom events."""
    return tinylytics.safe_summary(days=int(days))


def t_fetch_buttondown_subscribers(
    deps, kind: str = "recent", limit: int = 25
) -> dict[str, Any]:
    """Subscriber activity. ``kind`` is one of:
      - ``"recent"``       — newest subscribers
      - ``"unsubscribed"`` — recent unsubscribes/churn
      - ``"counts"``       — total/premium/unsubscribed counts only
    Email addresses are hashed before they ever reach the LLM.
    """
    kind = (kind or "recent").lower()
    if kind == "counts":
        return {"counts": buttondown.counts()}
    if kind == "unsubscribed":
        return {"kind": "unsubscribed", "subscribers": buttondown.recent_unsubscribes(limit=int(limit))}
    return {"kind": "recent", "subscribers": buttondown.recent_subscribers(limit=int(limit))}


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
    "search_archive": {
        "name": "search_archive",
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
    "get_issue": {
        "name": "get_issue",
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
    "get_section": {
        "name": "get_section",
        "description": (
            "Pull one named section from one issue (e.g. 'Notable', 'Briefly', 'Featured', 'Microposts'). "
            "Cheaper than get_issue when you only need that section."
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
    "list_recent_issues": {
        "name": "list_recent_issues",
        "description": (
            "Last N issues by number (newest first), with date, subject, topics, and abstract. "
            "Use to ground 'the latest', 'last few', 'recent' references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "default 10"}},
        },
    },
    "quote_search": {
        "name": "quote_search",
        "description": (
            "Exact substring search across issue bodies. Use to verify a specific phrase or product name "
            "actually appears in the archive — do not infer presence from search_archive hits alone."
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
    "get_support_state": {
        "name": "get_support_state",
        "description": (
            "Current support program state: this year's nonprofit, supporter count, amount raised, "
            "past nonprofits. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "fetch_pinboard": {
        "name": "fetch_pinboard",
        "description": (
            "Live-fetch the most recent N bookmarks from Pinboard and persist them to SQLite. "
            "Costs an HTTP round trip — use only when the user explicitly wants fresh data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer", "description": "default 50, max 100"}},
        },
    },
    "read_stored_bookmarks": {
        "name": "read_stored_bookmarks",
        "description": (
            "Read the most recent N bookmarks already stored in SQLite (no live API call). "
            "Use this before reaching for fetch_pinboard."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "default 30"}},
        },
    },
    "fetch_pinboard_unread": {
        "name": "fetch_pinboard_unread",
        "description": (
            "Live-fetch bookmarks Jamie has marked as `to read` on Pinboard. This is "
            "the working queue for what could go in the next issue. Persists to SQLite."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "default 100, max 1000"},
                "tag": {"type": "string", "description": "optional Pinboard tag filter"},
            },
        },
    },
    "fetch_pinboard_popular": {
        "name": "fetch_pinboard_popular",
        "description": (
            "Pinboard's site-wide popular bookmarks feed — the discovery surface "
            "Jamie scans manually. Use to suggest items he might not have seen yet, "
            "or to ground 'what's resonating across Pinboard right now'. Returns "
            "title, url, description, posted_by."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "default 30"},
            },
        },
    },
    "fetch_url": {
        "name": "fetch_url",
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
    "fetch_tinylytics": {
        "name": "fetch_tinylytics",
        "description": (
            "Trailing-window engagement summary for weekly.thingelstad.com: "
            "stats, top pages, referrers, and custom events (donate, membership). "
            "Use to ground 'what's working lately'. Returns partial data even if "
            "individual endpoints fail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "trailing days; default 7"},
            },
        },
    },
    "fetch_buttondown_subscribers": {
        "name": "fetch_buttondown_subscribers",
        "description": (
            "Subscriber activity from Buttondown. `kind`: 'recent' (newest signups), "
            "'unsubscribed' (recent churn), or 'counts' (totals only). Email addresses "
            "are hashed before they ever reach this tool — never raw emails."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["recent", "unsubscribed", "counts"]},
                "limit": {"type": "integer", "description": "default 25"},
            },
        },
    },
    "remember": {
        "name": "remember",
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
    "recall": {
        "name": "recall",
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
    "forget_note": {
        "name": "forget_note",
        "description": (
            "Mark a memory note as resolved (the todo is done) or stale (no longer "
            "applicable). Notes are never hard-deleted; resolved/stale notes drop out of "
            "default recall results."
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
    "current_issue_number": {
        "name": "current_issue_number",
        "description": (
            "Resolve the in-flight issue number — the one Jamie is assembling "
            "this week. **The in-flight issue is NOT in your archive corpus** "
            "(search_archive / get_issue won't find it; it's a draft). This tool "
            "combines two signals: the highest workspace folder in S3 and the "
            "highest published issue in the corpus. Use when Jamie says 'the "
            "current issue', 'this weekend's issue', or 'the one I'm working on'. "
            "No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "s3_list_issue_workspaces": {
        "name": "s3_list_issue_workspaces",
        "description": (
            "List every issue workspace folder in S3 (under "
            "s3://files.thingelstad.com/weekly-thing/issues/). Returns each issue's "
            "number, file count, and most-recent modification time. The highest "
            "issue number is the issue currently being assembled — call "
            "`current_issue_number` for the resolved working number, or use this "
            "when you need the per-folder modification times. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "s3_list_issue": {
        "name": "s3_list_issue",
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
    "s3_read_issue_file": {
        "name": "s3_read_issue_file",
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
    "s3_write_issue_file": {
        "name": "s3_write_issue_file",
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
    "persona_list": {
        "name": "persona_list",
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
    "persona_read": {
        "name": "persona_read",
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
    "persona_write": {
        "name": "persona_write",
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
    "search_archive": t_search_archive,
    "get_issue": t_get_issue,
    "get_section": t_get_section,
    "list_recent_issues": t_list_recent_issues,
    "quote_search": t_quote_search,
    "get_support_state": t_get_support_state,
    "fetch_pinboard": t_fetch_pinboard,
    "fetch_pinboard_unread": t_fetch_pinboard_unread,
    "fetch_pinboard_popular": t_fetch_pinboard_popular,
    "read_stored_bookmarks": t_read_stored_bookmarks,
    "fetch_url": t_fetch_url,
    "current_issue_number": t_current_issue_number,
    "fetch_tinylytics": t_fetch_tinylytics,
    "fetch_buttondown_subscribers": t_fetch_buttondown_subscribers,
    "remember": t_remember,
    "recall": t_recall,
    "forget_note": t_forget_note,
    "s3_list_issue_workspaces": t_s3_list_issue_workspaces,
    "s3_list_issue": t_s3_list_issue,
    "s3_read_issue_file": t_s3_read_issue_file,
    "s3_write_issue_file": t_s3_write_issue_file,
    "persona_list": t_persona_list,
    "persona_read": t_persona_read,
    "persona_write": t_persona_write,
}


# Universal tool set every persona gets unless they explicitly drop one.
# Memory, the per-issue S3 workspace, and the in-flight issue resolver
# are all universal — every persona needs to know what week it is and
# read/write artifacts that flow through Jamie's assemble pipeline.
UNIVERSAL = (
    "search_archive",
    "get_issue",
    "get_section",
    "list_recent_issues",
    "quote_search",
    "remember",
    "recall",
    "forget_note",
    "current_issue_number",
    "s3_list_issue_workspaces",
    "s3_list_issue",
    "s3_read_issue_file",
    "s3_write_issue_file",
    "persona_list",
    "persona_read",
    "persona_write",
)


def get(name: str) -> Tool:
    return Tool(name=name, spec=SPECS[name], func=FUNCS[name])


def get_many(names: list[str]) -> list[Tool]:
    return [get(n) for n in names]
