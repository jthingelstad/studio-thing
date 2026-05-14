"""``create-final`` — Eddy's reorder review → ``final.md``.

Reads ``draft.md``, asks Eddy for a reordered/curated final (Notable
narrative flow, Briefly thematic grouping, Journal cuts/elevations),
posts the proposal to ``#editorial`` for Jamie's accept/skip/refresh, and
writes ``final.md`` (Eddy's version on accept, the draft as-is on skip/
timeout). Then tells Jamie what comes next — the compose jobs and
``build-publish`` are run on demand; ``build-publish`` refuses (with a
missing-list) until ``haiku.md`` / ``metadata.json`` / ``intro.md`` /
``cover.jpg`` are all present.

Refuses if ``final.md`` already exists — delete it explicitly to re-run.
"""

from __future__ import annotations

import asyncio
import logging
import re

from ..tools import anthropic_client, db, interaction, render, s3
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.create_final")

NAME = "create-final"
MAX_ROUNDS = 3

_FENCE_RE = re.compile(r"```(?:markdown|md)?\s*\n(.*?)\n?```", re.DOTALL)

_NEXT_STEPS = (
    "Next, in any order: `/eddy issue haiku`, `/eddy issue subject`, "
    "`/patty cta` — then `/eddy issue publish` (it'll list "
    "anything still missing if you run it early)."
)


def _draft_text(n: int) -> str:
    res = s3.read_issue_file(n, "draft.md")
    return res["text"] if (res.get("found") and isinstance(res.get("text"), str)) else ""


def _extract_proposed_body(reply: str):
    m = _FENCE_RE.search(reply or "")
    return m.group(1).strip() if m else None


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])
    # Off-loop: both reads hit S3.
    final_exists = (await asyncio.to_thread(s3.read_issue_file, n, "final.md")).get("found")
    if final_exists:
        return _base.JobResult(False, f"❌ WT{n} already has `final.md` — delete it to re-run `create-final`.")
    draft = await asyncio.to_thread(_draft_text, n)
    if not draft.strip():
        return _base.JobResult(False, f"❌ no `draft.md` for WT{n} — run `/eddy issue update` first.")
    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(False, f"(create-final skipped — {reason})")

    asset = f"{n}/final.md"
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-create-final")
            user_msg = (
                f"{base_prompt}\n\n---\n\nThe current draft (WT{n}):\n\n"
                f"```markdown\n{draft[: _llm_job.CREATE_FINAL_BODY_CAP]}\n```"
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
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "final", final_body,
                title=f"WT{n} — final", subtitle=f"FINAL (post-Eddy ordering) · WT{n} · awaiting publish.md",
                strip_block_markers=True,
            )
            view = f"\n\n📄 [view final]({html_url})" if html_url else ""
            await channel.send(f"✅ `final.md` written for WT{n}.{view}\n\n{_NEXT_STEPS}", suppress_embeds=True)
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `create-final` already running ({exc.holder_desc}).")

    return _base.JobResult(
        True,
        f"`final.md` written for WT{n}{f' · 📄 {html_url}' if html_url else ''}. {_NEXT_STEPS}",
        data={"issue_number": n, "preview_url": html_url},
    )
