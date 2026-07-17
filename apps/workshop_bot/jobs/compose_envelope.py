"""``compose-envelope`` — the batched Publish-phase composer.

One LLM call over the runtime-assembled draft (``_llm_job.draft_body``)
returns the whole email **envelope** in a single structured reply — 5
subject options, 1 meta description, and 3 haiku options. Because the
three deliverables are composed together against the same draft, they
share editorial context directly: the draft *is* the anchor (retiring
the old ``compose-thesis`` machinery, where a separate thesis.md was the
shared anchor the four shipping jobs read).

The per-slot **pick UX is preserved** — Jamie still picks subject 1–5
and haiku 1–3 in ``#editorial`` (with the option-cards HTML pages),
description is one-shot. But the pickers **replay** the already-generated
options via :func:`_llm_job.replay_pick` rather than re-calling the model
per slot — so the happy path is exactly **one** ``bot.core`` call, not
three. A 🔄 refresh on a slot regenerates just that slot (one extra call).

Writes ``metadata.json`` (subject + description; deterministic
image/slug/number/publish_date; preserves any existing ``buttondown_id``)
and ``haiku.md`` — byte-for-byte the same artifacts ``compose-meta`` and
``compose-haiku`` write. Auto-fired inside ``mark-built`` (Build →
Publish); also available manually. The standalone ``compose-meta`` /
``compose-haiku`` jobs remain as single-slot repair escape hatches.
"""

from __future__ import annotations

import asyncio
import json
import logging

from ..tools import content_store, db
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_envelope")

NAME = "compose-envelope"

_SUBJECT_COUNT = 5
_HAIKU_COUNT = 3

ASSETS_BASE = "https://files.thingelstad.com/weekly-thing"


def _extract_envelope(data) -> tuple[list[str], str, list[str]]:
    """Pull ``(subjects, description, haikus)`` out of the model's JSON
    reply. Returns empty lists / string when a field is missing or the
    wrong shape — the caller treats "no subjects or no haikus" as
    unparseable and retries."""
    if not isinstance(data, dict):
        return [], "", []
    raw_subjects = data.get("subjects")
    raw_haikus = data.get("haikus")
    description = data.get("description")

    subjects = (
        [str(s).strip() for s in raw_subjects if str(s).strip()][:_SUBJECT_COUNT]
        if isinstance(raw_subjects, list)
        else []
    )
    haikus = (
        [str(h).strip() for h in raw_haikus if str(h).strip()][:_HAIKU_COUNT]
        if isinstance(raw_haikus, list)
        else []
    )
    description = str(description).strip() if isinstance(description, str) else ""
    return subjects, description, haikus


def _pretty_haiku_options(options: list[str]) -> list[str]:
    """Render each haiku as a Discord blockquote so the three lines hold
    together visually in the picker (mirrors ``compose-haiku``)."""
    return ["\n".join("> " + ln for ln in o.splitlines()) for o in options]


