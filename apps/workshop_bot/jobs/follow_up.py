"""``follow-up-sweep`` + Eddy follow-up reads/writes.

Studio has no assistant heartbeat — a cadence tick with nothing real to say is
just noise. This is the one targeted exception: when Eddy (or Jamie) commits
to revisiting something at a future *time* ("I'll check in tomorrow
evening") or when the issue reaches a *number* ("when we get to 387"), it's
recorded in the ``follow_ups`` table; the hourly ``follow-up-sweep`` job
fires the due ones. PASSes silently when nothing's due.

Public surface:
- ``sweep(ctx)``        — the hourly job (cron-only; not exposed as a slash).
- ``list_open(ctx)``    — `/<persona> followup list` — the pending follow-ups.
- ``add(ctx, …)``       — `/<persona> followup add` — schedule one (Jamie).
- ``cancel(ctx, …)``    — `/<persona> followup cancel <id>``.

Triggers — exactly one of:
- ``when``     — an ISO date (``YYYY-MM-DD``, taken as 18:00 that day) or
                 datetime (``YYYY-MM-DDTHH:MM[:SS]``). Any distance.
- ``in_days``  — a relative offset; fires at 18:00 that many days out.
- ``at_issue`` — an issue number; fires once the active in-flight issue has
                 reached it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from ..personas.base import is_pass_response
from ..tools import db
from ..tools.content import context
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.follow_up")

NAME = "follow-up-sweep"

_PERSONA_HOME_CHANNEL = {"eddy": "DISCORD_CHANNEL_EDITORIAL"}
_CONTEXT_BUILDER = {"eddy": context.build_eddy_context}
_DEFAULT_EVENING_HOUR = 18
_MAX_PER_SWEEP = 8  # bound how many we fire in one tick; the rest catch the next sweep

# Inlined (short, no per-persona variation needed) — the user message the
# persona's agent loop runs with when a follow-up comes due. `{note}` /
# `{trigger}` / `{ctx_block}` are filled in.
_FOLLOW_UP_PROMPT = """You committed to following up with Jamie — here's the note you (or he) left:

> {note}

{trigger}

Current state:

{ctx_block}

