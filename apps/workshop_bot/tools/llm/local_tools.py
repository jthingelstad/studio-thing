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

from .. import archive_lookup, content_store, db, issue_items as issue_items_mod, s3, support_state, web
from ..content import archive, draft, issue
from .tool_registry import ToolRegistry, active_persona, active_react_target
from ._specs import SPECS

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
    # the top-of-module surface and matches how compose_echoes imports it.
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


# ---------- archive_lookup (DB-backed exact lookups over the historical
#            issues + issue_links tables, seeded by the one-shot backfill
#            and kept current by /eddy issue put-to-bed) ----------

def t_archive_lookup_get_issue(deps, number: int) -> dict[str, Any] | str:
    """Structured metadata for one shipped issue from the historical
    record (workshop.db ``issues`` row). Sub-millisecond SQL lookup.
    Returns None if the issue hasn't been filed (still in flight or not
    backfilled). Distinct from ``archive__get_issue`` which reads the
    markdown body; use this when you need numbers (word_count, link_count,
    audio metadata, era) rather than prose."""
    try:
        n = int(number)
    except (TypeError, ValueError):
        return f"could not parse issue number from {number!r}"
    row = archive_lookup.get_issue(n)
    return row if row is not None else f"no record for WT{n} (not yet filed)"


def t_archive_lookup_find_by_domain(
    deps, domain: str, limit: int = 50,
) -> list[dict[str, Any]]:
    """Issues that cite ``domain`` in any link, newest first. Use when
    Jamie asks 'has Jamie linked to this site before?' or 'how often
    does Daring Fireball show up?'."""
    return archive_lookup.find_issues_by_domain(domain, limit=int(limit))


def t_archive_lookup_find_in_year(deps, year: int) -> list[dict[str, Any]]:
    """All issues shipped in ``year``, newest first."""
    return archive_lookup.find_issues_in_year(int(year))


def t_archive_lookup_link_history(deps, url: str) -> list[dict[str, Any]]:
    """Every shipping of an exact URL. Forward-looking — Pinboard
    currently prevents re-pinning, so the answer is usually an empty list
    today; this will matter when workshop hosts link commentary directly."""
    return archive_lookup.link_history(url)


def t_archive_lookup_domain_history(deps, domain: str) -> dict[str, Any]:
    """Aggregate snapshot for ``domain``: link_count, issue_count,
    first/last issue numbers + dates, plus the latest 5 issues that
    cited it. Empty dict if the domain isn't in the corpus."""
    return archive_lookup.domain_history(domain)


def t_archive_lookup_recent(deps, n: int = 10) -> list[dict[str, Any]]:
    """The ``n`` most recently shipped issues by number — sourced from the
    DB record, so carries word_count + audio + era columns the corpus
    version doesn't. Use when you need a quick 'what just shipped?'."""
    return archive_lookup.recent_issues(int(n))


def t_archive_lookup_stats(deps) -> dict[str, Any]:
    """Corpus-wide totals: issue count, link count, domain count, total
    words, audio coverage %. The numbers Marky and the home page report."""
    return archive_lookup.aggregate_stats()


