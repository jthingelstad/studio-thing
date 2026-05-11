"""Discord slash-command surface — ``/workshop job <name>``.

The operator-facing slash command for workshop_bot, hosted on a single
persona bot (Eddy) — slash commands are scoped per Discord application
token, and one host is the cleanest cut.

All workshop_bot user-facing actions are **jobs** — deterministic Python
in ``apps/workshop_bot/jobs/``. The slash surface fires them. One command
shape::

    /workshop job <name> [<args>]

``job`` is a subcommand group under ``workshop``; job names are flat and
hyphenated, no further nesting.

Two dispatch shapes:

- **Fast jobs** (most): defer, run the job's async ``run(ctx, …)``, ack
  the invoker ephemerally with the job's result message. (The followup
  send is wrapped in try/except — a Discord interaction token is only
  good for ~15 min, and although these jobs finish well inside that, a
  slow LLM hiccup shouldn't surface as a command error.)
- **Interactive jobs** (``create-final``, ``compose-haiku`` / ``-meta`` /
  ``-cta``): these post options to a channel and wait for Jamie's
  reaction — possibly far longer than the 15-min token window. So the
  command acks *immediately* ("started — react in #editorial / #supporters"),
  then awaits the job, which posts its own outcome to the channel. We never
  send a second followup; the channel posts carry the result.

Jobs that post to a channel during the run do so via ``ctx.post(...)``.

Wired: ``start-issue``, ``update-draft``, ``issue-status``,
``pinboard-scan``, ``create-final``, ``compose-haiku`` / ``-meta`` /
``-cta``, ``build-publish``, ``promotion-prep``, ``daily-metrics``,
``add-campaign``, ``campaign-report``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..jobs import _base as jobs_base
from ..jobs import (
    add_campaign,
    build_publish,
    campaign_report,
    compose_cta,
    compose_haiku,
    compose_meta,
    create_final,
    daily_metrics,
    issue_status,
    pinboard_scan,
    promotion_prep,
    start_issue,
    update_draft,
)

if TYPE_CHECKING:
    from .base import PersonaBot

logger = logging.getLogger("workshop.commands")

# Discord ephemeral followup cap is 2000 chars; leave headroom.
_MSG_CAP = 1900


def _ctx(bot) -> "jobs_base.JobContext":
    return jobs_base.JobContext(deps=getattr(bot, "deps", None), trigger="manual")


def _clip(text: str) -> str:
    return text if len(text) <= _MSG_CAP else text[: _MSG_CAP - 1] + "…"


def register_workshop_commands(bot: "PersonaBot") -> app_commands.CommandTree:
    """Attach the ``/workshop`` command tree to a host bot.

    Returns the ``CommandTree`` so the caller (the host bot's
    ``on_ready``) can sync it to a guild or globally.
    """
    tree = app_commands.CommandTree(bot)

    workshop = app_commands.Group(
        name="workshop",
        description="Workshop bot ops commands",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    job = app_commands.Group(
        name="job",
        description="Run a workshop job",
        parent=workshop,
    )

    async def _ack(interaction, text: str) -> None:
        """Send an ephemeral followup, swallowing an expired-token error."""
        try:
            await interaction.followup.send(_clip(text), ephemeral=True)
        except discord.HTTPException:  # token gone (>15 min) or transient — the work still happened
            logger.warning("/workshop: couldn't ack invoker (interaction expired?)")

    async def _run_and_ack(interaction, coro_factory, label: str) -> None:
        """Fast jobs: defer, run, ack with the result."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await coro_factory()
        except Exception as exc:  # noqa: BLE001
            logger.exception("/workshop job %s failed", label)
            await _ack(interaction, f"❌ `{label}` hit an error: `{type(exc).__name__}: {exc}`")
            return
        await _ack(interaction, result.message)

    async def _run_interactive(interaction, coro_factory, label: str, started: str) -> None:
        """Interactive jobs: ack immediately, then run (it can wait on a
        reaction for far longer than the interaction token lasts). The job
        posts its own outcome to the channel; we don't send a followup."""
        await interaction.response.send_message(started, ephemeral=True)
        try:
            await coro_factory()
        except Exception as exc:  # noqa: BLE001
            logger.exception("/workshop job %s failed", label)
            await _ack(interaction, f"❌ `{label}` hit an error: `{type(exc).__name__}: {exc}` — see logs / the channel.")

    @job.command(
        name="start-issue",
        description="Start a new in-flight issue (number, Saturday pub date, day count).",
    )
    @app_commands.describe(
        number="Issue number being assembled (e.g. 458)",
        pub_date="Publishing Saturday (YYYY-MM-DD)",
        day_count="Days to include before the cutoff — usually 7, sometimes 14",
    )
    async def start_issue_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        number: int,
        pub_date: str,
        day_count: int = 7,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: start_issue.run(
                _ctx(bot),
                number=number,
                pub_date=pub_date,
                day_count=int(day_count),
                set_by=str(interaction.user),
            ),
            "start-issue",
        )

    @job.command(
        name="update-draft",
        description="Re-project upstream content into the in-flight issue's draft.md.",
    )
    async def update_draft_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: update_draft.run(_ctx(bot)), "update-draft")

    @job.command(
        name="issue-status",
        description="Read-only state report on the in-flight issue.",
    )
    async def issue_status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: issue_status.run(_ctx(bot)), "issue-status")

    @job.command(
        name="pinboard-scan",
        description="Run Linky's Pinboard scan now (popular + toread + Briefly-suggest).",
    )
    async def pinboard_scan_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: pinboard_scan.run(_ctx(bot)), "pinboard-scan")

    @job.command(
        name="create-final",
        description="Eddy's reorder review → final.md (then run compose-haiku/meta/cta and build-publish).",
    )
    async def create_final_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: create_final.run(_ctx(bot)), "create-final",
            "Starting `create-final` — Eddy will post a reorder proposal in #editorial; react there.",
        )

    @job.command(
        name="compose-haiku",
        description="Generate haiku options for the in-flight issue → haiku.md.",
    )
    async def compose_haiku_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_haiku.run(_ctx(bot)), "compose-haiku",
            "Starting `compose-haiku` — options will post in #editorial; react there to pick.",
        )

    @job.command(
        name="compose-meta",
        description="Generate subject + description options for the in-flight issue → metadata.json.",
    )
    async def compose_meta_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_meta.run(_ctx(bot)), "compose-meta",
            "Starting `compose-meta` — options will post in #editorial; react there to pick.",
        )

    @job.command(
        name="compose-cta",
        description="Patty's membership-CTA proposal for the in-flight issue → cta-*.md.",
    )
    async def compose_cta_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_cta.run(_ctx(bot)), "compose-cta",
            "Starting `compose-cta` — Patty will post CTA framings in #supporters; react there to pick.",
        )

    @job.command(
        name="build-publish",
        description="Assemble publish.md from final.md + assets (refuses if anything required is missing).",
    )
    async def build_publish_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: build_publish.run(_ctx(bot)), "build-publish")

    @job.command(
        name="promotion-prep",
        description="Draft syndication content (Reddit + LinkedIn) for the latest published issue → #promotion.",
    )
    async def promotion_prep_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: promotion_prep.run(_ctx(bot)), "promotion-prep")

    @job.command(
        name="daily-metrics",
        description="Run Marky's daily website + subscriber + campaign report now (default-PASS if quiet).",
    )
    async def daily_metrics_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: daily_metrics.run(_ctx(bot)), "daily-metrics")

    @job.command(
        name="add-campaign",
        description="Register an ad campaign for Marky to track (name, ?ref= tag, optional expected signups/traffic).",
    )
    @app_commands.describe(
        name="A short name for the campaign (e.g. dense-discovery-may-2026)",
        ref="The ?ref= tag used in the campaign URL (e.g. dd-2026-05-15)",
        expected_signups="Optional — how many subscribers you expect from it",
        expected_traffic="Optional — how many visits you expect from it",
    )
    async def add_campaign_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        name: str,
        ref: str,
        expected_signups: int = 0,
        expected_traffic: int = 0,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: add_campaign.run(
                _ctx(bot), name=name, ref=ref,
                expected_signups=(expected_signups or None),
                expected_traffic=(expected_traffic or None),
            ),
            "add-campaign",
        )

    @job.command(
        name="campaign-report",
        description="List active campaigns + current performance vs expected.",
    )
    async def campaign_report_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: campaign_report.run(_ctx(bot)), "campaign-report")

    tree.add_command(workshop)
    return tree
