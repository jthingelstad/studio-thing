"""Discord slash-command surface — ``/workshop``.

First operator-facing slash command on workshop_bot. Hosted on a single
persona bot (Eddy) — slash commands are scoped per Discord application
token, and one host is the cleanest first cut.

Subcommands today:

  - ``/workshop heartbeat <agent>`` — fire one persona's heartbeat on
    demand. ``<agent>`` is one of the four personas, or ``team`` to
    fire all four in parallel via ``asyncio.gather``.

The handler reuses the existing ``scheduler.handlers.heartbeat`` so a
manual fire is indistinguishable from a scheduled fire (same
``db.AgentRun`` rows, same home-channel post, same PASS-swallow). The
invoker always gets an ephemeral ack — including on PASS — so a quiet
heartbeat doesn't look like a silent failure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..scheduler import handlers
from ..scheduler import jobs as jobs_module
from ..scheduler.runner import JobContext

if TYPE_CHECKING:
    from .base import PersonaBot
    from .team import TeamRegistry

logger = logging.getLogger("workshop.commands")

PERSONAS: tuple[str, ...] = ("eddy", "linky", "marky", "patty")

_RESULT_LABELS: dict[str, str] = {
    "posted": "posted to home channel",
    "pass": "PASS (nothing to surface)",
    "disabled": "skipped — heartbeats disabled",
    "skipped": "skipped — persona/prompt unavailable",
    "error": "error during agent loop",
}


def render_result(result: str) -> str:
    return _RESULT_LABELS.get(result, result)


async def run_one_heartbeat(team: "TeamRegistry", persona: str) -> str:
    """Fire one persona's heartbeat and return its status string.

    Reuses the persona's existing heartbeat ``JobSpec`` as a cheap
    context carrier so manual fires share the scheduled path's
    ``ctx.job`` shape (handler logs reference ``ctx.job.id``).
    """
    spec = jobs_module.by_id(f"{persona}-heartbeat")
    if spec is None:
        return "skipped"
    ctx = JobContext(team=team, job=spec)
    try:
        return await handlers.heartbeat(ctx, persona)
    except Exception:  # noqa: BLE001
        logger.exception("/workshop heartbeat %s: unexpected error", persona)
        return "error"


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

    agent_choices = [
        app_commands.Choice(name=p, value=p) for p in PERSONAS
    ] + [app_commands.Choice(name="team", value="team")]

    @workshop.command(
        name="heartbeat",
        description="Force a heartbeat on demand for one persona, or 'team' for all four.",
    )
    @app_commands.describe(agent="Which persona, or 'team' for all four")
    @app_commands.choices(agent=agent_choices)
    async def heartbeat_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        agent: app_commands.Choice[str],
    ) -> None:
        # Heartbeats can take 20–40s; defer immediately so Discord's
        # 3-second response window doesn't expire on us.
        await interaction.response.defer(ephemeral=True, thinking=True)

        team = bot.deps.team
        if team is None:
            await interaction.followup.send(
                "Team registry unavailable; can't dispatch heartbeat.",
                ephemeral=True,
            )
            return

        if agent.value == "team":
            results = await asyncio.gather(
                *(run_one_heartbeat(team, p) for p in PERSONAS),
                return_exceptions=False,
            )
            lines = [
                f"`{p}`: {render_result(r)}" for p, r in zip(PERSONAS, results)
            ]
            await interaction.followup.send(
                "**Team heartbeat**\n" + "\n".join(lines),
                ephemeral=True,
            )
            return

        result = await run_one_heartbeat(team, agent.value)
        await interaction.followup.send(
            f"`{agent.value}`: {render_result(result)}",
            ephemeral=True,
        )

    tree.add_command(workshop)
    return tree
