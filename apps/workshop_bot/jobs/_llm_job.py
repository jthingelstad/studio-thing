"""Shared helpers for the compose-* jobs and reorder.

These jobs all: (1) read the issue's draft.md, (2) run a persona's agent
loop with a job prompt, (3) parse a JSON payload out of the reply, (4)
post options / proposals to a channel and wait for Jamie's reaction, (5)
write the accepted artifact to the workspace.

The pick-an-option pattern is shared by compose_haiku (JSON list of
options) and compose_meta's subject path (numbered markdown list).
:func:`refresh_loop` collapses both into one helper — pass the parser
that turns the LLM reply into a `list[str]` of options.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, NamedTuple, Optional

from ..tools import db, render
from ..tools.discord import interaction
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


async def try_send(
    channel,
    message: str,
    *,
    suppress_embeds: bool = True,
    job_label: str = "job",
) -> bool:
    """Best-effort ``channel.send`` — log on failure, never raise.

    Used by jobs that write an artifact to S3 / DB *before* posting the
    success card to Discord: if the post fails, the artifact is still
    durable and the JobResult records the outcome. The Discord glitch
    shouldn't bubble out as if the job failed. ``job_label`` is logged
    when send raises so the source is grep-able in workshop.log.
    """
    try:
        await channel.send(message, suppress_embeds=suppress_embeds)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: channel.send failed: %s", job_label, exc)
        return False

# How many times to re-prompt the model on a 🔄 refresh or an unparseable
# response before giving up. Shared across compose_haiku, compose_meta,
# and reorder.
MAX_REFRESH_ROUNDS = 3

# Cap how much of the issue body we feed the model.
ISSUE_BODY_CAP = 20_000

# The reorder job reads ``draft.md`` for Eddy's ordering pass, and the
# draft includes the full Journal section (rehosted images, all
# micro.blog posts in window) plus block markers — bulkier than the
# curated body. Bump the cap so Eddy sees the whole draft when
# reordering. The other compose jobs run on ``draft.md`` directly and
# don't need the extra headroom.
CREATE_FINAL_BODY_CAP = ISSUE_BODY_CAP + 6_000


def draft_body(issue_number: int) -> str:
    """The issue body rendered live from current DB state — the DB is the
    draft. Empty string when the issue has no actual content yet (an empty
    issue still renders its static tail — the Reddit line — which isn't a
    body worth composing against).

    Compose-* jobs use this to anchor on the same body the operator sees in
    the web preview. (Previously read the ``draft.md`` S3 projection, which
    died with the retired ``update-draft`` job.)
    """
    from ..tools import content_store, issue_items, renderers

    n = int(issue_number)
    has_rows = bool(issue_items.list_items(n))
    intro = content_store.read_issue(n, "intro.md")
    if not has_rows and not (intro and intro.strip()):
        return ""
    try:
        return renderers.render_body_for_issue(n).strip()
    except Exception:  # noqa: BLE001 — compose jobs degrade to no body
        logger.exception("draft_body: render failed for #%d", n)
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
    model: Optional[str] = None,
    cards_issue: Optional[int] = None,
    cards_filename: Optional[str] = None,
    cards_title: Optional[str] = None,
    cards_subtitle: Optional[str] = None,
    cards_body_kind: str = "serif",
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
        model: alias forwarded to ``bot.core(model=…)`` — ``None`` means
            use the persona's ``preferred_model``. The picker jobs
            (``compose-haiku`` / ``compose-meta``) pass ``"sonnet"`` to
            force the cheaper model since the output is short and
            picker-shaped; ``reorder`` leaves this ``None`` so
            it inherits Eddy's Opus default for the JSON proposal.
        cards_issue / cards_filename / cards_title: when all three are
            supplied, each round also renders the options to an HTML
            option-cards page at
            ``s3://files.thingelstad.com/weekly-thing/{cards_issue}/{cards_filename}.html``
            and appends "📄 {url}" to the Discord prompt so Jamie can
            read the options in the browser (with copy buttons) before
            reacting. Best-effort: a render failure just omits the
            URL and the Discord pick still works.
        cards_subtitle / cards_body_kind: optional formatting for the
            cards page (see :func:`tools.render.option_cards_html`).

    A 🔄 refresh appends a "fresh framings" hint to ``base_msg``; an
    unparseable response appends a tighter "follow the prompt's output
    shape" hint. Both feed into the next round."""
    user_msg = base_msg
    for _round in range(rounds):
        with db.AgentRun(persona, trigger=trigger) as agent_run:
            reply, _meta = await bot.core(latest=user_msg, history=[], model=model)
            agent_run.record_meta(_meta)
            agent_run.records_written = 1 if (reply and reply.strip()) else 0
        options = parser(reply or "")
        if not options:
            user_msg = base_msg + (
                "\n\n(That response didn't match the expected output shape — "
                "follow the prompt's format exactly, no surrounding prose.)"
            )
            continue
        pick = await _present_and_pick(
            bot, channel, options=options, pretty=pretty,
            prompt_label=prompt_label,
            cards_issue=cards_issue, cards_filename=cards_filename,
            cards_title=cards_title, cards_subtitle=cards_subtitle,
            cards_body_kind=cards_body_kind,
        )
        if pick == "refresh":
            user_msg = base_msg + "\n\n(Jamie asked for fresh options — give different framings, please.)"
            continue
        if pick is None or pick >= len(options):
            return None
        return options[pick]
    return None


