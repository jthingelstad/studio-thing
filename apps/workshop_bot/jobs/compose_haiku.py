"""``compose-haiku`` — generate haiku options from the issue, write ``haiku.md``.

Reads ``final.md`` (or ``draft.md`` if final isn't written yet) and the
published-archive corpus (for "haiku I've used before — don't repeat
them"), asks Eddy for 2–3 options, posts them to ``#editorial``, and
writes Jamie's pick to ``haiku.md``. Required for ship. Re-fire any time
for fresh options.
"""

from __future__ import annotations

import asyncio
import logging

from ..tools import db, s3
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_haiku")

NAME = "compose-haiku"


def _parse_haiku_options(reply: str) -> list[str]:
    """Extract up to 5 haiku option strings from the model's JSON reply.
    Returns an empty list if the reply doesn't parse as
    ``{"options": [...]}`` — :func:`_llm_job.refresh_loop` retries on
    empty."""
    data = _llm_job.parse_json_payload(reply)
    options = (data or {}).get("options")
    if not isinstance(options, list):
        return []
    cleaned = [str(o).strip() for o in options if str(o).strip()]
    return cleaned[:5]


def _pretty_haiku_options(options: list[str]) -> list[str]:
    """Render each haiku as a Discord blockquote so the three lines hold
    together visually in the picker."""
    return ["\n".join("> " + ln for ln in o.splitlines()) for o in options]


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])
    # Off-loop: final_or_draft hits S3 (read of final.md, fallback to draft.md).
    body = await asyncio.to_thread(_llm_job.final_or_draft, n)
    if not body.strip():
        return _base.JobResult(False, f"❌ no `final.md`/`draft.md` for WT{n} yet.")
    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(
            True, f"(compose-haiku skipped — {reason})",
            data={"options_posted": False, "haiku_written": False},
        )

    asset = f"{n}/haiku.md"
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-compose-haiku")
            # Thread Eddy's thesis (when present) into the user message so the
            # haiku anchors on the same editorial intent as the reorder, subject,
            # description, and CTA framings. Missing thesis.md → empty string,
            # job degrades to today's body-only behaviour.
            thesis_block = await asyncio.to_thread(_llm_job.thesis_block, n)
            base_msg = (
                f"{thesis_block}"
                + ("\n" if thesis_block else "")
                + f"{base_prompt}\n\n---\n\nThe issue (WT{n}):\n\n"
                f"```markdown\n{body[:_llm_job.ISSUE_BODY_CAP]}\n```"
            )
            chosen = await _llm_job.refresh_loop(
                bot, channel,
                base_msg=base_msg,
                parser=_parse_haiku_options,
                pretty=_pretty_haiku_options,
                prompt_label=f"📜 Haiku options for WT{n} — pick one:",
                trigger="compose-haiku",
                cards_issue=n,
                cards_filename="haiku-options",
                cards_title=f"WT{n} — haiku options",
                cards_subtitle="three lines each · react in #editorial to pick",
                cards_body_kind="mono",
            )
            if not chosen:
                return _base.JobResult(
                    False,
                    f"compose-haiku for WT{n}: no pick (timed out / unparseable) — re-run when ready.",
                    data={"options_posted": True, "haiku_written": False},
                )
            chosen = chosen.strip() + "\n"
            s3.write_issue_file(n, "haiku.md", chosen)
            # Best-effort: haiku.md is on S3 either way; a Discord glitch
            # on the success card shouldn't fail the job.
            await _llm_job.try_send(
                channel, f"✅ Haiku set for WT{n}.", job_label="compose-haiku",
            )
            return _base.JobResult(
                True, f"`haiku.md` written for WT{n}.",
                data={"issue_number": n, "haiku": chosen,
                      "options_posted": True, "haiku_written": True},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-haiku` already running ({exc.holder_desc}).")
