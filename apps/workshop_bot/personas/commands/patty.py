"""``/patty`` slash tree.

Patty is the supporter steward. ``/patty cta`` runs the per-issue
membership-CTA composer; ``/patty goal {set,done}`` opens and closes
goal milestones; ``/patty followup …`` manages her own commitments.
Ad-hoc commands (``/patty progress``, ``/patty nonprofit``, ``/patty
supporters``) added in commit 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import compose_cta, follow_up as followup_job, ops, patty_quicklook
from ._shared import _ctx, make_ack, make_run_and_ack, make_run_interactive

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_patty_commands(
    bot: "PersonaBot",
    *,
    tree: Optional[app_commands.CommandTree] = None,
) -> app_commands.CommandTree:
    """Attach the ``/patty`` command tree to Patty's bot."""
    if tree is None:
        tree = app_commands.CommandTree(bot)

    _ack = make_ack("/patty")
    _run_and_ack = make_run_and_ack(_ack, "/patty")
    _run_interactive = make_run_interactive("/patty")

    patty = app_commands.Group(
        name="patty",
        description="Patty (supporter steward) — CTAs, goals, follow-ups",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    goal = app_commands.Group(
        name="goal", description="Membership / revenue milestones", parent=patty
    )
    followup = app_commands.Group(
        name="followup", description="Patty's follow-up commitments", parent=patty
    )

    # ── /patty cta ────────────────────────────────────────────────────

    @patty.command(
        name="cta",
        description="Patty's membership-CTA proposal for the in-flight issue → cta-*.md.",
    )
    async def patty_cta_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_cta.run(_ctx(bot)), "cta",
            "Starting `cta` — Patty will post CTA framings in #supporters; react there to pick.",
        )

    # ── /patty quick-look reads ───────────────────────────────────────

    @patty.command(
        name="progress",
        description="Current goal progress (active goal + live count + anniversary pacing).",
    )
    async def patty_progress_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: patty_quicklook.progress(_ctx(bot)), "progress")

    @patty.command(
        name="nonprofit",
        description="Current nonprofit details + last few past beneficiaries.",
    )
    async def patty_nonprofit_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: patty_quicklook.nonprofit(_ctx(bot)), "nonprofit")

    @patty.command(
        name="supporters",
        description="Recent Stripe activity — YTD total + recent donations.",
    )
    @app_commands.describe(days="Trailing window for donation list (default 14, max 365)")
    async def patty_supporters_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, days: int = 14
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: patty_quicklook.supporters(_ctx(bot), days=int(days)),
            "supporters",
        )

    # ── /patty goal ───────────────────────────────────────────────────

    @goal.command(
        name="set",
        description="Open a new Patty milestone — refuses if one's already active (mark it done first).",
    )
    @app_commands.describe(
        kind="members (live Buttondown count) or dollars (live Stripe total)",
        value="The target to hit (e.g. 75)",
        notes="Optional context for the goal",
    )
    async def goal_set_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, kind: str, value: int, notes: str = ""
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: ops.set_goal(_ctx(bot), kind=kind, value=int(value), notes=(notes or None)),
            "goal set",
        )

    @goal.command(
        name="done",
        description="Mark the active Patty milestone hit (today) — then set the next with goal set.",
    )
    @app_commands.describe(notes="Optional note about hitting it")
    async def goal_done_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, notes: str = ""
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: ops.goal_achieved(_ctx(bot), notes=(notes or None)),
            "goal done",
        )

    # ── /patty followup ───────────────────────────────────────────────

    @followup.command(
        name="list",
        description="Patty's pending follow-up commitments.",
    )
    async def followup_list_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: followup_job.list_open(_ctx(bot), persona="patty"),
            "followup list",
        )

    @followup.command(
        name="add",
        description="Schedule a Patty follow-up at a time, in N days, or when an issue is reached.",
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
                _ctx(bot), note=note, persona="patty",
                when=(when or ""),
                in_days=(None if int(in_days) < 0 else int(in_days)),
                at_issue=(None if int(at_issue) < 0 else int(at_issue)),
                created_by=str(interaction.user),
            ),
            "followup add",
        )

    @followup.command(
        name="cancel",
        description="Cancel a pending Patty follow-up by id (from `followup list`).",
    )
    @app_commands.describe(id="The follow-up id")
    async def followup_cancel_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, id: int
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: followup_job.cancel(_ctx(bot), followup_id=int(id), persona="patty"),
            "followup cancel",
        )

    tree.add_command(patty)
    return tree
