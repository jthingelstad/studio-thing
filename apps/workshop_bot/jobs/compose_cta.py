"""``compose-cta`` (Patty) — fill the membership-block slots Eddy declared.

Reads ``final.md`` from the per-issue S3 workspace and **scans for inline
markers** (``<!-- cta:N -->`` and ``<!-- thanks:N -->``) placed by
``create-final``. Each marker is a slot. Patty fills the supporter-CTA
slots and the thank-you slots, posting 1–2 framings per slot to
``#supporters`` for Jamie to pick. The picked copy is written to
``cta-N.md`` / ``thanks-N.md`` with ``kind:`` YAML frontmatter; the
audience-aware Liquid wrapping happens later, in ``build-publish``.

Slot discovery is the inversion of today's flow: Patty no longer decides
*how many* CTAs there are or *where* they go — that's Eddy's editorial
call now. Patty only writes copy for slots Eddy declared. The placement
decision lives inline in ``final.md``; the file format here loses its
``placement:`` frontmatter (slot position is encoded by the marker, not by
the file).

Per slot:

- ``<!-- cta:N -->`` → ``prompts/patty/compose-cta.md`` (supporter ask, in
  Thingy's voice). Reader sees this in the audience-resolved Liquid only
  when they're *not* a premium member.
- ``<!-- thanks:N -->`` → ``prompts/patty/compose-thanks.md`` (sincere
  thank-you, Thingy's voice, gratitude register — never an ask). Reader
  sees this only when they *are* a premium member.

If ``thesis.md`` is present (written by ``create-final``), the thesis is
injected into both prompts as a ``## Thesis`` block at the top, so the
framings anchor on the issue's stated editorial intent. Missing
``thesis.md`` is fine — the job falls back to today's behaviour of
reading just the body.

Slots that already have a non-empty copy file are skipped — re-running
the job won't re-prompt for ones Jamie has already picked. To re-roll a
specific slot, delete its ``cta-N.md`` / ``thanks-N.md`` first.
"""

from __future__ import annotations

import asyncio
import logging
import re

from ..tools import db, s3
from ..tools.content import context
from ..tools.discord import interaction
from ..tools.llm import anthropic_client
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.compose_cta")

NAME = "compose-cta"

# How many prior issues' ``buttondown.md`` to include for arc continuity (so
# the model can see how prior CTAs / thanks read). The product
# (count × excerpt cap) bounds the arc-context size in the user message.
_ARC_LOOKBACK_COUNT = 4
_ARC_EXCERPT_CAP = 4_000

# Fixed slot list — every issue gets the same three atoms composed
# (regardless of editorial state). render_email's hardcoded
# CTA_SLOT_POSITIONS map decides where each lands in the email body.
FIXED_SLOTS: list[tuple[str, int]] = [("cta", 1), ("cta", 2), ("thanks", 1)]

# Map marker kind → (prompt name, output filename pattern, friendly slot label,
# YAML ``kind:`` value written into the file's frontmatter).
_KIND_CONFIG: dict[str, dict[str, str]] = {
    "cta":    {"prompt": "patty-compose-cta",    "label": "supporter CTA", "frontmatter_kind": "supporter"},
    "thanks": {"prompt": "patty-compose-thanks", "label": "thank-you",     "frontmatter_kind": "thanks"},
}


def _filename_for(kind: str, n: int) -> str:
    return f"cta-{n}.md" if kind == "cta" else f"thanks-{n}.md"


def _slot_filled(issue_number: int, filename: str) -> bool:
    """True if the per-slot file already exists with a non-empty body."""
    res = s3.read_issue_file(issue_number, filename)
    if not (res.get("found") and isinstance(res.get("text"), str)):
        return False
    text = res["text"]
    # Strip frontmatter (``---\n…\n---``) before checking for body content.
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
    return bool(body.strip())


def _recent_publish_excerpts(issue_number: int, count: int = _ARC_LOOKBACK_COUNT) -> str:
    out: list[str] = []
    for prev in range(issue_number - 1, issue_number - 1 - count, -1):
        if prev < 1:
            break
        res = s3.read_issue_file(prev, "buttondown.md")
        if res.get("found") and isinstance(res.get("text"), str) and res["text"].strip():
            out.append(f"--- WT{prev} buttondown.md ---\n{res['text'][:_ARC_EXCERPT_CAP]}")
    return "\n\n".join(out) if out else "(no prior buttondown.md files available)"


def _parse_framings(reply: str) -> list[str]:
    """Pull 1–2 framing strings out of the model's JSON reply.

    Both ``compose-cta`` and ``compose-thanks`` return
    ``{"framings": ["…", "…"]}``. Returns ``[]`` to signal
    "unparseable; retry" — the same convention as the other compose jobs."""
    data = _llm_job.parse_json_payload(reply)
    if not isinstance(data, dict):
        return []
    framings = data.get("framings")
    if not isinstance(framings, list):
        return []
    out: list[str] = []
    for f in framings:
        s = str(f).strip()
        if s:
            out.append(s)
        if len(out) >= 2:
            break
    return out


