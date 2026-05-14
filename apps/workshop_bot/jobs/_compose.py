"""Shared helpers for the compose-* jobs and create-final.

These jobs all: (1) read the issue's final.md (or draft.md as a fallback
before create-final has run), (2) run a persona's agent loop with a job
prompt, (3) parse a JSON payload out of the reply, (4) post options /
proposals to a channel and wait for Jamie's reaction, (5) write the
accepted artifact to the workspace.

The pick-an-option pattern is shared by compose_haiku (JSON list of
options) and compose_meta's subject path (numbered markdown list).
:func:`refresh_loop` collapses both into one helper — pass the parser
that turns the LLM reply into a `list[str]` of options.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, NamedTuple, Optional

from ..tools import db, interaction
from ..tools import s3
from . import _base


class ResolvedBot(NamedTuple):
    """Result of :func:`resolve_bot_and_channel`. Backwards-compatible
    with the old 3-tuple unpack (``bot, channel, reason = …``) AND
    accessible by field name (``r.bot``, ``r.channel``,
    ``r.error_reason``). When the persona / channel resolved cleanly,
    ``error_reason`` is ``None``; otherwise ``bot`` and ``channel`` are
    ``None`` and ``error_reason`` carries the user-safe explanation."""

    bot: Any
    channel: Any
    error_reason: Optional[str]

logger = logging.getLogger("workshop.jobs.compose")

# How many times to re-prompt the model on a 🔄 refresh or an unparseable
# response before giving up. Shared across compose_haiku, compose_meta,
# and create_final.
MAX_REFRESH_ROUNDS = 3

# Cap how much of the issue body we feed the model.
ISSUE_BODY_CAP = 20_000

# `create-final` reads ``draft.md`` rather than the post-final body, and
# the draft includes the full Journal section (rehosted images, all
# micro.blog posts in window) plus block markers — which is bulkier than
# the post-curation final. Bump the cap so Eddy sees the whole draft
# when reordering. The other compose jobs run on the trimmed
# ``final.md`` (or ``draft.md`` as fallback) and don't need the extra
# headroom.
CREATE_FINAL_BODY_CAP = ISSUE_BODY_CAP + 6_000

# `promotion-prep` reads ``publish.md`` — the byte-shaped email body, which
# carries the intro + the optional Currently block + the cover block + every
# non-empty section + the membership-CTA Liquid scaffold + the haiku close
# + the email-only tracking pixel. It's the bulkiest of the three artifacts;
# give Marky the whole thing when she's drafting syndication framings.
PROMOTION_BODY_CAP = ISSUE_BODY_CAP + 8_000


def final_or_draft(issue_number: int) -> str:
    """``final.md`` if it exists, else ``draft.md`` (so the compose jobs
    can be run manually before create-final). Empty string if neither."""
    for name in ("final.md", "draft.md"):
        res = s3.read_issue_file(issue_number, name)
        if res.get("found") and isinstance(res.get("text"), str) and res["text"].strip():
            return res["text"]
    return ""


def parse_json_payload(reply: str) -> Optional[dict[str, Any]]:
    """Extract and parse the first JSON object in ``reply`` (the model is
    asked to return only JSON; tolerate code fences / surrounding prose)."""
    if not reply:
        return None
    m = re.search(r"\{.*\}", reply, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def refresh_loop(
    bot,
    channel,
    *,
    base_msg: str,
    parser: Callable[[str], list[str]],
    pretty: Optional[Callable[[list[str]], list[str]]] = None,
    prompt_label: str,
    trigger: str,
    rounds: int = MAX_REFRESH_ROUNDS,
    persona: str = "eddy",
) -> Optional[str]:
    """The compose-pick loop: call the model, parse a list of options,
    show them in the channel, wait for Jamie's pick or 🔄 refresh, repeat
    up to ``rounds`` times. Returns the picked string, or ``None`` on
    timeout / unparseable-after-all-retries.

    Args:
        bot: persona client whose ``core(latest=..., history=..., model=...)``
            we call.
        channel: Discord channel to post options to (via ``interaction.await_choice``).
        base_msg: initial user message for the model.
        parser: ``(reply_text) -> list[str]`` — extracts the option strings.
            Return an empty list to signal "unparseable; retry."
        pretty: optional ``(options) -> list[str]`` to transform options
            before posting (e.g. quote-block each haiku). Defaults to
            identity.
        prompt_label: the prompt text shown above the options in Discord.
        trigger: the ``agent_runs.trigger`` label for the LLM call.
        rounds: max attempts before giving up.
        persona: persona name for ``db.AgentRun``.

    A 🔄 refresh appends a "fresh framings" hint to ``base_msg``; an
    unparseable response appends a tighter "follow the prompt's output
    shape" hint. Both feed into the next round."""
    user_msg = base_msg
    for _round in range(rounds):
        with db.AgentRun(persona, trigger=trigger) as agent_run:
            reply, _meta = await bot.core(latest=user_msg, history=[], model=None)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
        options = parser(reply or "")
        if not options:
            user_msg = base_msg + (
                "\n\n(That response didn't match the expected output shape — "
                "follow the prompt's format exactly, no surrounding prose.)"
            )
            continue
        shown = pretty(options) if pretty else options
        pick = await interaction.await_choice(bot, channel, shown, prompt=prompt_label)
        if pick == "refresh":
            user_msg = base_msg + "\n\n(Jamie asked for fresh options — give different framings, please.)"
            continue
        if pick is None or pick >= len(options):
            return None
        return options[pick]
    return None


def resolve_bot_and_channel(
    ctx: "_base.JobContext", persona: str, channel_env: str,
) -> ResolvedBot:
    """Return a :class:`ResolvedBot` for ``persona``: ``bot`` (the
    persona's discord.Client subclass — has ``wait_for``), ``channel``
    (has ``send`` and yields messages with ``add_reaction``), and
    ``error_reason`` (``None`` on success, a user-safe string otherwise).

    Backwards-compatible with the 3-tuple unpack callers were using —
    ``bot, channel, reason = resolve_bot_and_channel(...)`` keeps
    working, and new code can use field access for clarity:

        r = resolve_bot_and_channel(...)
        if r.bot is None:
            return JobResult(False, f"skipped — {r.error_reason}")
    """
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return ResolvedBot(None, None, "no Discord (team registry unavailable)")
    bot = team.bots.get(persona)
    if bot is None or getattr(bot, "user", None) is None:
        return ResolvedBot(None, None, f"{persona} unavailable")
    channel = ctx.channel(channel_env, persona=persona)
    if channel is None:
        return ResolvedBot(None, None, f"can't resolve {channel_env}")
    return ResolvedBot(bot, channel, None)
