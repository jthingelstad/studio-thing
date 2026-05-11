"""``compose-meta`` — generate subject + description options, write ``metadata.json``.

Reads ``final.md`` (or ``draft.md``) plus the last ~10 issues' subjects
from ``data/buttondown/emails/*.json`` (for "don't repeat the same
words"), asks Eddy for 2–3 (subject, description) pairs, posts them to
``#editorial``, and writes Jamie's pick to ``metadata.json`` — a subset of
the Buttondown email schema; ``image`` / ``slug`` / ``number`` /
``publish_date`` are deterministic, only ``subject`` / ``description`` are
generated. Required for ship.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..tools import anthropic_client, db, interaction, s3
from . import _base, _compose

logger = logging.getLogger("workshop.jobs.compose_meta")

NAME = "compose-meta"
MAX_ROUNDS = 3

REPO = Path(__file__).resolve().parents[3]
EMAILS_DIR = REPO / "data" / "buttondown" / "emails"
ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"


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
            base_prompt = anthropic_client.load_prompt("eddy-compose-meta")
            recent = _recent_subjects(10)
            user_msg = (
                f"{base_prompt}\n\nIssue number: {n}\n\n"
                "Recent subjects (do NOT repeat these words):\n"
                + "\n".join(f"- {s}" for s in recent)
                + f"\n\n---\n\nThe issue (WT{n}):\n\n```markdown\n{body[:_compose.ISSUE_BODY_CAP]}\n```"
            )
            for _round in range(MAX_ROUNDS):
                with db.AgentRun("eddy", trigger="compose-meta") as agent_run:
                    reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
                    agent_run.records_written = 1
                data = _compose.parse_json_payload(reply)
                options = (data or {}).get("options")
                if not isinstance(options, list) or not options:
                    return _base.JobResult(False, "compose-meta: model didn't return parseable options.")
                pairs = []
                for o in options[:5]:
                    if isinstance(o, dict) and o.get("subject"):
                        pairs.append({"subject": str(o["subject"]).strip(),
                                      "description": str(o.get("description") or "").strip()})
                if not pairs:
                    return _base.JobResult(False, "compose-meta: options missing subject fields.")
                pretty = [f"**{p['subject']}**\n> {p['description']}" for p in pairs]
                pick = await interaction.await_choice(
                    bot, channel, pretty, prompt=f"📰 Subject + description options for WT{n} — pick one:",
                )
                if pick == "refresh":
                    user_msg += "\n\n(Jamie asked for fresh options — different framings, please.)"
                    continue
                if pick is None or pick >= len(pairs):
                    return _base.JobResult(False, f"compose-meta for WT{n}: no pick (timed out) — re-run when ready.",
                                           data={"posted": True})
                chosen = pairs[pick]
                pub_iso = f"{window['pub_date']}T12:00:00Z"
                metadata = {
                    "number": n,
                    "subject": chosen["subject"],
                    "description": chosen["description"],
                    "image": f"{ASSETS_BASE}/{n}/cover.jpg",
                    "slug": str(n),
                    "publish_date": pub_iso,
                }
                s3.write_issue_file(n, "metadata.json", json.dumps(metadata, indent=2) + "\n")
                await channel.send(f"✅ Subject + description set for WT{n}: **{chosen['subject']}**", suppress_embeds=True)
                return _base.JobResult(True, f"`metadata.json` written for WT{n}.",
                                       data={"issue_number": n, "metadata": metadata, "posted": True})
            return _base.JobResult(False, "compose-meta: out of refreshes without a pick.", data={"posted": True})
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-meta` already running ({exc.holder_desc}).")
