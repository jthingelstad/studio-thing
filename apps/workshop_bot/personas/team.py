"""Team-mention coordinator.

When Jamie @-mentions the Team role, all four persona bots receive the
same Discord event. Without coordination they'd all answer in parallel
without seeing each other. The TeamRegistry:

1. Locks per-message so only one bot orchestrates the round.
2. Runs each persona's ``core()`` sequentially in a fixed order, posting
   each reply via that bot's own client (so the response appears under
   the right avatar/name).
3. Refetches conversation history before each persona runs, so a later
   persona sees the earlier ones' replies as ``[Name] …`` user turns —
   that's how cross-talk gets baked into a single team round.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from ..tools import conversation, discord_io

if TYPE_CHECKING:
    import discord

    from .base import PersonaBot

logger = logging.getLogger("workshop.team")

# Order matters — first persona answers cold; later personas see earlier
# replies in their history and can build on / push back.
TEAM_ORDER: tuple[str, ...] = ("eddy", "marky", "patty", "linky")

# Bound how many message ids we remember to avoid unbounded growth on a
# long-lived process. ``OrderedDict``-as-set gives FIFO eviction.
RECENT_ID_CAP = 500
POSTED_ID_CAP = 1000


def _trim_ordered_set(data: "OrderedDict[int, None]", cap: int) -> None:
    """In-place FIFO trim to ``cap`` entries."""
    while len(data) > cap:
        data.popitem(last=False)


class TeamRegistry:
    def __init__(self) -> None:
        self.bots: dict[str, "PersonaBot"] = {}
        # ``OrderedDict``-as-ordered-set keyed by message_id; values unused.
        # Insertion order is preserved by the language, so FIFO eviction
        # is deterministic (unlike a plain set).
        self._handled: "OrderedDict[int, None]" = OrderedDict()
        self._claim_lock = asyncio.Lock()
        # Message ids the team orchestrator has posted. Peer-reaction code
        # skips these so we don't double-evaluate during a team round.
        self._posted_message_ids: "OrderedDict[int, None]" = OrderedDict()

    def is_team_post(self, message_id: int) -> bool:
        return message_id in self._posted_message_ids

    def register(self, bot: "PersonaBot") -> None:
        self.bots[bot.persona] = bot

    async def claim(self, message_id: int) -> bool:
        """Return True if this caller wins the right to orchestrate the round."""
        async with self._claim_lock:
            if message_id in self._handled:
                return False
            self._handled[message_id] = None
            _trim_ordered_set(self._handled, RECENT_ID_CAP)
            return True

    async def orchestrate(
        self,
        *,
        message: "discord.Message",
        body: str,
        attachment: str,
        model: "str | None",
    ) -> None:
        latest = (attachment or body).strip()
        if not latest:
            # @Team with no body — let one bot say "what's up?" and bow out.
            first = self.bots.get(TEAM_ORDER[0])
            if first is not None:
                channel = first.get_channel(message.channel.id)
                if channel is not None:
                    await channel.send("Team's here. What's up?")
            return

        for persona_name in TEAM_ORDER:
            bot = self.bots.get(persona_name)
            if bot is None or bot.user is None:
                continue
            channel = bot.get_channel(message.channel.id)
            if channel is None:
                logger.warning(
                    "%s: channel %s not visible; skipping team round",
                    persona_name, message.channel.id,
                )
                continue

            try:
                # Pre-trigger history + this-round agent replies, but not the
                # trigger itself (we pass that as `latest` below).
                history = await self._build_round_history(
                    channel=channel,
                    trigger=message,
                    bot_user_id=bot.user.id,
                )
                async with channel.typing():
                    answer, meta = await bot.core(
                        latest=latest, history=history, model=model
                    )
                if answer.strip():
                    await self._send_via(channel, answer)
                logger.info(
                    "team: %s replied (%d iter, %d tool calls)",
                    persona_name,
                    meta.get("iterations", 0),
                    len(meta.get("tool_calls") or []),
                )
            except Exception:  # noqa: BLE001
                logger.exception("team: %s core failed", persona_name)
                try:
                    await channel.send(f"(Sorry, {persona_name.capitalize()} hit an error and bowed out.)")
                except Exception:  # noqa: BLE001
                    pass

    async def _send_via(self, channel, text: str) -> None:
        """Post chunked text via a specific bot's channel object.

        Records the resulting message ids so peer-reaction code can skip
        them — peers shouldn't also evaluate posts the orchestrator made.
        """
        if not text.strip():
            return
        for chunk in discord_io.split_for_discord(text):
            sent = await channel.send(chunk)
            self._posted_message_ids[sent.id] = None
        _trim_ordered_set(self._posted_message_ids, POSTED_ID_CAP)

    async def _build_round_history(
        self,
        *,
        channel,
        trigger: "discord.Message",
        bot_user_id: int,
    ) -> list[dict[str, str]]:
        """History for one persona inside a team round.

        Combines: pre-trigger context (last ~8 messages strictly older than
        the trigger) + any messages posted between the trigger and now
        (which are this round's earlier agent replies). The trigger itself
        is NOT included — the orchestrator passes it as the new user turn.
        """
        pre: list[tuple[str, str]] = []
        try:
            async for msg in channel.history(
                limit=conversation.DEFAULT_LIMIT, before=trigger
            ):
                content = conversation.strip_mentions(msg.content)
                if not content:
                    continue
                if msg.author.id == bot_user_id:
                    pre.append(("assistant", content))
                elif msg.author.bot:
                    name = conversation.short_bot_name(
                        msg.author.display_name or msg.author.name
                    )
                    pre.append(("user", f"[{name}] {content}"))
                else:
                    pre.append(("user", content))
        except Exception:  # noqa: BLE001
            logger.exception("history fetch (pre) failed")
        pre.reverse()  # oldest first

        between: list[tuple[str, str]] = []
        try:
            async for msg in channel.history(
                limit=20, after=trigger, oldest_first=True
            ):
                if msg.id == trigger.id:
                    continue
                content = conversation.strip_mentions(msg.content)
                if not content:
                    continue
                if msg.author.id == bot_user_id:
                    between.append(("assistant", content))
                elif msg.author.bot:
                    name = conversation.short_bot_name(
                        msg.author.display_name or msg.author.name
                    )
                    between.append(("user", f"[{name}] {content}"))
                # Real-user messages between trigger and now are unusual mid-round;
                # skip them so we don't misorder the conversation.
        except Exception:  # noqa: BLE001
            logger.exception("history fetch (between) failed")

        combined = pre + between
        coalesced: list[list[str]] = []
        for role, content in combined:
            if coalesced and coalesced[-1][0] == role:
                coalesced[-1][1] = coalesced[-1][1] + "\n\n" + content
            else:
                coalesced.append([role, content])
        while coalesced and coalesced[0][0] == "assistant":
            coalesced.pop(0)
        return [{"role": r, "content": c} for r, c in coalesced]