def _pretty(framings: list[str]) -> list[str]:
    """Render framings as blockquotes for the Discord picker."""
    return [f"> {f}" for f in framings]


async def _fill_slot(
    *, bot, channel, n: int, kind: str, slot_n: int,
    arc_excerpts: str, patty_ctx_block: str, thesis_block: str,
) -> bool:
    """Generate framings for one slot, post the picker, write the picked
    body to the slot's file. Returns True if a file was written."""
    cfg = _KIND_CONFIG[kind]
    base_prompt = anthropic_client.load_prompt(cfg["prompt"])
    head = thesis_block + ("\n" if thesis_block else "") + patty_ctx_block
    user_msg = (
        f"{head}\n\n{base_prompt}\n\n"
        f"---\n\nRecent issues (for arc continuity — prior CTAs/thanks are in these):\n\n"
        f"{arc_excerpts}\n\n"
        f"---\n\nThis is slot **{kind}:{slot_n}** for WT{n}. "
        f"Draft 1–2 framings for *this slot only*."
    )
    pick = await _llm_job.refresh_loop(
        bot, channel,
        base_msg=user_msg,
        parser=_parse_framings,
        pretty=_pretty,
        prompt_label=f"💝 WT{n} — {cfg['label']} slot {slot_n} (`{kind}:{slot_n}`):",
        trigger=f"compose-cta:{kind}",
        persona="patty",
        cards_issue=n,
        cards_filename=f"{kind}-{slot_n}-options",
        cards_title=f"WT{n} — {cfg['label']} options ({kind}:{slot_n})",
        cards_subtitle=f"1–2 framings · react in #supporters to pick",
    )
    if not pick:
        await _llm_job.try_send(
            channel,
            f"(No pick for {cfg['label']} slot {slot_n} of WT{n} — left unwritten.)",
            job_label="compose-cta",
        )
        return False
    content = f"---\nkind: {cfg['frontmatter_kind']}\n---\n\n{pick}\n"
    s3.write_issue_file(n, _filename_for(kind, slot_n), content)
    return True


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window.")
    n = int(window["issue_number"])

    # Slot count is fixed — Patty composes the three known atoms per
    # issue regardless of editorial state. render_email's hardcoded
    # CTA_SLOT_POSITIONS map decides where each lands; absent atoms
    # produce no marker / no Liquid block on the email side.
    slots: list[tuple[str, int]] = FIXED_SLOTS

    bot, channel, reason = _llm_job.resolve_bot_and_channel(ctx, "patty", "DISCORD_CHANNEL_SUPPORTERS")
    if bot is None:
        return _base.JobResult(True, f"(compose-cta skipped — {reason})", data={"posted": False})

    # Per-slot locks — same granularity as today, just with the thanks
    # files included.
    assets = [f"{n}/{_filename_for(k, num)}" for k, num in slots]
    try:
        with _base.job_lock(assets, NAME):
            # Off-loop: dynamic context + arc excerpts both hit external APIs
            # / S3 (slow round-trip otherwise stalls the gateway).
            patty_ctx = await asyncio.to_thread(context.build_patty_context)
            patty_ctx_block = context.render_block(patty_ctx)
            arc_excerpts = await asyncio.to_thread(_recent_publish_excerpts, n)
            thesis_block = await asyncio.to_thread(_llm_job.thesis_block, n)

            written = 0
            skipped = 0
            for kind, slot_n in slots:
                filename = _filename_for(kind, slot_n)
                if _slot_filled(n, filename):
                    skipped += 1
                    await _llm_job.try_send(
                        channel,
                        f"⏭️ Skipping `{kind}:{slot_n}` for WT{n} — `{filename}` already has copy. "
                        f"Delete it to re-roll.",
                        job_label="compose-cta",
                    )
                    continue
                if await _fill_slot(
                    bot=bot, channel=channel, n=n, kind=kind, slot_n=slot_n,
                    arc_excerpts=arc_excerpts,
                    patty_ctx_block=patty_ctx_block,
                    thesis_block=thesis_block,
                ):
                    written += 1

            summary = (
                f"✅ compose-cta for WT{n}: {written} slot(s) written"
                + (f", {skipped} already filled" if skipped else "")
                + f" (of {len(slots)} declared)."
            )
            await _llm_job.try_send(channel, summary, job_label="compose-cta")
            return _base.JobResult(
                True, summary,
                data={
                    "issue_number": n,
                    "slots_total": len(slots),
                    "slots_written": written,
                    "slots_skipped": skipped,
                },
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `compose-cta` already running ({exc.holder_desc}).")