Post a brief check-in to Jamie now, in your channel — reference what you said you'd revisit, give him your honest current read, and ask if he wants anything from you. Keep it short and natural; this is you keeping a promise, not filing a report. If, looking at where things actually stand, there's genuinely nothing useful to say yet, reply with exactly `PASS` and nothing else."""


# ---------- trigger parsing (shared by the tool and the slash command) ----------


class FollowUpError(ValueError):
    """Bad follow-up arguments — the message is safe to surface."""


def _parse_when(when: str) -> str:
    """Normalize an ISO date/datetime to ``YYYY-MM-DDTHH:MM:SS`` (naive local
    — the sweep compares against ``datetime.now()``). A bare date `YYYY-MM-DD`
    becomes ~6pm that day."""
    raw = str(when).strip().replace(" ", "T")
    bad = FollowUpError(
        f"`when` must be ISO — `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` (got `{when}`). "
        "Compute it from today's date in your context, or use `in_days` for a relative offset."
    )
    if "T" not in raw:  # date only → that day, evening
        try:
            d = date.fromisoformat(raw)
        except ValueError as exc:
            raise bad from exc
        dt = datetime.combine(d, time(_DEFAULT_EVENING_HOUR, 0, 0))
    else:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise bad from exc
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def resolve_trigger(
    *, when: Optional[str] = None, in_days: Optional[int] = None, at_issue: Optional[int] = None
) -> tuple[str, Optional[str], Optional[int]]:
    """Return ``(trigger_kind, due_at, trigger_issue)`` for exactly one of
    the three trigger specs. Raises :class:`FollowUpError` otherwise."""
    given = [
        name
        for name, v in (("when", when), ("in_days", in_days), ("at_issue", at_issue))
        if v not in (None, "")
    ]
    if len(given) != 1:
        raise FollowUpError(
            "Give exactly one of `when` (ISO date/datetime), `in_days`, or `at_issue`."
        )
    if when not in (None, ""):
        return "time", _parse_when(when), None
    if in_days not in (None, ""):
        try:
            n = int(in_days)
        except (TypeError, ValueError) as exc:
            raise FollowUpError(f"`in_days` must be a whole number (got `{in_days}`).") from exc
        if n < 0:
            raise FollowUpError("`in_days` can't be negative.")
        due = datetime.combine(date.today() + timedelta(days=n), time(_DEFAULT_EVENING_HOUR, 0, 0))
        return "time", due.isoformat(timespec="seconds"), None
    try:
        issue_n = int(at_issue)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise FollowUpError(f"`at_issue` must be an issue number (got `{at_issue}`).") from exc
    if issue_n <= 0:
        raise FollowUpError("`at_issue` must be positive.")
    return "issue", None, issue_n


def normalize_persona(persona: Optional[str], *, default: str = "eddy") -> str:
    p = (persona or default).strip().lower()
    if p not in db.FOLLOW_UP_PERSONAS:
        raise FollowUpError(
            f"persona must be one of: {', '.join(db.FOLLOW_UP_PERSONAS)} (got `{p}`)."
        )
    return p


def trigger_desc(row: dict) -> str:
    if row.get("trigger_kind") == "issue":
        return f"when WT{row.get('trigger_issue')} is in flight"
    return f"at {row.get('due_at') or '?'}"


# ---------- create / list / cancel ----------


def create(
    *,
    persona: str,
    note: str,
    when: Optional[str] = None,
    in_days: Optional[int] = None,
    at_issue: Optional[int] = None,
    channel_env: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    """Insert a follow-up; returns its row. Raises :class:`FollowUpError`."""
    note = (note or "").strip()
    if not note:
        raise FollowUpError("Give a `note` — what the follow-up is about.")
    persona = normalize_persona(persona)
    kind, due_at, trigger_issue = resolve_trigger(when=when, in_days=in_days, at_issue=at_issue)
    fid = db.insert_follow_up(
        persona=persona,
        trigger_kind=kind,
        note=note,
        due_at=due_at,
        trigger_issue=trigger_issue,
        channel_env=(channel_env or None),
        created_by=(created_by or None),
    )
    return db.get_follow_up(fid) or {}


async def add(
    ctx: "_base.JobContext",
    *,
    note: str,
    persona: str = "eddy",
    when: str = "",
    in_days: Optional[int] = None,
    at_issue: Optional[int] = None,
    created_by: Optional[str] = None,
) -> "_base.JobResult":
    try:
        row = create(
            persona=persona,
            note=note,
            when=(when or None),
            in_days=in_days,
            at_issue=at_issue,
            created_by=created_by,
        )
    except FollowUpError as exc:
        return _base.JobResult(False, f"❌ {exc}")
    return _base.JobResult(
        True,
        f"⏰ follow-up `#{row['id']}` set — **{row['persona']}** will check in {trigger_desc(row)}:\n> {row['note']}",
        data={"id": row["id"]},
    )


async def list_open(ctx: "_base.JobContext", *, persona: Optional[str] = None) -> "_base.JobResult":
    rows = db.open_follow_ups(persona=(persona or None))
    add_hint = "`/eddy followup add`"
    cancel_hint = "`/eddy followup cancel <id>`"
    if not rows:
        return _base.JobResult(True, f"No pending follow-ups. Add one with {add_hint}.")
    lines = [f"**Pending follow-ups** ({len(rows)}):"]
    for r in rows:
        lines.append(
            f'`#{r["id"]}` · **{r["persona"]}** · {trigger_desc(r)} · "{(r["note"] or "").strip()}"'
        )
    lines.append(f"{cancel_hint} to drop one.")
    return _base.JobResult(True, "\n".join(lines))


async def cancel(
    ctx: "_base.JobContext", *, followup_id: int, persona: Optional[str] = None
) -> "_base.JobResult":
    row = db.get_follow_up(int(followup_id))
    if row is None:
        return _base.JobResult(False, f"❌ no follow-up `#{followup_id}`.")
    if row.get("cancelled_at"):
        return _base.JobResult(True, f"Follow-up `#{followup_id}` is already cancelled.")
    if row.get("fired_at"):
        return _base.JobResult(
            True, f"Follow-up `#{followup_id}` already fired — nothing to cancel."
        )
    if not db.cancel_follow_up(int(followup_id), persona=(persona or None)):
        return _base.JobResult(
            False, f"❌ couldn't cancel `#{followup_id}` (not yours / already closed?)."
        )
    return _base.JobResult(
        True, f"🗑️ follow-up `#{followup_id}` cancelled.", data={"id": int(followup_id)}
    )


# ---------- the hourly sweep ----------


def _persona_context_block(persona: str) -> str:
    builder = _CONTEXT_BUILDER.get(persona)
    if builder is None:
        return "_(no context available)_"
    try:
        ctx_dict = builder()
    except Exception as exc:  # noqa: BLE001
        logger.warning("follow-up-sweep: %s context build failed: %s", persona, exc)
        return "_(context unavailable)_"
    try:
        return context.render_block(ctx_dict)
    except Exception:  # noqa: BLE001
        return "_(context unavailable)_"


async def sweep(ctx: "_base.JobContext") -> "_base.JobResult":
    # Whole-job lock so a slow run (8 follow-ups × LLM call each) can't
    # overlap the next hourly cron fire. ``mark_follow_up_fired`` is the
    # idempotency gate, but without the lock both runs pay for LLM
    # work and may race to post check-ins before the marking lands.
    try:
        with _base.job_lock([f"job:{NAME}"], NAME):
            return await _sweep_locked(ctx)
    except _base.JobLocked as exc:
        logger.info("follow-up-sweep: skipping — already running (%s)", exc.holder_desc)
        return _base.JobResult(
            True,
            f"follow-up-sweep already running ({exc.holder_desc}); skipped.",
        )


async def _sweep_locked(ctx: "_base.JobContext") -> "_base.JobResult":
    now_iso = datetime.now().isoformat(timespec="seconds")
    win = db.get_active_issue_window()
    active_issue = int(win["issue_number"]) if win else None
    due = db.due_follow_ups(now_iso=now_iso, active_issue=active_issue)
    if not due:
        return _base.JobResult(True, "(follow-up-sweep: nothing due)")

    fired = 0
    posted = 0
    skipped = 0
    for row in due[:_MAX_PER_SWEEP]:
        persona = row["persona"]
        channel_env = row.get("channel_env") or _PERSONA_HOME_CHANNEL.get(
            persona, "DISCORD_CHANNEL_EDITORIAL"
        )
        bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, persona, channel_env)
        if bot is None:
            logger.warning("follow-up-sweep: leaving #%s open — %s", row["id"], reason)
            skipped += 1
            continue
        trig = (
            f"It's now {now_iso}."
            if row["trigger_kind"] == "time"
            else f"WT{active_issue} is now the in-flight issue."
        )
        user_msg = _FOLLOW_UP_PROMPT.format(
            note=(row["note"] or "").strip(),
            trigger=trig,
            ctx_block=_persona_context_block(persona),
        )
        reply = ""
        try:
            with db.AgentRun(persona, trigger="follow-up") as agent_run:
                reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                agent_run.record_meta(_meta)
                agent_run.records_written = 1 if (reply and reply.strip()) else 0
        except Exception:  # noqa: BLE001
            logger.exception("follow-up-sweep: #%s (%s) agent run failed", row["id"], persona)
            # Leave it open — try again next sweep.
            skipped += 1
            continue
        db.mark_follow_up_fired(int(row["id"]))
        fired += 1
        if reply and reply.strip() and not is_pass_response(reply):
            if await ctx.post(channel, reply.strip(), persona=persona):
                posted += 1
        else:
            logger.info(
                "follow-up-sweep: #%s (%s) — agent PASSed, nothing posted", row["id"], persona
            )

    note = f"follow-up-sweep: {fired} fired ({posted} posted)"
    if skipped:
        note += f", {skipped} left open"
    leftover = len(due) - len(due[:_MAX_PER_SWEEP])
    if leftover:
        note += f", {leftover} deferred to the next sweep"
    return _base.JobResult(True, note + ".", data={"fired": fired, "posted": posted})
