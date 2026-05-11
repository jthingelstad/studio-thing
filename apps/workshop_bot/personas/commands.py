"""Discord slash-command surface — ``/workshop job <name>``.

The operator-facing slash command for workshop_bot, hosted on a single
persona bot (Eddy) — slash commands are scoped per Discord application
token, and one host is the cleanest cut.

All workshop_bot user-facing actions are **jobs** — deterministic Python
in ``apps/workshop_bot/jobs/``. The slash surface fires them. One command
shape::

    /workshop job <name> [<args>]

``job`` is a subcommand group under ``workshop``; job names are flat and
hyphenated, no further nesting. Each subcommand defers, runs the job's
async ``run(ctx, …)``, and acks the invoker ephemerally with the job's
result message. Jobs that also need to post to a channel during the run
do so via ``ctx.post(...)``.

Wired so far: ``start-issue``, ``update-draft``, ``issue-status``. Later
steps add ``create-final``, ``compose-haiku`` / ``-meta`` / ``-cta``,
``build-publish``, ``pinboard-scan``, ``promotion-prep``, ``daily-metrics``,
``add-campaign``, ``campaign-report``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..jobs import _base as jobs_base
from ..jobs import issue_status, start_issue, update_draft

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

    async def _run_and_ack(interaction, coro_factory, label: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await coro_factory()
        except Exception as exc:  # noqa: BLE001
            logger.exception("/workshop job %s failed", label)
            await interaction.followup.send(
                f"❌ `{label}` hit an error: `{type(exc).__name__}: {exc}`", ephemeral=True
            )
            return
        await interaction.followup.send(_clip(result.message), ephemeral=True)

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

    tree.add_command(workshop)
    return tree
