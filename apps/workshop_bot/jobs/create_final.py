"""``create-final`` — Eddy's reorder review → ``final.md``, then the compose chain.

Reads ``draft.md``, asks Eddy for a reordered/curated final (Notable
narrative flow, Briefly thematic grouping, Journal cuts/elevations),
posts the proposal to ``#editorial`` for Jamie's accept/skip/refresh, and
writes ``final.md`` (Eddy's version on accept, the draft as-is on skip/
timeout). Then auto-fires ``compose-haiku`` + ``compose-meta`` +
``compose-cta`` in parallel; when all three complete and the required
Jamie-authored assets (``intro.md``, ``cover.jpg``) are present,
auto-fires ``build-publish``.

Refuses if ``final.md`` already exists — delete it explicitly to re-run.
"""

from __future__ import annotations

import asyncio
import logging
import re

from ..tools import anthropic_client, db, interaction, s3
from . import _base, _compose, build_publish, compose_cta, compose_haiku, compose_meta

logger = logging.getLogger("workshop.jobs.create_final")

NAME = "create-final"
MAX_ROUNDS = 3

_FENCE_RE = re.compile(r"```(?:markdown|md)?\s*\n(.*?)\n?```", re.DOTALL)


def _draft_text(n: int) -> str:
    res = s3.read_issue_file(n, "draft.md")
    return res["text"] if (res.get("found") and isinstance(res.get("text"), str)) else ""


def _extract_proposed_body(reply: str):
    m = _FENCE_RE.search(reply or "")
    return m.group(1).strip() if m else None


def _is_jobresult(x) -> bool:
    return isinstance(x, _base.JobResult)


def _msg(x) -> str:
    return x.message if _is_jobresult(x) else f"errored ({type(x).__name__}: {x})"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])
    if s3.read_issue_file(n, "final.md").get("found"):
        return _base.JobResult(False, f"❌ WT{n} already has `final.md` — delete it to re-run `create-final`.")
    draft = _draft_text(n)
    if not draft.strip():
        return _base.JobResult(False, f"❌ no `draft.md` for WT{n} — run `/workshop job update-draft` first.")
    bot, channel = _compose.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(False, f"(create-final skipped — {channel})")

    asset = f"{n}/final.md"
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-create-final")
            user_msg = (
                f"{base_prompt}\n\n---\n\nThe current draft (WT{n}):\n\n"
                f"```markdown\n{draft[: _compose.ISSUE_BODY_CAP + 6000]}\n```"
            )
            final_body = draft
            for _round in range(MAX_ROUNDS):
                with db.AgentRun("eddy", trigger="create-final") as agent_run:
                    reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                    agent_run.records_written = 1
                proposed = _extract_proposed_body(reply)
                summary = (reply or "").split("```", 1)[0].strip() or "Eddy proposes a reordered final."
                await channel.send(f"📝 **create-final** for WT{n}\n\n{summary[:1500]}", suppress_embeds=True)
                approved = await interaction.await_approval(
                    bot, channel,
                    prompt=f"Accept Eddy's reordering for WT{n}'s `final.md`? (❌ keeps the draft order as-is.)",
                )
                if approved == "refresh":
                    user_msg += "\n\n(Jamie wants a different cut — try again.)"
                    continue
                final_body = proposed if (approved is True and proposed) else draft
                break
            s3.write_issue_file(n, "final.md", final_body if final_body.endswith("\n") else final_body + "\n")
            await channel.send(
                f"✅ `final.md` written for WT{n}. Firing the compose chain (haiku / meta / cta)…",
                suppress_embeds=True,
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `create-final` already running ({exc.holder_desc}).")

    # Auto-fire the compose chain in parallel; each runs its own review loop.
    haiku_r, meta_r, cta_r = await asyncio.gather(
        compose_haiku.run(_base.JobContext(deps=ctx.deps, trigger="chained")),
        compose_meta.run(_base.JobContext(deps=ctx.deps, trigger="chained")),
        compose_cta.run(_base.JobContext(deps=ctx.deps, trigger="chained")),
        return_exceptions=True,
    )

    if _is_jobresult(haiku_r) and haiku_r.ok and _is_jobresult(meta_r) and meta_r.ok and _is_jobresult(cta_r) and cta_r.ok:
        bp = await build_publish.run(_base.JobContext(deps=ctx.deps, trigger="chained"))
        publish_note = f"build-publish: {_msg(bp)}"
    else:
        publish_note = (
            "build-publish not auto-fired — re-run any compose job that didn't complete, "
            "then `/workshop job build-publish`."
        )

    return _base.JobResult(
        True,
        " | ".join([
            f"final.md written for WT{n}.",
            f"compose-haiku: {_msg(haiku_r)}",
            f"compose-meta: {_msg(meta_r)}",
            f"compose-cta: {_msg(cta_r)}",
            publish_note,
        ]),
        data={"issue_number": n},
    )
