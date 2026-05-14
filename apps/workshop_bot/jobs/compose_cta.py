"""``compose-cta`` (Patty) — the per-issue membership CTA(s).

Patty decides on 0, 1, or 2 CTAs for the issue and drafts 1–2 framings
per slot, in **Thingy's** voice (the public-facing librarian persona —
not Jamie's first person, not salesy). Reads ``final.md`` (or ``draft.md``),
recent supporting-member activity, the current goal + progress (via the
dynamic context block), and the last 3–4 issues' ``publish.md`` files for
arc continuity. Posts proposals to ``#supporters``; on Jamie's pick per
slot, writes ``cta-1.md`` / ``cta-2.md`` with ``placement:`` YAML
frontmatter. Optional for ship (Patty may choose 0 CTAs).
"""

from __future__ import annotations

import asyncio
import logging

from ..tools import anthropic_client, context, db, s3
from ..tools.discord import interaction
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_cta")

NAME = "compose-cta"

# How many prior issues' `publish.md` to include for arc continuity (so
# the model can see Patty's recent framings) and how many chars to take
# from each one. Each excerpt is glommed into the user message, so the
# product (count × excerpt cap) is what bounds the arc-context size.
_ARC_LOOKBACK_COUNT = 4
_ARC_EXCERPT_CAP = 4_000


def _recent_publish_excerpts(issue_number: int, count: int = _ARC_LOOKBACK_COUNT) -> str:
    out: list[str] = []
    for prev in range(issue_number - 1, issue_number - 1 - count, -1):
        if prev < 1:
            break
        res = s3.read_issue_file(prev, "publish.md")
        if res.get("found") and isinstance(res.get("text"), str) and res["text"].strip():
            out.append(f"--- WT{prev} publish.md ---\n{res['text'][:_ARC_EXCERPT_CAP]}")
    return "\n\n".join(out) if out else "(no prior publish.md files available)"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])
    # Off-loop: final_or_draft hits S3.
    body = await asyncio.to_thread(_llm_job.final_or_draft, n)
    if not body.strip():
        return _base.JobResult(False, f"❌ no `final.md`/`draft.md` for WT{n} yet.")
    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "patty", "DISCORD_CHANNEL_SUPPORTERS")
    if bot is None:
        return _base.JobResult(True, f"(compose-cta skipped — {reason})", data={"posted": False})

    # Lock both slots up front so a concurrent re-fire bounces. (No
    # refresh-in-loop here — Patty composes the full CTA set in one pass;
    # for fresh framings Jamie re-fires the whole job.)
    assets = [f"{n}/cta-1.md", f"{n}/cta-2.md"]
    try:
        with _base.job_lock(assets, NAME):
            base_prompt = anthropic_client.load_prompt("patty-compose-cta")
            # Off-loop: build_patty_context hits Stripe / Buttondown, and
            # _recent_publish_excerpts does up to four sequential S3 reads.
            # Wrap both so a slow round-trip doesn't stall the gateway.
            patty_ctx = await asyncio.to_thread(context.build_patty_context)
            arc_excerpts = await asyncio.to_thread(_recent_publish_excerpts, n)
            user_msg = (
                f"{context.render_block(patty_ctx)}\n\n{base_prompt}\n\n"
                f"---\n\nRecent issues (for arc continuity — your previous CTAs are in these):\n\n"
                f"{arc_excerpts}\n\n"
                f"---\n\nThis issue (WT{n}):\n\n```markdown\n{body[:_llm_job.ISSUE_BODY_CAP]}\n```"
            )
            with db.AgentRun("patty", trigger="compose-cta") as agent_run:
                reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                agent_run.records_written = 1
            data = _llm_job.parse_json_payload(reply)
            ctas = (data or {}).get("ctas")
            if not isinstance(ctas, list):
                return _base.JobResult(False, "compose-cta: model didn't return a parseable `ctas` list.")
            if len(ctas) == 0:
                await _llm_job.try_send(channel, f"💝 Patty's call for WT{n}: **no CTA this issue.**")
                return _base.JobResult(True, f"compose-cta for WT{n}: 0 CTAs (Patty's call).",
                                       data={"issue_number": n, "ctas_written": 0, "posted": True})

            written = 0
            for idx, cta in enumerate(ctas[:2]):
                if not isinstance(cta, dict):
                    continue
                placement = str(cta.get("placement") or _llm_job.DEFAULT_PLACEMENT).strip()
                if placement not in _llm_job.PLACEMENTS:
                    placement = _llm_job.DEFAULT_PLACEMENT
                framings = [str(f).strip() for f in (cta.get("framings") or []) if str(f).strip()][:2]
                if not framings:
                    continue
                pretty = [f"> {f}" for f in framings]
                slot_label = f"Slot {idx + 1} (placement: `{placement}`)"
                pick = await interaction.await_choice(
                    bot, channel, pretty,
                    prompt=f"💝 Patty's CTA proposal for WT{n} — {slot_label}:",
                    allow_refresh=True,
                )
                if pick == "refresh":
                    # Re-running the whole job is the clean way to refresh; ask Jamie to re-fire.
                    await _llm_job.try_send(
                        channel,
                        f"(For fresh CTA framings, re-fire `/patty cta` — "
                        f"slot {idx + 1} for WT{n} left unwritten.)",
                    )
                    continue
                if pick is None or pick >= len(framings):
                    await _llm_job.try_send(channel, f"(No pick for slot {idx + 1} of WT{n} — left unwritten.)")
                    continue
                chosen = framings[pick]
                content = f"---\nplacement: {placement}\n---\n\n{chosen}\n"
                s3.write_issue_file(n, f"cta-{idx + 1}.md", content)
                written += 1
            await _llm_job.try_send(channel, f"✅ {written} CTA(s) written for WT{n}.")
            return _base.JobResult(True, f"compose-cta for WT{n}: {written} CTA(s) written.",
                                   data={"issue_number": n, "ctas_written": written, "posted": True})
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-cta` already running ({exc.holder_desc}).")
