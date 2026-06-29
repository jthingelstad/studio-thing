"""``/linky`` slash tree.

Linky owns link curation. ``/linky scan`` manually re-fires the
scheduled ``pinboard-scan`` job; ``/linky followup …`` manages Linky's
own commitments. Ad-hoc commands (``/linky research <url>``,
``/linky pile``, ``/linky stats``) added in commit 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import (
    feedbin_ingest,
    follow_up as followup_job,
    linky_quicklook,
    linky_research,
    pinboard_scan,
)
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
        description="Run Linky's Pinboard toread scan now (discovery feeds are paused).",
    )
    async def linky_scan_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: pinboard_scan.run(_ctx(bot)), "scan")

    @linky.command(
        name="feedbin",
        description="Mirror Feedbin starred items to Pinboard as toread bookmarks (idempotent).",
    )
    async def linky_feedbin_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction, lambda: feedbin_ingest.run(_ctx(bot)), "feedbin",
        )

    @linky.command(
        name="research",
        description="Ad-hoc per-URL research — Linky's read on a URL you paste, posted to #research.",
    )
    @app_commands.describe(url="The http(s) URL to research")
    async def linky_research_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, url: str
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: linky_research.run(_ctx(bot), url=url, invoker=str(interaction.user)),
            "research",
        )

    @linky.command(
        name="pile",
        description="Show the currently `_brief`-tagged Pinboard bookmarks (the Briefly pile).",
    )
    @app_commands.describe(limit="How many to list (default 25, max 40)")
    async def linky_pile_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, limit: int = 25
    ) -> None:
        await _run_and_ack(
            interaction, lambda: linky_quicklook.pile(_ctx(bot), limit=int(limit)), "pile",
        )

    @linky.command(
        name="stats",
        description="Summary of Linky's recent surfacing activity (cards per source, last N days).",
    )
    @app_commands.describe(days="Trailing window in days (default 7, max 90)")
    async def linky_stats_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, days: int = 7
    ) -> None:
        await _run_and_ack(
            interaction, lambda: linky_quicklook.stats(_ctx(bot), days=int(days)), "stats",
        )

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
