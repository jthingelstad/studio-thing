"""``compose-haiku`` — generate haiku options from the issue, write ``haiku.md``.

Reads ``final.md`` (or ``draft.md`` if final isn't written yet) and the
published-archive corpus (for "haiku I've used before — don't repeat
them"), asks Eddy for 2–3 options, posts them to ``#editorial``, and
writes Jamie's pick to ``haiku.md``. Required for ship. Re-fire any time
for fresh options.
"""

from __future__ import annotations

import logging

from ..tools import anthropic_client, db, interaction, s3
from . import _base, _compose

logger = logging.getLogger("workshop.jobs.compose_haiku")

NAME = "compose-haiku"
MAX_ROUNDS = 3  # initial + up to 2 refreshes


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
        return _base.JobResult(True, f"(compose-haiku skipped — {reason})", data={"posted": False})

    asset = f"{n}/haiku.md"
    try:
        with _base.job_lock([asset], NAME):
            base_prompt = anthropic_client.load_prompt("eddy-compose-haiku")
            user_msg = (
                f"{base_prompt}\n\n---\n\nThe issue (WT{n}):\n\n"
                f"```markdown\n{body[:_compose.ISSUE_BODY_CAP]}\n```"
            )
            for _round in range(MAX_ROUNDS):
                with db.AgentRun("eddy", trigger="compose-haiku") as agent_run:
                    reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                    agent_run.records_written = 1
                data = _compose.parse_json_payload(reply)
                options = (data or {}).get("options")
                if not isinstance(options, list) or not options:
                    return _base.JobResult(False, "compose-haiku: model didn't return parseable options.")
                options = [str(o).strip() for o in options if str(o).strip()][:5]
                pretty = ["\n".join("> " + ln for ln in o.splitlines())  for o in options]
                pick = await interaction.await_choice(
                    bot, channel, pretty, prompt=f"📜 Haiku options for WT{n} — pick one:",
                )
                if pick == "refresh":
                    user_msg += "\n\n(Jamie asked for fresh options — different angles, please.)"
                    continue
                if pick is None or pick >= len(options):
                    return _base.JobResult(False, f"compose-haiku for WT{n}: no pick (timed out) — re-run when ready.",
                                           data={"posted": True})
                chosen = options[pick].strip() + "\n"
                s3.write_issue_file(n, "haiku.md", chosen)
                await channel.send(f"✅ Haiku set for WT{n}.", suppress_embeds=True)
                return _base.JobResult(True, f"`haiku.md` written for WT{n}.",
                                       data={"issue_number": n, "haiku": chosen, "posted": True})
            return _base.JobResult(False, "compose-haiku: out of refreshes without a pick.", data={"posted": True})
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-haiku` already running ({exc.holder_desc}).")
