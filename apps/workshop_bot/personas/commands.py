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

This step (Step 1 of the content-loop redesign) wires only ``start-issue``
— it records the in-flight issue window in workshop.db. Later steps extend
it (create the S3 folder, write ``draft.md`` from the starter template,
auto-fire ``update-draft``) and add the rest of the job tree
(``update-draft``, ``issue-status``, the compose jobs, …).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..tools import db, issue

if TYPE_CHECKING:
    from .base import PersonaBot

logger = logging.getLogger("workshop.commands")


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

    @job.command(
        name="start-issue",
        description="Start a new in-flight issue (number, Saturday pub date, day count).",
    )
    @app_commands.describe(
        number="Issue number being assembled (e.g. 348)",
        pub_date="Publishing Saturday (YYYY-MM-DD)",
        day_count="Days to include before the cutoff — usually 7, sometimes 14",
    )
    async def start_issue_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        number: int,
        pub_date: str,
        day_count: int = 7,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=False)
        try:
            window = issue.compute_window(pub_date, int(day_count))
        except issue.IssueWindowError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        try:
            db.set_issue_window(
                issue_number=int(number),
                pub_date=window["pub_date"],
                end_date=window["end_date"],
                start_date=window["start_date"],
                day_count=window["day_count"],
                set_by=str(interaction.user),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("/workshop job start-issue: db write failed")
            await interaction.followup.send(
                f"❌ Couldn't save window: `{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )
            return

        days_word = "day" if window["day_count"] == 1 else "days"
        await interaction.followup.send(
            f"✅ Issue **#{number}** set as the in-flight issue.\n"
            f"- Publish: **{window['pub_date']}** (Sat)\n"
            f"- Content cutoff (end_date): **{window['end_date']}**\n"
            f"- Window start (prior cutoff): **{window['start_date']}**\n"
            f"- Span: **{window['day_count']} {days_word}**",
            ephemeral=True,
        )

    tree.add_command(workshop)
    return tree
