"""``compose-meta`` — pick the email subject + description, write ``metadata.json``.

Two LLM steps, each ending in a reaction pick in ``#editorial``:

  1. **Subject** — Eddy returns 5 ``WT<N> — <theme>`` options
     (``prompts/eddy/compose-subject.md``); Jamie reacts 1️⃣–5️⃣ (or 🔄).
  2. **Description** — Eddy returns 3 description options
     (``prompts/eddy/compose-description.md``); Jamie picks.

The chosen pair lands in ``metadata.json`` — a subset of the Buttondown
email schema; ``image`` / ``slug`` / ``number`` / ``publish_date`` are
deterministic, only ``subject`` / ``description`` are generated. Required
for ship. (If Jamie skips the description pick, ``metadata.json`` is still
written with an empty description so the subject pick isn't wasted.)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..tools import anthropic_client, db, interaction, s3
from . import _base, _compose

logger = logging.getLogger("workshop.jobs.compose_meta")

NAME = "compose-meta"
MAX_ROUNDS = 3

REPO = Path(__file__).resolve().parents[3]
EMAILS_DIR = REPO / "data" / "buttondown" / "emails"
ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"

_NUM_LINE_RE = re.compile(r"(?m)^\s*\d+[.)]\s+(.+?)\s*$")


def _recent_subjects(limit: int = 10) -> list[str]:
    if not EMAILS_DIR.is_dir():
        return []
    rows: list[tuple[str, str]] = []
    for p in EMAILS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        subj = d.get("subject")
        pub = d.get("publish_date") or ""
        if subj:
            rows.append((str(pub), str(subj)))
    rows.sort(reverse=True)
    return [s for _, s in rows[:limit]]


def _parse_numbered_list(text: str, limit: int) -> list[str]:
    """Pull the items out of a ``1. … / 2. …`` numbered list, tolerating a
    stray preamble, code fences, or bold/quote wrappers around the items."""
    out: list[str] = []
    for m in _NUM_LINE_RE.finditer(text or ""):
        item = m.group(1).strip().strip("`").strip()
        item = re.sub(r"^\*\*(.*)\*\*$", r"\1", item).strip()
        item = item.strip('"').strip("“”").strip()
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


async def _choose(
    bot, channel, *, base_msg: str, prompt_label: str, limit: int, trigger: str,
):
    """Run an LLM call → parse a numbered list → ask Jamie to pick. Supports
    a 🔄 refresh (up to ``MAX_ROUNDS``). Returns the chosen string, or
    ``None`` on timeout / unparseable output."""
    user_msg = base_msg
    for _round in range(MAX_ROUNDS):
        with db.AgentRun("eddy", trigger=trigger) as agent_run:
            reply, _m = await bot.core(latest=user_msg, history=[], model=None)
            agent_run.records_written = 1
        options = _parse_numbered_list(reply, limit)
        if not options:
            return None
        pick = await interaction.await_choice(bot, channel, options, prompt=prompt_label)
        if pick == "refresh":
            user_msg = base_msg + "\n\n(Jamie asked for fresh options — give different framings, please.)"
            continue
        if pick is None or pick >= len(options):
            return None
        return options[pick]
    return None


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
        return _base.JobResult(True, f"(compose-meta skipped — {reason})", data={"posted": False})

    asset = f"{n}/metadata.json"
    try:
        with _base.job_lock([asset], NAME):
            issue_text = body[: _compose.ISSUE_BODY_CAP]
            recent = _recent_subjects(10)
            recent_block = (
                "Recent subject lines (vary from these):\n"
                + "\n".join(f"- {s}" for s in recent) + "\n\n"
                if recent else ""
            )

            # ---- step 1: subject (the 5-option prompt, verbatim) ----
            subject_prompt = anthropic_client.load_prompt("eddy-compose-subject")
            subject_msg = subject_prompt.replace("<NUM>", str(n)).replace("<<<ISSUE_TEXT>>>", issue_text)
            subject = await _choose(
                bot, channel, base_msg=subject_msg,
                prompt_label=f"📰 5 subject options for WT{n} — react to pick:",
                limit=8, trigger="compose-meta-subject",
            )
            if not subject:
                return _base.JobResult(
                    False,
                    f"compose-meta for WT{n}: no subject picked (timed out / unparseable) — re-run when ready.",
                    data={"posted": True},
                )

            # ---- step 2: description ----
            desc_prompt = anthropic_client.load_prompt("eddy-compose-description")
            desc_msg = (
                f"{recent_block}{desc_prompt}\n\n"
                f"Chosen subject line: {subject}\n\n"
                f"---\n\nThe issue (WT{n}):\n\n```markdown\n{issue_text}\n```"
            )
            description = await _choose(
                bot, channel, base_msg=desc_msg,
                prompt_label=f"📝 Description options for WT{n} (subject: **{subject}**) — react to pick:",
                limit=8, trigger="compose-meta-description",
            )
            if description is None:
                description = ""
                await channel.send(
                    f"⚠️ No description picked for WT{n} — `metadata.json` written with an empty "
                    f"description; set it in Buttondown or re-run `compose-meta`.",
                    suppress_embeds=True,
                )

            pub_iso = f"{window['pub_date']}T12:00:00Z"
            metadata = {
                "number": n,
                "subject": subject,
                "description": description,
                "image": f"{ASSETS_BASE}/{n}/cover.jpg",
                "slug": str(n),
                "publish_date": pub_iso,
            }
            s3.write_issue_file(n, "metadata.json", json.dumps(metadata, indent=2) + "\n")
            await channel.send(f"✅ `metadata.json` set for WT{n}: **{subject}**", suppress_embeds=True)
            return _base.JobResult(
                True, f"`metadata.json` written for WT{n} — {subject}",
                data={"issue_number": n, "metadata": metadata, "posted": True},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-meta` already running ({exc.holder_desc}).")
