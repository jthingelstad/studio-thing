"""Discord slash-command surface — ``/workshop`` grouped by content artifact.

The operator-facing slash commands for workshop_bot, hosted on a single
persona bot (Eddy) — slash commands are scoped per Discord application
token, and one host is the cleanest cut.

Every user-facing action is a deterministic Python job in
``apps/workshop_bot/jobs/`` (the "job" is the internal unit of scheduling
and locking). The slash surface doesn't expose that word — it's organised
around the *thing* you're working on:

    /workshop issue start | update | status | final | haiku | subject | cta | publish
    /workshop links scan
    /workshop promo prep | metrics
    /workshop campaign add | report | copy | sunset
    /workshop goal set | done
    /workshop status                          ← bot-health snapshot, not a content job

Two dispatch shapes:

- **Fast jobs** (most): defer, run the job's async ``run(ctx, …)``, ack
  the invoker ephemerally with the job's result message. (The followup
  send is wrapped in try/except — a Discord interaction token is only
  good for ~15 min, and although these jobs finish well inside that, a
  slow LLM hiccup shouldn't surface as a command error.)
- **Interactive jobs** (``issue final``, ``issue haiku`` / ``subject`` /
  ``cta``): these post options to a channel and wait for Jamie's reaction
  — possibly far longer than the 15-min token window. So the command acks
  *immediately* ("started — react in #editorial / #supporters"), then
  awaits the job, which posts its own outcome to the channel. We never
  send a second followup; the channel posts carry the result.

Jobs that post to a channel during the run do so via ``ctx.post(...)``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..jobs import _base as jobs_base
from ..jobs import status as status_job
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
    ops,
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
        description="Workshop bot — assemble the issue, run promotion, track goals",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    issue = app_commands.Group(
        name="issue", description="Assemble the in-flight issue", parent=workshop
    )
    links = app_commands.Group(
        name="links", description="Link curation (Pinboard)", parent=workshop
    )
    promo = app_commands.Group(
        name="promo", description="Promotion drafts + metrics", parent=workshop
    )
    campaign = app_commands.Group(
        name="campaign", description="Ad-campaign ledger", parent=workshop
    )
    goal = app_commands.Group(
        name="goal", description="Membership / revenue milestones", parent=workshop
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
            logger.exception("/workshop %s failed", label)
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
            logger.exception("/workshop %s failed", label)
            await _ack(interaction, f"❌ `{label}` hit an error: `{type(exc).__name__}: {exc}` — see logs / the channel.")

    # ── /workshop issue ───────────────────────────────────────────────

    @issue.command(
        name="start",
        description="Begin assembling a new issue (number, Saturday pub date, day count).",
    )
    @app_commands.describe(
        number="Issue number being assembled (e.g. 458)",
        pub_date="Publishing Saturday (YYYY-MM-DD)",
        day_count="Days to include before the cutoff — usually 7, sometimes 14",
    )
    async def issue_start_cmd(  # type: ignore[misc]
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
            "issue start",
        )

    @issue.command(
        name="update",
        description="Re-project upstream content (Pinboard + micro.blog + assets) into draft.md.",
    )
    async def issue_update_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: update_draft.run(_ctx(bot)), "issue update")

    @issue.command(
        name="status",
        description="Read-only state report on the in-flight issue (sections + assets).",
    )
    async def issue_status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: issue_status.run(_ctx(bot)), "issue status")

    @issue.command(
        name="final",
        description="Eddy's reorder review → final.md (then run issue haiku/subject/cta and issue publish).",
    )
    async def issue_final_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: create_final.run(_ctx(bot)), "issue final",
            "Starting `issue final` — Eddy will post a reorder proposal in #editorial; react there.",
        )

    @issue.command(
        name="haiku",
        description="Generate haiku options for the in-flight issue → haiku.md.",
    )
    async def issue_haiku_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_haiku.run(_ctx(bot)), "issue haiku",
            "Starting `issue haiku` — options will post in #editorial; react there to pick.",
        )

    @issue.command(
        name="subject",
        description="Pick the email subject (5 options) then generate the description → metadata.json.",
    )
    async def issue_subject_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_meta.run(_ctx(bot)), "issue subject",
            "Starting `issue subject` — 5 subject options then a description will post in #editorial; react there to pick.",
        )

    @issue.command(
        name="cta",
        description="Patty's membership-CTA proposal for the in-flight issue → cta-*.md.",
    )
    async def issue_cta_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_cta.run(_ctx(bot)), "issue cta",
            "Starting `issue cta` — Patty will post CTA framings in #supporters; react there to pick.",
        )

    @issue.command(
        name="publish",
        description="Assemble publish.md from final.md + assets (refuses if anything required is missing).",
    )
    async def issue_publish_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: build_publish.run(_ctx(bot)), "issue publish")

    # ── /workshop links ───────────────────────────────────────────────

    @links.command(
        name="scan",
        description="Run Linky's Pinboard scan now (popular + toread + Briefly-suggest) → #research.",
    )
    async def links_scan_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: pinboard_scan.run(_ctx(bot)), "links scan")

    # ── /workshop promo ───────────────────────────────────────────────

    @promo.command(
        name="prep",
        description="Draft syndication content (Reddit + LinkedIn) for the latest published issue → #promotion.",
    )
    async def promo_prep_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: promotion_prep.run(_ctx(bot)), "promo prep")

    @promo.command(
        name="metrics",
        description="Run Marky's daily website + subscriber + campaign report now (default-PASS if quiet).",
    )
    async def promo_metrics_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: daily_metrics.run(_ctx(bot)), "promo metrics")

    # ── /workshop campaign ────────────────────────────────────────────

    @campaign.command(
        name="add",
        description="Register an ad campaign for Marky to track (name, ?ref= tag, optional expected signups/traffic).",
    )
    @app_commands.describe(
        name="A short name for the campaign (e.g. dense-discovery-may-2026)",
        ref="The ?ref= tag from the campaign URL, exact case (e.g. DenseDiscovery-388)",
        expected_signups="Optional — how many subscribers you expect from it",
        expected_traffic="Optional — how many visits you expect from it",
        copy="Optional — the actual promo text that ran in the placement (set later with campaign copy)",
    )
    async def campaign_add_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        name: str,
        ref: str,
        expected_signups: int = 0,
        expected_traffic: int = 0,
        copy: str = "",
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: add_campaign.run(
                _ctx(bot), name=name, ref=ref,
                expected_signups=(expected_signups or None),
                expected_traffic=(expected_traffic or None),
                copy=(copy or None),
            ),
            "campaign add",
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
        description="Mark an ad campaign over — promo metrics stops polling it.",
    )
    @app_commands.describe(name="The campaign name (as registered with campaign add)")
    async def campaign_sunset_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, name: str
    ) -> None:
        await _run_and_ack(
            interaction, lambda: ops.campaign_sunset(_ctx(bot), name=name), "campaign sunset"
        )

    # ── /workshop goal ────────────────────────────────────────────────

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

    # ── /workshop status ──────────────────────────────────────────────

    @workshop.command(
        name="status",
        description="Ops snapshot — issue window, goal/campaigns, held job locks, recent runs.",
    )
    async def status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: status_job.run(_ctx(bot)), "status")

    tree.add_command(workshop)
    return tree
