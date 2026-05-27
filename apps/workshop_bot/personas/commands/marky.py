"""``/marky`` slash tree.

Marky owns promotion + campaigns + engagement metrics. ``/marky
{prep,metrics}`` manually re-fire the promotion-prep and daily-metrics
jobs; ``/marky campaign {add,edit,report,copy,sunset}`` manages the
campaign ledger; ``/marky followup …`` manages her own commitments.
Ad-hoc commands (``/marky engagement``, ``/marky referrers``) added
in commit 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import (
    add_campaign,
    campaign_report,
    daily_metrics,
    follow_up as followup_job,
    marky_quicklook,
    ops,
    promotion_prep,
    share_card,
)
from ._shared import _ctx, make_ack, make_run_and_ack

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_marky_commands(
    bot: "PersonaBot",
    *,
    tree: Optional[app_commands.CommandTree] = None,
) -> app_commands.CommandTree:
    """Attach the ``/marky`` command tree to Marky's bot."""
    if tree is None:
        tree = app_commands.CommandTree(bot)

    _ack = make_ack("/marky")
    _run_and_ack = make_run_and_ack(_ack, "/marky")

    marky = app_commands.Group(
        name="marky",
        description="Marky (promotion) — drafts, metrics, campaigns, follow-ups",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    campaign = app_commands.Group(
        name="campaign", description="Ad-campaign ledger", parent=marky
    )
    followup = app_commands.Group(
        name="followup", description="Marky's follow-up commitments", parent=marky
    )

    # ── /marky {prep,metrics} ─────────────────────────────────────────

    @marky.command(
        name="prep",
        description="Draft syndication content (Reddit + LinkedIn) for the latest published issue → #promotion.",
    )
    async def marky_prep_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: promotion_prep.run(_ctx(bot)), "prep")

    @marky.command(
        name="metrics",
        description="Run the daily website + subscriber + campaign report now (default-PASS if quiet).",
    )
    async def marky_metrics_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: daily_metrics.run(_ctx(bot)), "metrics")

    @marky.command(
        name="share",
        description="Post (or re-pin) the Share card — the last-published issue's syndication surface.",
    )
    async def marky_share_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: share_card.run(_ctx(bot)), "share")

    @marky.command(
        name="engagement",
        description="Quick read — subscriber growth + site engagement over a trailing window.",
    )
    @app_commands.describe(days="Trailing window in days (default 7, max 90)")
    async def marky_engagement_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, days: int = 7
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: marky_quicklook.engagement(_ctx(bot), days=int(days)),
            "engagement",
        )

    @marky.command(
        name="referrers",
        description="Tinylytics referrer drill-down over a trailing window (top 20).",
    )
    @app_commands.describe(days="Trailing window in days (default 30, max 365)")
    async def marky_referrers_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, days: int = 30
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: marky_quicklook.referrers(_ctx(bot), days=int(days)),
            "referrers",
        )

    # ── /marky campaign ───────────────────────────────────────────────

    @campaign.command(
        name="add",
        description="Register an ad campaign for Marky to track (name, ?ref= tag, optional url/platform/cost/copy/started_at).",
    )
    @app_commands.describe(
        name="A short name for the campaign (e.g. dense-discovery-may-2026)",
        ref="The ?ref= tag from the campaign URL, exact case (e.g. DenseDiscovery-388)",
        url="Optional — the raw destination URL people clicked",
        platform="Optional — channel (DenseDiscovery, LinkedIn, Bluesky, …)",
        cost="Optional — actual dollars paid for the placement",
        copy="Optional — the actual promo text that ran in the placement (set later with campaign copy)",
        started_at="Optional — YYYY-MM-DD start date (defaults to today; pass a future date for scheduled placements)",
    )
    async def campaign_add_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        name: str,
        ref: str,
        url: str = "",
        platform: str = "",
        cost: float = 0.0,
        copy: str = "",
        started_at: str = "",
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: add_campaign.run(
                _ctx(bot), name=name, ref=ref,
                url=(url or None),
                platform=(platform or None),
                cost=(cost if cost > 0 else None),
                copy=(copy or None),
                started_at=(started_at or None),
            ),
            "campaign add",
        )

    @campaign.command(
        name="edit",
        description="Change details on a running campaign — ref, url, platform, cost, notes, copy.",
    )
    @app_commands.describe(
        name="The campaign name (as registered with campaign add)",
        ref="New ?ref= tag, exact case (leave blank to keep the current one)",
        url="New destination URL (leave blank to keep)",
        platform="New platform/channel (leave blank to keep)",
        started_at="When it started — YYYY-MM-DD (leave blank to keep)",
        cost="Revised cost in dollars (-1 to keep the current value)",
        notes="Notes to set (leave blank to keep; can't clear here)",
        copy="The promo text that ran (leave blank to keep; use `campaign copy` to clear it)",
    )
    async def campaign_edit_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        name: str,
        ref: str = "",
        url: str = "",
        platform: str = "",
        started_at: str = "",
        cost: float = -1.0,
        notes: str = "",
        copy: str = "",
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: ops.campaign_edit(
                _ctx(bot), name=name,
                ref=(ref or None),
                url=(url or None),
                platform=(platform or None),
                started_at=(started_at or None),
                cost=(None if cost < 0 else float(cost)),
                notes=(notes or None), copy=(copy or None),
            ),
            "campaign edit",
        )

    @campaign.command(
        name="report",
        description="List active campaigns + current performance vs expected.",
    )
    async def campaign_report_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: campaign_report.run(_ctx(bot)), "campaign report")

    @campaign.command(
        name="copy",
        description="Record the promo text that ran in a campaign's placement (empty text clears it).",
    )
    @app_commands.describe(
        name="The campaign name (as registered with campaign add)",
        copy="The actual ad copy that ran — leave empty to clear what's stored",
    )
    async def campaign_copy_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, name: str, copy: str = ""
    ) -> None:
        await _run_and_ack(
            interaction, lambda: ops.campaign_copy(_ctx(bot), name=name, copy=(copy or None)), "campaign copy"
        )

    @campaign.command(
        name="sunset",
        description="Mark an ad campaign over — metrics stops polling it.",
    )
    @app_commands.describe(name="The campaign name (as registered with campaign add)")
    async def campaign_sunset_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, name: str
    ) -> None:
        await _run_and_ack(
            interaction, lambda: ops.campaign_sunset(_ctx(bot), name=name), "campaign sunset"
        )

    # ── /marky followup ───────────────────────────────────────────────

    @followup.command(
        name="list",
        description="Marky's pending follow-up commitments.",
    )
    async def followup_list_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: followup_job.list_open(_ctx(bot), persona="marky"),
            "followup list",
        )

    @followup.command(
        name="add",
        description="Schedule a Marky follow-up at a time, in N days, or when an issue is reached.",
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
                _ctx(bot), note=note, persona="marky",
                when=(when or ""),
                in_days=(None if int(in_days) < 0 else int(in_days)),
                at_issue=(None if int(at_issue) < 0 else int(at_issue)),
                created_by=str(interaction.user),
            ),
            "followup add",
        )

    @followup.command(
        name="cancel",
        description="Cancel a pending Marky follow-up by id (from `followup list`).",
    )
    @app_commands.describe(id="The follow-up id")
    async def followup_cancel_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, id: int
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: followup_job.cancel(_ctx(bot), followup_id=int(id), persona="marky"),
            "followup cancel",
        )

    tree.add_command(marky)
    return tree
