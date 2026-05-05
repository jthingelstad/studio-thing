"""Patty — supporter steward. Tool-using; gets get_support_state in addition to universal."""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord

from ..tools import agent_loop, agent_tools, anthropic_client, db, discord_io
from .base import PersonaBot

logger = logging.getLogger("workshop.patty")

PATTY_TOOLS: list[str] = list(agent_tools.UNIVERSAL) + ["get_support_state"]


class PattyBot(PersonaBot):
    persona = "patty"
    name = "Patty"
    home_channel_env = "DISCORD_CHANNEL_SUPPORTERS"

    async def core(
        self,
        *,
        latest: str,
        history: Optional[list[dict[str, str]]] = None,
        model: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        issue_index = anthropic_client.format_issue_index(self.deps.corpus.corpus["issues"])
        return agent_loop.run(
            persona=self.persona,
            user_message=latest or "(no new content; continue from history)",
            history=history or [],
            tools=PATTY_TOOLS,
            deps=self.deps,
            model=model,
            issue_index=issue_index,
        )

    async def handle(
        self,
        *,
        message: discord.Message,
        body: str,
        attachment: str,
        model: str,
        history: list[dict[str, str]],
    ) -> None:
        latest = (attachment or body).strip()
        if not latest and not history:
            await message.reply(
                "Hey — want me to draft a CTA, or thinking about something else?",
                mention_author=False,
            )
            return

        async with message.channel.typing():
            with db.AgentRun(self.persona, trigger="mention") as run:
                answer, meta = await self.core(latest=latest, history=history, model=model)
                db.insert_agent_output(
                    agent_name=self.persona,
                    output_type="reply",
                    content=answer,
                    metadata={
                        **meta,
                        "discord_message_id": str(message.id),
                        "discord_channel_id": str(message.channel.id),
                    },
                )
                run.records_written = 1

        await discord_io.send_chunked(message, answer)
