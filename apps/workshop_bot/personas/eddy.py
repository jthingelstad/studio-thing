"""Eddy — editor. Tool-using agent loop, archive-aware."""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord

from ..tools import agent_loop, agent_tools, anthropic_client, db, discord_io
from .base import PersonaBot

logger = logging.getLogger("workshop.eddy")

EDDY_TOOLS: list[str] = list(agent_tools.UNIVERSAL)


class EddyBot(PersonaBot):
    persona = "eddy"
    name = "Eddy"
    home_channel_env = "DISCORD_CHANNEL_EDITORIAL"

    async def core(
        self,
        *,
        latest: str,
        history: Optional[list[dict[str, str]]] = None,
        model: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        # Issue index lives in a cached system block — gives Eddy a cheap
        # "what issues exist" map without a tool call. Tool calls do the
        # depth (search_archive / get_issue / get_section / quote_search).
        issue_index = anthropic_client.format_issue_index(self.deps.corpus.corpus["issues"])
        return agent_loop.run(
            persona=self.persona,
            user_message=latest,
            history=history or [],
            tools=EDDY_TOOLS,
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
            await message.reply("Hey — what are we looking at?", mention_author=False)
            return

        async with message.channel.typing():
            with db.AgentRun(self.persona, trigger="mention") as run:
                answer, meta = await self.core(latest=latest, history=history, model=model)
                output_id = db.insert_agent_output(
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
                logger.info(
                    "eddy reply #%d (%d iter, %d tool calls)",
                    output_id, meta.get("iterations", 0), len(meta.get("tool_calls") or []),
                )

        await discord_io.send_chunked(message, answer)
