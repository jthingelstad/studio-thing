"""Read-only Scout production feed.

This is the machine-readable bridge for personal-ops consumers such as Otto.
Scout remains the source of truth: the feed projects the current production
state into stable task facts, but it does not mutate Studio Thing state.

The top-level feed is production-type based on purpose. Newsletter is the first
mapper; future Scout-owned surfaces such as blog posts or podcast episodes can
register mappers behind the same contract without changing consumers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

from ..tools import db
from . import production_state

SCHEMA_VERSION = 1
CENTRAL = ZoneInfo("America/Chicago")

ProductionMapper = Callable[[], list[dict[str, Any]]]


def _now() -> datetime:
    return datetime.now(tz=CENTRAL)


def _local_due(date_iso: str | None, *, at: time = time(hour=7)) -> Optional[str]:
    if not date_iso:
        return None
    try:
        d = datetime.strptime(str(date_iso)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return datetime.combine(d, at, tzinfo=CENTRAL).isoformat(timespec="seconds")


def _task_key(production_type: str, production_id: str, phase: str, slug: str) -> str:
    return f"studio-thing:{production_type}:{production_id}:{phase}:{slug}"


def _task(
    *,
    production_type: str,
    production_id: str,
    phase: str,
    slug: str,
    title: str,
    status: str,
    priority: str = "normal",
    estimate_minutes: int = 60,
    due_at: Optional[str] = None,
    reason: str,
    source_command: str,
    owner: str = "jamie",
) -> dict[str, Any]:
    return {
        "task_key": _task_key(production_type, production_id, phase, slug),
        "title": title,
        "owner": owner,
        "status": status,
        "priority": priority,
        "estimate_minutes": int(estimate_minutes),
        "due_at": due_at,
        "reason": reason,
        "source_command": source_command,
    }


def _section_needs_work(section: Mapping[str, Any]) -> bool:
    return bool(section.get("placeholder")) or not bool(section.get("present"))


def _production_status(tasks: list[dict[str, Any]]) -> str:
    actionable = {str(t.get("status")) for t in tasks}
    if "open" in actionable or "ready" in actionable:
        return "open"
    if "blocked" in actionable:
        return "blocked"
    return "complete"


def _newsletter_build_tasks(state: Mapping[str, Any], *, due_at: Optional[str]) -> list[dict[str, Any]]:
    n = int(state["issue_number"])
    production_id = f"WT{n}"
    phase = "build"
    tasks: list[dict[str, Any]] = []

    if not state.get("intro_present"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="intro",
            title=f"Write {production_id} intro",
            status="open",
            priority="high",
            estimate_minutes=60,
            due_at=due_at,
            reason="The Build card is missing intro.md.",
            source_command="/eddy edit intro",
        ))

    if not state.get("cover_present"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="cover",
            title=f"Add {production_id} cover",
            status="open",
            priority="high",
            estimate_minutes=30,
            due_at=due_at,
            reason="The Build card is missing cover art.",
            source_command="/scout issue update",
        ))

    labels = {"notable": "Notable", "journal": "Journal", "brief": "Briefly"}
    for slug, label in labels.items():
        section = (state.get("sections") or {}).get(slug, {})
        if not _section_needs_work(section):
            continue
        tag = "placeholder" if section.get("placeholder") else "empty"
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug=f"section-{slug}",
            title=f"Finish {production_id} {label}",
            status="open",
            priority="high",
            estimate_minutes=60,
            due_at=due_at,
            reason=f"The {label} section is {tag} on the Build card.",
            source_command="/scout issue update",
        ))

    open_comments = int(state.get("open_comments") or 0)
    if open_comments:
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="review-notes",
            title=f"Resolve {production_id} editorial review notes",
            status="open",
            priority="normal",
            estimate_minutes=30,
            due_at=due_at,
            reason=f"The Build card shows {open_comments} open review note"
                   f"{'' if open_comments == 1 else 's'}.",
            source_command="/scout issue update",
        ))

    build_ready = bool(state.get("build_ready"))
    tasks.append(_task(
        production_type="newsletter",
        production_id=production_id,
        phase=phase,
        slug="mark-built",
        title=f"Mark {production_id} built in Scout",
        status="ready" if build_ready else "blocked",
        priority="high",
        estimate_minutes=30,
        due_at=due_at,
        reason=("Required content is present; Scout can move the issue to Publish."
                if build_ready else
                "Blocked until the required Build content is present."),
        source_command="/scout issue built",
    ))

    return tasks


def _newsletter_publish_tasks(state: Mapping[str, Any], *, due_at: Optional[str]) -> list[dict[str, Any]]:
    n = int(state["issue_number"])
    production_id = f"WT{n}"
    phase = "publish"
    gates = state.get("gates") or {}
    tasks: list[dict[str, Any]] = []

    if state.get("recompose_needed"):
        missing = []
        if state.get("thesis_failed"):
            missing.append("thesis")
        if state.get("echoes_failed"):
            missing.append("Echoes")
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="recompose",
            title=f"Retry {production_id} publish composes",
            status="ready",
            priority="high",
            estimate_minutes=30,
            due_at=due_at,
            reason=f"Publish is missing {', '.join(missing) or 'required compose output'}.",
            source_command="Publish card: Retry composes",
        ))

    if not state.get("subject") or not state.get("description"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="metadata",
            title=f"Choose {production_id} subject and description",
            status="open",
            priority="high",
            estimate_minutes=30,
            due_at=due_at,
            reason="The Publish card is missing subject and/or description.",
            source_command="/eddy issue subject",
        ))

    if not state.get("haiku_present"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="haiku",
            title=f"Write {production_id} haiku",
            status="open",
            priority="normal",
            estimate_minutes=30,
            due_at=due_at,
            reason="The Publish card is missing the haiku.",
            source_command="/eddy issue haiku",
        ))

    if not state.get("cta_files"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="cta",
            title=f"Choose {production_id} CTA framing",
            status="open",
            priority="normal",
            estimate_minutes=30,
            due_at=due_at,
            reason="The Publish card has no CTA/thanks atom selected.",
            source_command="/patty cta",
        ))

    if not state.get("email_shipped"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="publish-buttondown",
            title=f"Publish {production_id} to Buttondown",
            status="ready" if gates.get(production_state.BTN_EMAIL) else "blocked",
            priority="high",
            estimate_minutes=30,
            due_at=due_at,
            reason=("Email gate is ready on the Publish card."
                    if gates.get(production_state.BTN_EMAIL) else
                    "Email is blocked by missing Publish requirements."),
            source_command="/scout issue publish buttondown",
        ))

    if not state.get("audio_shipped"):
        tasks.append(_task(
            production_type="newsletter",
            production_id=production_id,
            phase=phase,
            slug="publish-audio",
            title=f"Publish {production_id} podcast audio",
            status="ready" if gates.get(production_state.BTN_PODCAST) else "blocked",
            priority="normal",
            estimate_minutes=90,
            due_at=due_at,
            reason=("Podcast/audio gate is ready on the Publish card."
                    if gates.get(production_state.BTN_PODCAST) else
                    "Podcast/audio is blocked until issue content exists."),
            source_command="/scout issue publish audio",
        ))

    tasks.append(_task(
        production_type="newsletter",
        production_id=production_id,
        phase=phase,
        slug="publish-website",
        title=f"Publish {production_id} to the website",
        status="ready" if gates.get(production_state.BTN_WEBSITE) else "blocked",
        priority="high",
        estimate_minutes=30,
        due_at=due_at,
        reason=("Website gate is ready after Buttondown stamped the issue URL."
                if gates.get(production_state.BTN_WEBSITE) else
                "Website publish waits for Buttondown so the archive has the canonical URL."),
        source_command="/scout issue publish website",
    ))

    put_to_bed_ready = bool(state.get("email_shipped") and state.get("audio_shipped"))
    tasks.append(_task(
        production_type="newsletter",
        production_id=production_id,
        phase=phase,
        slug="put-to-bed",
        title=f"Put {production_id} to bed",
        status="ready" if put_to_bed_ready else "blocked",
        priority="high",
        estimate_minutes=30,
        due_at=due_at,
        reason=("Email and audio are shipped; close the active production window."
                if put_to_bed_ready else
                "Blocked until the issue's main publish legs are shipped."),
        source_command="/scout issue put-to-bed",
    ))

    return tasks


def _newsletter_production(window: Mapping[str, Any]) -> dict[str, Any]:
    """Project one in-flight newsletter window into a production dict."""
    n = int(window["issue_number"])
    production_id = f"WT{n}"
    phase = str(window.get("phase") or "build").lower()
    due_at = _local_due(window.get("pub_date"))

    if phase == "publish":
        state = production_state.publish_state(n, window=window)
        tasks = _newsletter_publish_tasks(state, due_at=due_at)
    else:
        phase = "build"
        state = production_state.build_state(n, window=window)
        tasks = _newsletter_build_tasks(state, due_at=due_at)

    return {
        "production_type": "newsletter",
        "production_id": production_id,
        "title": f"Weekly Thing {production_id}",
        "phase": phase,
        "due_at": due_at,
        "source": "studio-thing/apps/workshop_bot",
        "status": _production_status(tasks),
        "tasks": tasks,
    }


def newsletter_productions() -> list[dict[str, Any]]:
    """Project every in-flight newsletter window into a production (concurrent)."""
    return [_newsletter_production(w) for w in db.list_active_issue_windows()]


def _generic_productions(production_type: str) -> list[dict[str, Any]]:
    """Project active rows of a generic production type (article / podcast /
    project) from the registry. These have no per-phase task breakdown yet —
    status is derived from the phase (complete at the terminal phase)."""
    from ..tools.content import production_types as ptypes

    out: list[dict[str, Any]] = []
    for p in db.list_productions(production_type=production_type, status="active"):
        phase = str(p.get("phase") or "")
        out.append({
            "production_type": production_type,
            "production_id": p["id"],
            "title": p.get("title") or p["id"],
            "phase": phase,
            "due_at": _local_due(p.get("due_at")),
            "source": "studio-thing/apps/workshop_bot",
            "status": "complete" if ptypes.is_terminal(production_type, phase) else "open",
            "tasks": [],
        })
    return out


def article_productions() -> list[dict[str, Any]]:
    return _generic_productions("article")


def podcast_productions() -> list[dict[str, Any]]:
    return _generic_productions("podcast")


def project_productions() -> list[dict[str, Any]]:
    return _generic_productions("project")


PRODUCTION_MAPPERS: dict[str, ProductionMapper] = {
    "newsletter": newsletter_productions,
    "article": article_productions,
    "podcast": podcast_productions,
    "project": project_productions,
}


def build_feed(
    *,
    mappers: Optional[Mapping[str, ProductionMapper]] = None,
    generated_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Build the generic Scout production feed."""
    active_mappers = dict(mappers or PRODUCTION_MAPPERS)
    productions: list[dict[str, Any]] = []
    for production_type in sorted(active_mappers):
        for production in active_mappers[production_type]():
            productions.append(production)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or _now()).isoformat(timespec="seconds"),
        "productions": productions,
    }
