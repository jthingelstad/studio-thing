"""``compose-haiku`` — generate haiku options from the issue, write ``haiku.md``.

Reads ``final.md`` (or ``draft.md`` if final isn't written yet) and the
published-archive corpus (for "haiku I've used before — don't repeat
them"), asks Eddy for 2–3 options, posts them to ``#editorial``, and
writes Jamie's pick to ``haiku.md``. Required for ship. Re-fire any time
for fresh options.
"""

from __future__ import annotations

import logging

from ..tools import anthropic_client, db, s3
from . import _base, _compose

logger = logging.getLogger("workshop.jobs.compose_haiku")

NAME = "compose-haiku"


def _parse_haiku_options(reply: str) -> list[str]:
    """Extract up to 5 haiku option strings from the model's JSON reply.
    Returns an empty list if the reply doesn't parse as
    ``{"options": [...]}`` — :func:`_compose.refresh_loop` retries on
    empty."""
    data = _compose.parse_json_payload(reply)
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
    body = _compose.final_or_draft(n)
    if not body.strip():
        return _base.JobResult(False, f"❌ no `final.md`/`draft.md` for WT{n} yet.")
    bot, channel, reason = _compose.resolve_bot_and_channel(ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL")
    if bot is None:
        return _base.JobResult(
            True, f"(compose-haiku skipped — {reason})",
            data={"options_posted": False, "haiku_written": False},
        )

    asset = f"{n}/haiku.md"
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-compose-haiku")
            base_msg = (
                f"{base_prompt}\n\n---\n\nThe issue (WT{n}):\n\n"
                f"```markdown\n{body[:_compose.ISSUE_BODY_CAP]}\n```"
            )
            chosen = await _compose.refresh_loop(
                bot, channel,
                base_msg=base_msg,
                parser=_parse_haiku_options,
                pretty=_pretty_haiku_options,
                prompt_label=f"📜 Haiku options for WT{n} — pick one:",
                trigger="compose-haiku",
            )
            if not chosen:
                return _base.JobResult(
                    False,
                    f"compose-haiku for WT{n}: no pick (timed out / unparseable) — re-run when ready.",
                    data={"options_posted": True, "haiku_written": False},
                )
            chosen = chosen.strip() + "\n"
            s3.write_issue_file(n, "haiku.md", chosen)
            await channel.send(f"✅ Haiku set for WT{n}.", suppress_embeds=True)
            return _base.JobResult(
                True, f"`haiku.md` written for WT{n}.",
                data={"issue_number": n, "haiku": chosen,
                      "options_posted": True, "haiku_written": True},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-haiku` already running ({exc.holder_desc}).")