def t_archive_lookup_list_links(
    deps, issue_number: int, section: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Every link row for one issue, ordered by (section, position).
    Pass ``section`` to filter to 'notable' or 'briefly' only."""
    return archive_lookup.list_issue_links(int(issue_number), section=section)


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
# active window via the ``/scout issue start`` slash command; agents
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
    """List the per-issue workspace — authored content (DB) plus the generated
    artifacts + binaries in S3."""
    try:
        n = int(issue_number)
        listing = s3.list_issue(n)
        objs = list(listing.get("objects", []))
        have = {o.get("filename") for o in objs}
        for name in content_store.list_issue(n):
            if name not in have:
                objs.append({"filename": name, "key": f"db/content/{name}", "size": None})
        listing["objects"] = objs
        return listing
    except s3.S3PathError as exc:
        return {"error": str(exc)}


def t_workspace_read(deps, issue_number: int, filename: str) -> dict[str, Any]:
    """Read one authored file for the issue. Authored content (intro.md,
    cover.json, metadata.json, cta-N.md, …) comes from the DB content store;
    other names (generated artifacts) fall through to S3. Filename must be a
    bare component (no slashes, no '..')."""
    try:
        n = int(issue_number)
        if content_store.is_atom_name(filename):
            body = content_store.read_issue(n, filename)
            if body is None:
                return {"found": False, "name": filename}
            return {"found": True, "name": filename, "text": body}
        return s3.read_issue_file(n, filename)
    except s3.S3PathError as exc:
        return {"error": str(exc)}


def t_workspace_write(
    deps, issue_number: int, filename: str, content: str
) -> dict[str, Any]:
    """Write one authored file for the issue. Authored content (e.g. ``intro.md``,
    ``metadata.json``, ``cta-1.md``) is stored in the DB content store — the same
    rows the web project page edits; other names fall through to S3. Filename
    must be a bare component."""
    try:
        n = int(issue_number)
        if content_store.is_atom_name(filename):
            content_store.write_issue(n, filename, content, by="agent")
            return {"name": filename, "written": True, "size": len(content or "")}
        return s3.write_issue_file(n, filename, content)
    except s3.S3PathError as exc:
        return {"error": str(exc)}


# ---------- campaigns (Marky's ad-placement ledger) ----------


def t_campaigns_list(
    deps, status: Optional[str] = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Read the campaign ledger. Default returns every campaign — live
    and sunset — newest first. Status filter accepts ``'live'`` or
    ``'sunset'``."""
    rows = db.list_campaigns(status=status)
    n = max(1, min(int(limit), 200))
    return rows[:n]


def t_campaigns_get(deps, name: str) -> dict[str, Any]:
    """Read one campaign by name. Returns the row plus its most recent
    metric snapshot (``latest_metric``: signups, traffic, ran_at) or
    ``{"error": …}`` if no such campaign."""
    row = db.get_campaign(name)
    if not row:
        return {"error": f"unknown campaign {name!r}"}
    return {**row, "latest_metric": db.latest_campaign_metric(name)}


def t_campaigns_history(
    deps, name: str, limit: int = 30
) -> dict[str, Any]:
    """Recent metric rows for one campaign, newest first. Use to read a
    trajectory — when a placement landed, how it tapered, whether it
    plateaued. Returns ``{"error": …}`` if no such campaign."""
    if db.get_campaign(name) is None:
        return {"error": f"unknown campaign {name!r}"}
    return {
        "name": name,
        "metrics": db.recent_campaign_metrics(name, limit=int(limit)),
    }


def t_campaigns_set_actual_signups(
    deps, name: str, signups: int
) -> dict[str, Any]:
    """Write the current attribution-realised signups count for a
    campaign. ``daily-metrics`` updates this column after each poll, so
    in the routine flow there's no need to call this tool. Use it for
    manual corrections (you ran ``buttondown__attribution_summary``
    yourself and noticed the stored value is stale) or for ad-hoc
    placements outside the daily-metrics path. Returns the updated row,
    or ``{"error": …}`` if no such campaign."""
    n = int(signups)
    if n < 0:
        return {"error": "signups must be ≥ 0"}
    if not db.set_actual_signups(name, n):
        return {"error": f"unknown campaign {name!r}"}
    row = db.get_campaign(name) or {}
    return {"ok": True, "campaign": row}


# ---------- currently (per-issue ## Currently section) ----------

# The mutating tools (`set`, `clear`, `add_type`, `reorder`) write the
# DB change and return; they do NOT refire `update-draft`. The daily
# 17:00 CT run (or a manual `/scout issue update`) projects the new
# state into the rendered draft.


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
            return {"error": "no active issue window — Jamie starts one via /scout issue start"}
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
    paraphrase). The new value lands in the next scheduled
    ``update-draft`` (or a manual one); this tool writes the DB and
    returns, it doesn't fire the rebuild itself.

    If the ``label`` isn't a known canonical type, this errors — call
    ``currently__add_type`` first when Jamie mentions a brand-new type
    (e.g. "Printing")."""
    n = _active_issue_number()
    if n is None:
        return {"error": "no active issue window — Jamie starts one via /scout issue start"}
    try:
        res = db.currently_set_entry(n, label, value)
    except db.CurrentlyError as exc:
        return {"error": str(exc)}
    return {
        "ok": True,
        "issue_number": n,
        "label": res["label"],
        "position": res["position"],
    }


def t_currently_clear(deps, label: str) -> dict[str, Any]:
    """Delete one Currently entry for the active in-flight issue.
    Renumbers remaining entries contiguously. The change lands in the
    next scheduled (or manual) ``update-draft``."""
    n = _active_issue_number()
    if n is None:
        return {"error": "no active issue window — Jamie starts one via /scout issue start"}
    deleted = db.currently_clear_entry(n, label)
    return {
        "ok": True,
        "issue_number": n,
        "label": (label or "").strip(),
        "deleted": deleted,
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
    grouping, strongest first, or a deliberate shuffle. The new order
    lands in the next scheduled (or manual) ``update-draft``."""
    n = _active_issue_number()
    if n is None:
        return {"error": "no active issue window — Jamie starts one via /scout issue start"}
    if not isinstance(labels, list) or not labels:
        return {"error": "`labels` must be a non-empty list of label strings"}
    try:
        applied = db.currently_reorder(n, labels)
    except db.CurrentlyError as exc:
        return {"error": str(exc)}
    return {
        "ok": True,
        "issue_number": n,
        "applied_order": applied,
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
            "error": "No active issue window. Jamie sets it via /scout issue start."
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
        "closed": bool(row.get("closed_at")),
        "closed_at": row.get("closed_at"),
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



# ---------- productions registry (any production type) ----------

def t_productions_list(deps, production_type: str = None, status: str = None) -> dict[str, Any]:
    """List productions of any type (newsletter / article / podcast / project)."""
    rows = db.list_productions(production_type=production_type, status=status, limit=100)
    return {"productions": [
        {"id": r["id"], "type": r["production_type"], "title": r["title"],
         "phase": r["phase"], "status": r["status"], "due_at": r.get("due_at")}
        for r in rows
    ]}


def t_productions_get(deps, production_id: str) -> dict[str, Any]:
    """Full detail for one production by id (e.g. 'WT350', 'ART7', 'POD3')."""
    row = db.get_production(production_id)
    if not row:
        return {"error": f"no such production: {production_id}"}
    return row


def t_productions_create(deps, production_type: str, title: str, due_at: str = None) -> dict[str, Any]:
    """Create a production of any type. For newsletters prefer the start-issue
    flow; this is for articles / podcasts / projects."""
    try:
        row = db.create_production(production_type=production_type, title=title,
                                   due_at=due_at, created_by="agent")
    except ValueError as exc:
        return {"error": str(exc)}
    return {"ok": True, "id": row["id"], "type": row["production_type"], "phase": row["phase"]}


def t_productions_set_phase(deps, production_id: str, phase: str) -> dict[str, Any]:
    """Move a production to a phase in its type's vocabulary."""
    row = db.get_production(production_id)
    if not row:
        return {"error": f"no such production: {production_id}"}
    try:
        if row["production_type"] == "newsletter":
            db.set_issue_phase(int(row["seq"]), phase)  # mirrors the registry
        else:
            db.set_production_phase(production_id, phase, updated_by="agent")
    except ValueError as exc:
        return {"error": str(exc)}
    return {"ok": True, "id": production_id, "phase": phase}


# ---------- production content (any production, DB-backed) ----------

def t_production_content_read(deps, production_id: str, name: str) -> dict[str, Any]:
    """Read an authored content block of any production (e.g. ART7/'body.md')."""
    body = content_store.get(production_id, name)
    if body is None:
        return {"found": False, "name": name}
    return {"found": True, "name": name, "text": body}


def t_production_content_write(deps, production_id: str, name: str, body: str) -> dict[str, Any]:
    """Write an authored content block. NOTE: never write Jamie's prose for
    him — use this for structure/notes/metadata, not to draft his sentences."""
    content_store.set(production_id, name, body, by="agent")
    return {"ok": True, "name": name, "size": len(body or "")}


def t_production_content_list(deps, production_id: str) -> dict[str, Any]:
    """List the content block names present for a production."""
    return {"names": content_store.list(production_id)}


# ---------- production tasks (the state engine's interactive half) ----------

def t_tasks_list(deps, production_id: str, status: str = None) -> dict[str, Any]:
    """The added/assigned tasks on a production (the board)."""
    return {"tasks": db.list_tasks(production_id, status=status)}


def t_tasks_add(deps, production_id: str, title: str, owner: str = "jamie",
                phase: str = None, detail: str = None) -> dict[str, Any]:
    """Add a task to a production. owner ∈ jamie/scout/eddy/linky/marky/patty."""
    try:
        row = db.add_task(production_id, title, owner=owner, phase=phase,
                          detail=detail, created_by="agent")
    except ValueError as exc:
        return {"error": str(exc)}
    return {"ok": True, "task_id": row["id"], "owner": row["owner"], "status": row["status"]}


def t_tasks_update(deps, task_id: int, status: str = None, owner: str = None,
                   title: str = None) -> dict[str, Any]:
    """Update a task — claim it (owner=<you>, status='doing'), reassign, retitle,
    or change status (todo/doing/done/blocked)."""
    try:
        row = db.update_task(int(task_id), status=status, owner=owner, title=title)
    except ValueError as exc:
        return {"error": str(exc)}
    if not row:
        return {"error": f"no such task: {task_id}"}
    return {"ok": True, "task_id": row["id"], "owner": row["owner"], "status": row["status"]}


def t_tasks_complete(deps, task_id: int) -> dict[str, Any]:
    """Mark a task done."""
    row = db.complete_task(int(task_id))
    if not row:
        return {"error": f"no such task: {task_id}"}
    return {"ok": True, "task_id": row["id"], "status": "done"}


FUNCS: dict[str, Callable[..., Any]] = {
    "archive__search": t_search_archive,
    "archive__retrieve": t_retrieve_archive,
    "archive__get_issue": t_get_issue,
    "archive__get_section": t_get_section,
    "archive__list_recent": t_list_recent_issues,
    "archive__quote_search": t_quote_search,
    "archive_lookup__get_issue": t_archive_lookup_get_issue,
    "archive_lookup__find_by_domain": t_archive_lookup_find_by_domain,
    "archive_lookup__find_in_year": t_archive_lookup_find_in_year,
    "archive_lookup__link_history": t_archive_lookup_link_history,
    "archive_lookup__domain_history": t_archive_lookup_domain_history,
    "archive_lookup__recent": t_archive_lookup_recent,
    "archive_lookup__stats": t_archive_lookup_stats,
    "archive_lookup__list_links": t_archive_lookup_list_links,
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
    "campaigns__list": t_campaigns_list,
    "campaigns__get": t_campaigns_get,
    "campaigns__history": t_campaigns_history,
    "campaigns__set_actual_signups": t_campaigns_set_actual_signups,
    "productions__list": t_productions_list,
    "productions__get": t_productions_get,
    "productions__create": t_productions_create,
    "productions__set_phase": t_productions_set_phase,
    "production_content__read": t_production_content_read,
    "production_content__write": t_production_content_write,
    "production_content__list": t_production_content_list,
    "tasks__list": t_tasks_list,
    "tasks__add": t_tasks_add,
    "tasks__update": t_tasks_update,
    "tasks__complete": t_tasks_complete,
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
