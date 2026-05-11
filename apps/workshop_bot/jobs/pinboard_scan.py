"""``pinboard-scan`` — Linky's twice-daily Pinboard pass.

Four lanes per scan (all closed-loop — Pinboard ↔ ``#research`` ↔ Jamie):

- **A — popular review.** Pull Pinboard's popular feed; surface ≤1 item
  Jamie would actually want; never auto-add to the toread queue; dedup
  against ``pinboard_popular_seen``.
- **B — toread tending.** 3–5 WT-aware assessments of items in the queue.
- **C — Briefly capture.** When a toread item belongs in Briefly, ask
  Jamie for a one-liner; his reply IS the blurb — ``capture_blurb`` writes
  the description, tags ``_brief``, removes ``toread``.
- **D — read-length + queue-depth.** Estimate per-item read length; watch
  the toread pile against the deadline; alert if it's piling up.

Active condition: an issue window is set AND today ∈ ``[start_date, end_date]``.
Otherwise PASS (no post). Linky's own prompt is responsible for the
finer "nothing to do this scan → PASS" judgment. (A locked issue —
``final.md`` exists — has no effect on Linky; the answer is just "no work".)
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..tools import anthropic_client, context, db
from . import _base

logger = logging.getLogger("workshop.jobs.pinboard_scan")

NAME = "pinboard-scan"


def _in_window(window: dict, today) -> bool:
    try:
        sd = datetime.strptime(window["start_date"], "%Y-%m-%d").date()
        ed = datetime.strptime(window["end_date"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return sd <= today <= ed


def _is_pass(text: str) -> bool:
    if not text:
        return True
    import re as _re
    strip = _re.compile(r"[\s*_`~\"'()<>\[\].!?,;:\\\-—–]+")
    if strip.sub("", text).upper() == "PASS":
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return bool(lines) and strip.sub("", lines[-1]).upper() == "PASS"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(True, "PASS — no active issue window.", data={"posted": False})
    today = datetime.now().date()
    if not _in_window(window, today):
        return _base.JobResult(
            True,
            f"PASS — today ({today}) is outside the issue window "
            f"[{window['start_date']}, {window['end_date']}].",
            data={"posted": False},
        )

    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return _base.JobResult(True, "(no Discord — pinboard-scan skipped)", data={"posted": False})
    linky = team.bots.get("linky")
    if linky is None or getattr(linky, "user", None) is None:
        return _base.JobResult(True, "(Linky unavailable — pinboard-scan skipped)", data={"posted": False})

    linky_ctx = context.build_linky_context(ref_date=today)
    try:
        scan_prompt = anthropic_client.load_prompt("linky-pinboard-scan")
    except OSError as exc:
        logger.warning("pinboard-scan: prompt missing: %s", exc)
        return _base.JobResult(False, f"pinboard-scan prompt missing: {exc}", data={"posted": False})
    user_msg = f"{context.render_block(linky_ctx)}\n\n{scan_prompt}"

    with db.AgentRun("linky", trigger="pinboard-scan") as agent_run:
        answer, _meta = await linky.core(latest=user_msg, history=[], model=None)
        agent_run.records_written = 0 if (not answer or _is_pass(answer)) else 1

    if not answer or _is_pass(answer):
        return _base.JobResult(True, "Linky: PASS (nothing to surface this scan).", data={"posted": False})
    posted = await ctx.post("DISCORD_CHANNEL_RESEARCH", answer, persona="linky")
    return _base.JobResult(
        True,
        "Linky posted a pinboard-scan to #research." if posted else "(couldn't post Linky's scan)",
        data={"posted": bool(posted)},
    )