async def _present_and_pick(
    bot,
    channel,
    *,
    options: list[str],
    pretty: Optional[Callable[[list[str]], list[str]]] = None,
    prompt_label: str,
    cards_issue: Optional[int] = None,
    cards_filename: Optional[str] = None,
    cards_title: Optional[str] = None,
    cards_subtitle: Optional[str] = None,
    cards_body_kind: str = "serif",
):
    """Render one round of option cards (best-effort) and wait for Jamie's
    pick. Shared by :func:`refresh_loop` (options come fresh from the model
    each round) and :func:`replay_pick` (options were produced up-front in a
    single batched call). Returns the raw ``interaction.await_choice`` result
    (0-based index, ``"refresh"``, or ``None``)."""
    shown = pretty(options) if pretty else options
    # Optional HTML option-cards page — uploaded on every round so the URL
    # stays valid across 🔄 refreshes (the URL is stable; only the contents
    # change). Best-effort: a render failure just omits the URL.
    round_label = prompt_label
    if cards_issue is not None and cards_filename and cards_title:
        url = await asyncio.to_thread(
            render.render_and_upload_option_cards,
            int(cards_issue), cards_filename, cards_title, options,
            subtitle=cards_subtitle, body_kind=cards_body_kind,
        )
        if url:
            round_label = f"{prompt_label}\n📄 {url}"
    return await interaction.await_choice(bot, channel, shown, prompt=round_label)


async def replay_pick(
    bot,
    channel,
    *,
    options: list[str],
    pretty: Optional[Callable[[list[str]], list[str]]] = None,
    prompt_label: str,
    regenerate: Optional[Callable[[], "asyncio.Future"]] = None,
    rounds: int = MAX_REFRESH_ROUNDS,
    cards_issue: Optional[int] = None,
    cards_filename: Optional[str] = None,
    cards_title: Optional[str] = None,
    cards_subtitle: Optional[str] = None,
    cards_body_kind: str = "serif",
) -> Optional[str]:
    """Run the option-cards pick UX over options that were **already
    generated** — no model call on the happy path. This is the second half of
    the batched-envelope flow: one LLM call produces every option up front
    (subjects + description + haikus), then each slot's picker replays its
    options here without re-prompting the model.

    Returns the picked string, or ``None`` on timeout / exhausted rounds.

    A 🔄 refresh re-invokes ``regenerate`` (an async callable returning a
    fresh ``list[str]`` for *this slot only*) when one is supplied — so Jamie
    can still ask for genuinely different framings, at the cost of one extra
    model call for that slot. When ``regenerate`` is ``None``, a refresh just
    re-shows the same options."""
    current = list(options)
    for _round in range(rounds):
        if not current:
            return None
        pick = await _present_and_pick(
            bot, channel, options=current, pretty=pretty,
            prompt_label=prompt_label,
            cards_issue=cards_issue, cards_filename=cards_filename,
            cards_title=cards_title, cards_subtitle=cards_subtitle,
            cards_body_kind=cards_body_kind,
        )
        if pick == "refresh":
            if regenerate is not None:
                fresh = await regenerate()
                if fresh:
                    current = list(fresh)
            continue
        if pick is None or pick >= len(current):
            return None
        return current[pick]
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