async def _generate(bot, *, base_msg: str, model: str) -> tuple[list[str], str, list[str]]:
    """One batched ``bot.core`` call → ``(subjects, description, haikus)``.
    Retries up to ``MAX_REFRESH_ROUNDS`` on an unparseable reply (missing
    subjects or haikus), tightening the hint each round. Returns empty
    lists when the model never produces a usable envelope."""
    msg = base_msg
    for _round in range(_llm_job.MAX_REFRESH_ROUNDS):
        with db.AgentRun("eddy", trigger="compose-envelope") as agent_run:
            reply, meta = await bot.core(latest=msg, history=[], model=model)
            agent_run.record_meta(meta)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
        subjects, description, haikus = _extract_envelope(_llm_job.parse_json_payload(reply or ""))
        if subjects and haikus:
            return subjects, description, haikus
        msg = base_msg + (
            "\n\n(That reply didn't match the required JSON shape — return "
            'exactly {"subjects":[5 strings],"description":"…","haikus":'
            "[3 strings]}, nothing else.)"
        )
    return [], "", []


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])

    # Off-loop: draft_body renders the body live from the DB.
    body = await asyncio.to_thread(_llm_job.draft_body, n)
    if not body.strip():
        return _base.JobResult(False, f"❌ no draft body for WT{n} yet.")

    bot, channel, reason = _llm_job.resolve_bot_and_channel(
        ctx, "eddy", "DISCORD_CHANNEL_EDITORIAL"
    )
    if bot is None:
        return _base.JobResult(
            True,
            f"(compose-envelope skipped — {reason})",
            data={"metadata_written": False, "haiku_written": False},
        )

    # Both slots write different files; lock both so a concurrent
    # compose-meta / compose-haiku can't race the envelope.
    assets = [f"{n}/metadata.json", f"{n}/haiku.md"]
    try:
        with _base.job_lock(assets, NAME):
            prompt = anthropic_client.load_prompt("eddy-compose-envelope")
            issue_text = body[: _llm_job.ISSUE_BODY_CAP]
            base_msg = prompt.replace("<NUM>", str(n)).replace("<<<ISSUE_TEXT>>>", issue_text)

            # ---- one batched call ---- #
            # Sonnet, like the individual compose-meta / compose-haiku
            # pickers — the envelope is short, structured output.
            subjects, description, haikus = await _generate(bot, base_msg=base_msg, model="sonnet")
            if not subjects or not haikus:
                msg = (
                    f"compose-envelope for WT{n}: Eddy didn't return a usable "
                    f"envelope after {_llm_job.MAX_REFRESH_ROUNDS} tries — re-run when ready."
                )
                await _llm_job.try_send(channel, f"⚠️ {msg}", job_label="compose-envelope")
                return _base.JobResult(
                    False,
                    msg,
                    data={"metadata_written": False, "haiku_written": False},
                )

            # ---- subject pick (replay — no model call) ---- #
            async def _regen_subjects():
                s, _d, _h = await _generate(bot, base_msg=base_msg, model="sonnet")
                return s

            subject = await _llm_job.replay_pick(
                bot,
                channel,
                options=subjects,
                prompt_label=f"📰 {len(subjects)} subject options for WT{n} — react to pick:",
                regenerate=_regen_subjects,
                cards_issue=n,
                cards_filename="subject-options",
                cards_title=f"WT{n} — subject options",
                cards_subtitle=f"{len(subjects)} candidates · react in #editorial to pick",
            )
            if not subject:
                return _base.JobResult(
                    False,
                    f"compose-envelope for WT{n}: no subject picked (timed out) — re-run when ready.",
                    data={"metadata_written": False, "haiku_written": False},
                )

            # ---- haiku pick (replay — no model call) ---- #
            async def _regen_haikus():
                _s, _d, h = await _generate(bot, base_msg=base_msg, model="sonnet")
                return h

            haiku = await _llm_job.replay_pick(
                bot,
                channel,
                options=haikus,
                pretty=_pretty_haiku_options,
                prompt_label=f"📜 Haiku options for WT{n} — pick one:",
                regenerate=_regen_haikus,
                cards_issue=n,
                cards_filename="haiku-options",
                cards_title=f"WT{n} — haiku options",
                cards_subtitle="three lines each · react in #editorial to pick",
                cards_body_kind="mono",
            )
            if not haiku:
                # Subject is picked; persist metadata.json so it isn't lost,
                # but report the haiku miss so Jamie re-runs / picks it.
                _write_metadata(n, window, subject, description)
                await _llm_job.try_send(
                    channel,
                    f"✅ `metadata.json` set for WT{n} (subject + description), "
                    f"but no haiku picked — re-run `compose-envelope` or `/eddy issue haiku`.",
                    job_label="compose-envelope",
                )
                return _base.JobResult(
                    False,
                    f"compose-envelope for WT{n}: metadata written, haiku not picked.",
                    data={"metadata_written": True, "haiku_written": False, "subject": subject},
                )

            # ---- write both artifacts ---- #
            metadata = _write_metadata(n, window, subject, description)
            content_store.write_issue(n, "haiku.md", haiku.strip() + "\n")

            desc_line = description or "_(empty — set it in Buttondown or re-run)_"
            await _llm_job.try_send(
                channel,
                f"✅ Envelope composed for WT{n}\n"
                f"**Subject:** {subject}\n"
                f"**Description:** {desc_line}\n"
                f"**Haiku** set.",
                job_label="compose-envelope",
            )
            return _base.JobResult(
                True,
                f"Envelope written for WT{n} — {subject}",
                data={
                    "issue_number": n,
                    "metadata": metadata,
                    "metadata_written": True,
                    "haiku_written": True,
                    "subject": subject,
                    "haiku": haiku.strip() + "\n",
                },
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-envelope` already running ({exc.holder_desc}).")


def _write_metadata(n: int, window, subject: str, description: str) -> dict:
    """Write ``metadata.json`` exactly as ``compose-meta`` does — the picked
    subject + description plus the deterministic fields, preserving any
    existing ``buttondown_id`` (and other prior keys) so a re-run after the
    first Buttondown send PATCHes the same draft instead of orphaning it."""
    pub_iso = f"{window['pub_date']}T12:00:00Z"
    metadata = {
        "number": n,
        "subject": subject,
        "description": description,
        "image": f"{ASSETS_BASE}/{n}/cover.jpg",
        "slug": str(n),
        "publish_date": pub_iso,
    }
    existing = content_store.read_issue(n, "metadata.json")
    if existing:
        try:
            prior = json.loads(existing)
        except ValueError, TypeError:
            prior = None
        if isinstance(prior, dict):
            for key, value in prior.items():
                if key not in metadata:
                    metadata[key] = value
    content_store.write_issue(n, "metadata.json", json.dumps(metadata, indent=2) + "\n")
    return metadata
