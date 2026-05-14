"""``/linky`` slash tree.

Linky owns link curation. ``/linky scan`` manually re-fires the
hourly ``pinboard-scan`` job; ``/linky followup …`` manages Linky's
own commitments. Ad-hoc commands (``/linky research <url>``,
``/linky pile``, ``/linky stats``) added in commit 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import follow_up as followup_job
from ...jobs import pinboard_scan
from ._shared import _ctx, make_ack, make_run_and_ack

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_linky_commands(
    bot: "PersonaBot",
    *,
    tree: Optional[app_commands.CommandTree] = None,
) -> app_commands.CommandTree:
    """Attach the ``/linky`` command tree to Linky's bot."""
    if tree is None:
        tree = app_commands.CommandTree(bot)

    _ack = make_ack("/linky")
    _run_and_ack = make_run_and_ack(_ack, "/linky")

    linky = app_commands.Group(
        name="linky",
        description="Linky (curator) — link scan, follow-ups",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    followup = app_commands.Group(
        name="followup", description="Linky's follow-up commitments", parent=linky
    )

    @linky.command(
        name="scan",
        description="Run Linky's Pinboard scan now (toread + discovery feeds) → #research.",
    )
    async def linky_scan_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: pinboard_scan.run(_ctx(bot)), "scan")

    @followup.command(
        name="list",
        description="Linky's pending follow-up commitments.",
    )
    async def followup_list_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: followup_job.list_open(_ctx(bot), persona="linky"),
            "followup list",
        )

    @followup.command(
        name="add",
        description="Schedule a Linky follow-up at a time, in N days, or when an issue is reached.",
    )
    @app_commands.describe(
        note="What the follow-up is about",
        when="ISO date YYYY-MM-DD (≈6pm) or datetime YYYY-MM-DDTHH:MM",
        in_days="…or a relative offset in days",
        at_issue="…or an issue number — fires once that issue is in flight",
    )
    async def followup_add_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        note: str,
        when: str = "",
        in_days: int = -1,
        at_issue: int = -1,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: followup_job.add(
                _ctx(bot), note=note, persona="linky",
                when=(when or ""),
                in_days=(None if int(in_days) < 0 else int(in_days)),
                at_issue=(None if int(at_issue) < 0 else int(at_issue)),
                created_by=str(interaction.user),
            ),
            "followup add",
        )

    @followup.command(
        name="cancel",
        description="Cancel a pending Linky follow-up by id (from `followup list`).",
    )
    @app_commands.describe(id="The follow-up id")
    async def followup_cancel_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, id: int
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: followup_job.cancel(_ctx(bot), followup_id=int(id), persona="linky"),
            "followup cancel",
        )

    tree.add_command(linky)
    return tree
