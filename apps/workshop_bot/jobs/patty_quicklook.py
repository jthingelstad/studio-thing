"""``/patty {progress,nonprofit,supporters}`` — read-only quick looks.

No LLM calls; these are operator-facing summaries of what
``build_patty_context``, ``support_state``, and Stripe already surface.
Useful when Jamie wants a quick read without firing a compose-cta or
@-mentioning Patty.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..systems.stripe import client as stripe_client
from ..tools import support_state
from ..tools.content import context
from . import _base

logger = logging.getLogger("workshop.jobs.patty_quicklook")


# ---------- /patty progress ----------

async def progress(ctx: "_base.JobContext") -> "_base.JobResult":
    """Current goal + live progress + days-to-anniversary pacing."""
    pctx = await asyncio.to_thread(context.build_patty_context)
    goal = pctx.get("active_goal")
    if not goal:
        return _base.JobResult(
            True,
            "No active goal. Open one with `/patty goal set <kind> <value>`.",
            data={"has_active_goal": False},
        )

    kind = goal.get("kind") or "?"
    target = goal.get("target_value")
    current = goal.get("current_progress")
    remaining = goal.get("remaining")
    started_at = goal.get("started_at") or "?"

    bits = [
        f"🎯 **Active goal:** {kind} → {target}",
        f"_(started {started_at})_",
    ]
    if current is None:
        bits.append("Current progress: _(unavailable — Buttondown/Stripe lookup failed)_")
    else:
        try:
            pct = f"{round(100 * float(current) / float(target))}%" if target else "—"
        except (TypeError, ValueError, ZeroDivisionError):
            pct = "—"
        bits.append(f"Current: **{current}** ({pct})")
        if remaining is not None:
            bits.append(f"Remaining: **{remaining}**")

    bits.append(
        f"_Anniversary:_ {pctx.get('next_anniversary')} "
        f"({pctx.get('days_to_anniversary')} days · "
        f"{pctx.get('expected_issues_before_anniversary')} more issues)"
    )

    recent = pctx.get("recent_achieved_goals") or []
    if recent:
        bits.append("\n**Recently hit:**")
        for g in recent[:3]:
            dur = g.get("duration_days")
            tail = f" ({dur}d)" if isinstance(dur, int) else ""
            bits.append(f"- {g.get('kind')} → {g.get('target')} ({g.get('achieved')}{tail})")

    return _base.JobResult(True, "\n".join(bits),
                           data={"has_active_goal": True, "context": pctx})


# ---------- /patty nonprofit ----------

async def nonprofit(ctx: "_base.JobContext") -> "_base.JobResult":
    """Current nonprofit details + last few past nonprofits."""
    try:
        state = await asyncio.to_thread(support_state.read)
    except Exception as exc:  # noqa: BLE001
        logger.warning("patty_quicklook nonprofit: support_state read failed: %s", exc)
        return _base.JobResult(False, f"❌ couldn't read support state: `{type(exc).__name__}: {exc}`")

    support = state.get("support") or {}
    cur = support.get("current") or {}
    past = support.get("past") or []

    if not cur:
        return _base.JobResult(True, "_(no current nonprofit set — check `apps/site/_data/support.json`)_",
                               data={"current": None, "past": past})

    name = cur.get("nonprofit") or cur.get("short_name") or "?"
    year_label = cur.get("year_label") or cur.get("year") or "?"
    description = cur.get("description") or ""

    bits = [f"🏛️ **{name}** _({year_label})_"]
    if description:
        bits.append(description)
    if past:
        bits.append("")
        bits.append("**Past nonprofits:**")
        for p in past[:5]:
            ylabel = p.get("year_label") or p.get("year") or "?"
            pname = p.get("nonprofit") or p.get("short_name") or "?"
            bits.append(f"- {ylabel}: {pname}")

    return _base.JobResult(True, "\n".join(bits), data={"current": cur, "past": past})


# ---------- /patty supporters ----------

async def supporters(ctx: "_base.JobContext", *, days: int = 14) -> "_base.JobResult":
    """Recent Stripe activity over a trailing window — YTD total + last few donations."""
    try:
        ytd = await asyncio.to_thread(stripe_client.year_to_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("patty_quicklook supporters: year_to_date failed: %s", exc)
        ytd = {}
    try:
        recent = await asyncio.to_thread(stripe_client.recent_donations, limit=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("patty_quicklook supporters: recent_donations failed: %s", exc)
        recent = []

    year = ytd.get("year") or "?"
    count = ytd.get("count")
    total_usd = ytd.get("total_usd")
    average_usd = ytd.get("average_usd")

    bits = [f"💝 **Supporters — last {int(days)}d / year {year}**"]
    if total_usd is not None:
        bits.append(
            f"YTD: **${total_usd:,.0f}** ({count or 0} donations, avg ${average_usd or 0:,.2f})"
        )
    else:
        bits.append("_(Stripe YTD unavailable)_")

    if recent:
        # Filter to the trailing window where possible.
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
        windowed: list[dict] = []
        for d in recent:
            created = d.get("created") or d.get("created_at")
            try:
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                elif isinstance(created, (int, float)):
                    dt = datetime.fromtimestamp(int(created), tz=timezone.utc)
                else:
                    continue
            except (TypeError, ValueError):
                continue
            if dt >= cutoff:
                windowed.append({**d, "_dt": dt})
        windowed.sort(key=lambda x: x.get("_dt") or cutoff, reverse=True)
        if windowed:
            bits.append("")
            bits.append(f"**Last {len(windowed)} in {int(days)}d window:**")
            for d in windowed[:6]:
                amount = d.get("amount_usd")
                handle = d.get("donor_handle") or d.get("name_hash") or "?"
                when = d.get("_dt").strftime("%b %d") if d.get("_dt") else "?"
                amt = f"${amount:,.0f}" if isinstance(amount, (int, float)) else "?"
                bits.append(f"- {when} · {amt} · `{handle[:8]}`")
        else:
            bits.append(f"\n_(No donations in the last {int(days)} days.)_")

    return _base.JobResult(True, "\n".join(bits), data={"ytd": ytd, "recent_count": len(recent)})
