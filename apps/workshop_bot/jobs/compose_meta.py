"""``compose-meta`` — pick the email subject + description, write ``metadata.json``.

Two LLM steps:

  1. **Subject** — Eddy returns 5 ``WT<N> — <theme>`` options
     (``prompts/eddy/compose-subject.md`` — Jamie's prompt verbatim, with
     ``<NUM>`` and ``<<<ISSUE_TEXT>>>`` substituted by the job); the job
     posts all 5 to ``#editorial`` and Jamie reacts 1️⃣–5️⃣ (🔄 = refresh,
     up to ``MAX_ROUNDS``).
  2. **Description** — Eddy generates a single comma-separated topic line
     (``prompts/eddy/compose-description.md`` — also verbatim;
     ``<<<ISSUE_TEXT>>>`` substituted). One-shot, no picker — the prompt
     is deterministic enough (length window, ordering rules, style
     guardrails) that re-rolling rarely improves it. The job takes the
     first non-empty line of the reply and writes it.

The picked subject + generated description land in ``metadata.json`` — a
subset of the Buttondown email schema; ``image`` / ``slug`` / ``number`` /
``publish_date`` are deterministic, only ``subject`` and ``description``
are generated. Required for ship. The success post in ``#editorial``
surfaces both so Jamie can spot a bad description before publishing (edit
in Buttondown or re-run ``compose-meta``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from ..tools import db, s3
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_meta")

NAME = "compose-meta"
_SUBJECT_OPTION_CAP = 8  # parse at most this many subjects (prompt asks for 5)

ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"

_NUM_LINE_RE = re.compile(r"(?m)^\s*\d+[.)]\s+(.+?)\s*$")


def _parse_numbered_list_factory(limit: int):
    """Build the parser passed to :func:`_llm_job.refresh_loop` — pulls
    items out of a ``1. … / 2. …`` numbered list, tolerating a stray
    preamble, code fences, or bold/quote wrappers."""
    def _parse(text: str) -> list[str]:
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
    return _parse


def _first_nonempty_line(text: str) -> str:
    """The description prompt is "Output: a single line"; take the first
    non-empty line in case the model echoes a preamble or trailing
    blank lines despite the prompt."""
    for line in (text or "").splitlines():
        s = line.strip()
        if s:
            return s
    return ""


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
            True, f"(compose-meta skipped — {reason})",
            data={"metadata_written": False},
        )

    asset = f"{n}/metadata.json"
    try:
        with _base.job_lock([asset], NAME):
            issue_text = body[: _llm_job.ISSUE_BODY_CAP]
            # Thread Eddy's thesis (when present) into both subject and
            # description prompts so the picked subject + the one-shot
            # description anchor on the same editorial intent that drove
            # the reorder. Missing thesis.md → empty prefix, jobs degrade
            # to today's body-only behaviour.
            thesis_block = await asyncio.to_thread(_llm_job.thesis_block, n)
            thesis_prefix = thesis_block + "\n" if thesis_block else ""

            # ---- step 1: subject (the 5-option prompt, verbatim) ----
            subject_prompt = anthropic_client.load_prompt("eddy-compose-subject")
            subject_msg = thesis_prefix + subject_prompt.replace("<NUM>", str(n)).replace(
                "<<<ISSUE_TEXT>>>", issue_text
            )
            subject = await _llm_job.refresh_loop(
                bot, channel,
                base_msg=subject_msg,
                parser=_parse_numbered_list_factory(_SUBJECT_OPTION_CAP),
                prompt_label=f"📰 5 subject options for WT{n} — react to pick:",
                trigger="compose-meta:subject",
                cards_issue=n,
                cards_filename="subject-options",
                cards_title=f"WT{n} — subject options",
                cards_subtitle=f"5 candidates · react 1️⃣–5️⃣ in #editorial to pick",
            )
            if not subject:
                # Subject options were posted to #editorial; Jamie didn't
                # pick within the timeout (or the model wouldn't return a
                # parseable list after MAX_ROUNDS). The metadata.json file
                # is *not* written without a subject.
                return _base.JobResult(
                    False,
                    f"compose-meta for WT{n}: no subject picked (timed out / unparseable) — re-run when ready.",
                    data={"subject_options_posted": True, "metadata_written": False},
                )

            # ---- step 2: description ----
            # One-shot: Jamie's description prompt is deterministic enough
            # (length window, ordering rules, style guardrails) to skip the
            # picker / refresh loop. If he wants a different angle he edits
            # in Buttondown or re-runs compose-meta.
            desc_prompt = anthropic_client.load_prompt("eddy-compose-description")
            desc_msg = thesis_prefix + desc_prompt.replace("<<<ISSUE_TEXT>>>", issue_text)
            with db.AgentRun("eddy", trigger="compose-meta:description") as agent_run:
                desc_reply, _m = await bot.core(latest=desc_msg, history=[], model=None)
                agent_run.record_meta(_m)
                agent_run.records_written = 1 if desc_reply else 0
            description = _first_nonempty_line(desc_reply)

            pub_iso = f"{window['pub_date']}T12:00:00Z"
            metadata = {
                "number": n,
                "subject": subject,
                "description": description,
                "image": f"{ASSETS_BASE}/{n}/cover.jpg",
                "slug": str(n),
                "publish_date": pub_iso,
            }
            # Preserve buttondown_id (and anything else send-to-buttondown has
            # written) so re-running compose-meta after the first Buttondown
            # send doesn't orphan the existing draft on the next send. Only
            # subject/description are generated here; everything else either
            # is deterministic (number/slug/image/publish_date) or comes from
            # downstream jobs we shouldn't clobber.
            existing = s3.read_issue_file(n, "metadata.json")
            if existing.get("found") and isinstance(existing.get("text"), str):
                try:
                    prior = json.loads(existing["text"])
                except (ValueError, TypeError):
                    prior = None
                if isinstance(prior, dict):
                    for key, value in prior.items():
                        if key not in metadata:
                            metadata[key] = value
            s3.write_issue_file(n, "metadata.json", json.dumps(metadata, indent=2) + "\n")
            desc_line = description if description else "_(empty — set it in Buttondown or re-run compose-meta)_"
            # Best-effort: metadata.json is on S3 either way; a Discord
            # glitch on the success card shouldn't fail the job.
            await _llm_job.try_send(
                channel,
                f"✅ `metadata.json` set for WT{n}\n"
                f"**Subject:** {subject}\n"
                f"**Description:** {desc_line}",
                job_label="compose-meta",
            )
            return _base.JobResult(
                True, f"`metadata.json` written for WT{n} — {subject}",
                data={"issue_number": n, "metadata": metadata,
                      "subject_options_posted": True, "metadata_written": True},
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-meta` already running ({exc.holder_desc}).")
