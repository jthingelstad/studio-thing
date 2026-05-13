"""Operator pokes at the goals + campaigns ledgers — small, no-LLM jobs.

These don't touch S3, Discord, or the agent loop; they just record a
decision Jamie made. Wired onto the slash surface as ``/workshop goal
set`` / ``/workshop goal done`` / ``/workshop campaign sunset`` /
``/workshop campaign copy`` / ``/workshop campaign edit`` (internal job
names: ``set-goal`` / ``goal-achieved`` / ``campaign-sunset`` /
``campaign-copy`` / ``campaign-edit``).

- ``set-goal <kind> <value> [notes]`` — open a new active milestone for
  Patty. Refuses if one's already active (the ``goals`` table allows only
  one row with ``achieved_at IS NULL``) — close it with ``goal-achieved``
  first.
- ``goal-achieved [notes]`` — mark the active milestone hit (today). The
  note, if given, is appended to whatever was recorded when the goal was
  set.
- ``campaign-sunset <name>`` — flip a campaign's status to ``sunset`` so
  ``daily-metrics`` stops polling it.
- ``campaign-copy <name> <text>`` — set (or, with empty text, clear) the
  promo copy that ran in a campaign's placement, so performance can be
  read against the creative.
- ``campaign-edit <name> [ref] [started_at] [ends_at] [expected_signups]
  [expected_traffic] [notes] [copy]`` — change details on an existing
  campaign in place (the name is immutable; ``status`` flips via
  ``campaign-sunset``). Only the fields you pass are touched.
"""

from __future__ import annotations

import logging

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.ops")

GOAL_KINDS = ("members", "dollars")


async def set_goal(
    ctx: "_base.JobContext", *, kind: str, value: int, notes: str | None = None
) -> "_base.JobResult":
    kind = (kind or "").strip().lower()
    if kind not in GOAL_KINDS:
        return _base.JobResult(
            False, f"❌ goal kind must be one of: {', '.join(GOAL_KINDS)} — got `{kind}`."
        )
    try:
        value = int(value)
    except (TypeError, ValueError):
        return _base.JobResult(False, f"❌ goal value must be a whole number — got `{value}`.")
    if value <= 0:
        return _base.JobResult(False, "❌ goal value must be positive.")
    active = db.get_active_goal()
    if active is not None:
        return _base.JobResult(
            False,
            f"❌ there's already an active goal — **{active['target_kind']} → "
            f"{active['target_value']}** (since {active.get('started_at', '?')}). "
            "Mark it hit with `/workshop goal done` first.",
        )
    notes = (notes or "").strip() or None
    db.insert_goal(target_kind=kind, target_value=value, notes=notes)
    return _base.JobResult(
        True,
        f"🎯 new goal: **{kind} → {value}**" + (f" — {notes}" if notes else "") + ".",
        data={"target_kind": kind, "target_value": value},
    )


async def goal_achieved(ctx: "_base.JobContext", *, notes: str | None = None) -> "_base.JobResult":
    active = db.get_active_goal()
    if active is None:
        return _base.JobResult(
            False,
            "❌ no active goal to mark achieved. Set one with "
            "`/workshop goal set <kind> <value>`.",
        )
    notes = (notes or "").strip() or None
    merged = active.get("notes") or None
    if notes:
        merged = f"{merged} · {notes}" if merged else notes
    ok = db.mark_goal_achieved(int(active["id"]), notes=merged)
    if not ok:
        return _base.JobResult(False, "❌ couldn't mark the goal achieved (already closed?).")
    return _base.JobResult(
        True,
        f"✅ goal hit: **{active['target_kind']} → {active['target_value']}**"
        + (f" — {notes}" if notes else "")
        + ". Set the next one with `/workshop goal set <kind> <value>`.",
        data={"goal_id": active["id"]},
    )


async def campaign_copy(ctx: "_base.JobContext", *, name: str, copy: str | None = None) -> "_base.JobResult":
    name = (name or "").strip()
    if not name:
        return _base.JobResult(False, "❌ give the campaign name.")
    c = db.get_campaign(name)
    if c is None:
        return _base.JobResult(
            False, f"❌ no campaign named `{name}` — see `/workshop campaign report`."
        )
    text = (str(copy).strip() or None) if copy is not None else None
    db.set_campaign_copy(name, text)
    if text is None:
        return _base.JobResult(True, f"🧹 cleared the copy for `{name}`.", data={"name": name, "has_copy": False})
    preview = text if len(text) <= 280 else text[:277] + "…"
    return _base.JobResult(
        True,
        f"📝 copy recorded for `{name}` ({len(text)} chars):\n\n{preview}",
        data={"name": name, "has_copy": True},
    )


def _campaign_summary(c: dict) -> str:
    es, et = c.get("expected_signups"), c.get("expected_traffic")
    bits = [f"ref `{c.get('ref')}`", f"status `{c.get('status')}`", f"started {c.get('started_at') or '?'}"]
    if c.get("ends_at"):
        bits.append(f"ends {c['ends_at']}")
    bits.append(f"expect {es if es is not None else '—'} signups / {et if et is not None else '—'} visits")
    if c.get("copy"):
        bits.append("has copy")
    if c.get("notes"):
        bits.append(f"notes: {c['notes']}")
    return " · ".join(bits)


async def campaign_edit(
    ctx: "_base.JobContext",
    *,
    name: str,
    ref: str | None = None,
    started_at: str | None = None,
    ends_at: str | None = None,
    expected_signups: int | None = None,
    expected_traffic: int | None = None,
    notes: str | None = None,
    copy: str | None = None,
) -> "_base.JobResult":
    name = (name or "").strip()
    if not name:
        return _base.JobResult(False, "❌ give the campaign name.")
    not_found = f"❌ no campaign named `{name}` — see `/workshop campaign report` (or `campaign add` it first)."

    def _txt(v):
        return (str(v).strip() or None) if v is not None else None

    changes = {
        "ref": _txt(ref),
        "started_at": _txt(started_at),
        "ends_at": _txt(ends_at),
        "expected_signups": expected_signups,
        "expected_traffic": expected_traffic,
        "notes": _txt(notes),
        "copy": _txt(copy),
    }
    applied = {k: v for k, v in changes.items() if v is not None}
    if not applied:
        c = db.get_campaign(name)
        if c is None:
            return _base.JobResult(False, not_found)
        return _base.JobResult(
            True,
            f"`{name}` — {_campaign_summary(c)}\n_(no changes given — pass at least one field to edit.)_",
            data={"name": name},
        )
    updated = db.update_campaign(name, **applied)
    if updated is None:
        return _base.JobResult(False, not_found)
    return _base.JobResult(
        True,
        f"✏️ updated {', '.join('`' + k + '`' for k in applied)} on `{name}`.\n`{name}` — {_campaign_summary(updated)}",
        data={"name": name},
    )


async def campaign_sunset(ctx: "_base.JobContext", *, name: str) -> "_base.JobResult":
    name = (name or "").strip()
    if not name:
        return _base.JobResult(False, "❌ give the campaign name to sunset.")
    c = db.get_campaign(name)
    if c is None:
        return _base.JobResult(
            False, f"❌ no campaign named `{name}` — see `/workshop campaign report`."
        )
    if c.get("status") == "sunset":
        return _base.JobResult(True, f"`{name}` is already sunset — nothing to do.")
    db.set_campaign_status(name, "sunset")
    return _base.JobResult(
        True,
        f"🌅 campaign `{name}` (ref `{c.get('ref')}`) marked **sunset** — "
        "`daily-metrics` will stop polling it.",
        data={"name": name},
    )
