"""``/scout`` slash tree.

Scout is the producer — owner of the production slate. The Part 1
surface is intentionally minimal and read-only: ``/scout status`` (a
slate-framed ops snapshot) and ``/scout slate`` (the production-slate
view, newsletter-only data today).

The production-management slash subgroup (``/scout issue start``,
``built``, ``publish``, ``put-to-bed``, ``reset``, etc.) migrates over
from ``/eddy issue …`` in Part 2, after WT350 publishes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import scout_slate, scout_status
from ._shared import _ctx, make_ack, make_run_and_ack

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_scout_commands(
    bot: "PersonaBot",
    *,
    tree: Optional[app_commands.CommandTree] = None,
) -> app_commands.CommandTree:
    """Attach the ``/scout`` command tree to Scout's bot."""
    if tree is None:
        tree = app_commands.CommandTree(bot)

    _ack = make_ack("/scout")
    _run_and_ack = make_run_and_ack(_ack, "/scout")

    scout = app_commands.Group(
        name="scout",
        description="Scout (producer) — production slate + bot status",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ── /scout status ────────────────────────────────────────────────
    @scout.command(
        name="status",
        description="Scout's read-only ops snapshot — slate, locks, recent runs.",
    )
    async def scout_status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: scout_status.run(_ctx(bot)),
            "status",
        )

    # ── /scout slate ─────────────────────────────────────────────────
    @scout.command(
        name="slate",
        description="The production slate (newsletter today; blog/podcast/membership in Phase 2).",
    )
    @app_commands.describe(
        kind="Optional surface filter (newsletter / blog / podcast / membership)",
    )
    async def scout_slate_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, kind: str = ""
    ) -> None:
        normalized: Optional[str] = kind.strip().lower() or None
        await _run_and_ack(
            interaction,
            lambda: scout_slate.run(
                _ctx(bot),
                kind=normalized,  # type: ignore[arg-type]
            ),
            "slate",
        )

    tree.add_command(scout)
    return tree
