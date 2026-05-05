"""Tool registry for the workshop-bot agent loop.

Each tool is a Python function plus an Anthropic JSON schema. The loop
dispatches by name. Functions take (deps, **kwargs) and return JSON-
serializable data; serialization happens in the loop.

Capped string lengths keep tool results from blowing the context window.
A single tool result over ~50KB will be truncated when serialized.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import archive, db, pinboard, support_state

logger = logging.getLogger("workshop.tools")

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
    import re
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


def t_read_stored_bookmarks(deps, limit: int = 30) -> list[dict[str, Any]]:
    """Most recent bookmarks already in SQLite (no live API call)."""
    return db.recent_link_candidates(limit=int(limit))


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
}


FUNCS: dict[str, Callable[..., Any]] = {
    "search_archive": t_search_archive,
    "get_issue": t_get_issue,
    "get_section": t_get_section,
    "list_recent_issues": t_list_recent_issues,
    "quote_search": t_quote_search,
    "get_support_state": t_get_support_state,
    "fetch_pinboard": t_fetch_pinboard,
    "read_stored_bookmarks": t_read_stored_bookmarks,
}


# Universal tool set every persona gets unless they explicitly drop one.
UNIVERSAL = (
    "search_archive",
    "get_issue",
    "get_section",
    "list_recent_issues",
    "quote_search",
)


def get(name: str) -> Tool:
    return Tool(name=name, spec=SPECS[name], func=FUNCS[name])


def get_many(names: list[str]) -> list[Tool]:
    return [get(n) for n in names]
