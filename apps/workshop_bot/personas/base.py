"""PersonaBot — shared base for the four discord.py clients.

Each persona is a subclass that sets a few class attributes (name, tools,
preferred model, home channel env var) and inherits the routing,
peer-reaction protocol, and team-round handling defined here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Optional

import discord

from ..tools import agent_loop, anthropic_client, conversation, db, discord_io

if TYPE_CHECKING:
    from ..tools.agent_tools import ToolRegistry
    from ..tools.corpus import CorpusHandle
    from .team import TeamRegistry

logger = logging.getLogger("workshop.persona")

MODEL_FLAGS: dict[str, str] = {
    "--haiku": "haiku",
    "--sonnet": "sonnet",
    "--opus": "opus",
}
MODEL_FLAG_RE = re.compile(r"\B(--haiku|--sonnet|--opus)\b")

ROUND_HISTORY_DEPTH = 20  # how far back to scan for a human round anchor

# Strip common markdown / punctuation / quoting; if what's left is just the
# word PASS, treat it as a no-reply signal regardless of how the model wrapped it.
_PASS_STRIP_RE = re.compile(r"[\s*_`~\"'()<>\[\]\.\!\?,;:\\\-—–]+")


def is_pass_response(text: str) -> bool:
    if not text:
        return False
    cleaned = _PASS_STRIP_RE.sub("", text)
    return cleaned.upper() == "PASS"


@dataclass
class Deps:
    """Shared resources injected into every persona."""

    corpus: "CorpusHandle"
    registry: "ToolRegistry"
    team: Optional["TeamRegistry"] = None


def _read_env_int(key: str) -> Optional[int]:
    raw = (os.environ.get(key) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def team_role_id() -> Optional[str]:
    """Read once; env doesn't change at runtime."""
    raw = (os.environ.get("DISCORD_TEAM_ROLE_ID") or "").strip()
    return raw or None


def dialog_channel_ids() -> set[int]:
    """Channel IDs where inter-agent reactions are allowed.

    Only #workshop. #chatter is a status firehose — agents post there but
    never react to each other (avoids turning the log stream into chatter).
    """
    cid = _read_env_int("DISCORD_CHANNEL_WORKSHOP")
    return {cid} if cid is not None else set()


class PersonaBot(discord.Client):
    """Base class for the four persona bots.

    Subclasses set:
      - ``persona`` / ``name``         — identity
      - ``home_channel_env``           — env var holding the channel id where
                                         this persona answers without an
                                         @-mention
      - ``empty_greeting``             — reply when @-mentioned with no body
      - ``preferred_model`` (optional) — overrides the WORKSHOP_DEFAULT_MODEL
                                         env default for this persona

    Tool surface comes from ``deps.registry`` (the ``ToolRegistry``
    composed at boot in ``bot.py``). Every persona sees every tool;
    lane discipline lives in the persona prompt.

    ``on_message`` dispatches when:
      - this specific bot is @-mentioned (single-persona reply), or
      - the @Team role is mentioned (TeamRegistry runs all four sequentially,
        one bot orchestrating), or
      - a human posts in this persona's home channel and no other bot is
        mentioned.
    """

    persona: ClassVar[str] = "base"
    name: ClassVar[str] = "Persona"
    home_channel_env: ClassVar[Optional[str]] = None
    empty_greeting: ClassVar[str] = "Hey — what are we looking at?"
    preferred_model: ClassVar[Optional[str]] = None

    # Class-level lock so peer-reaction slot checks across the four persona
    # clients (all in this same asyncio event loop) serialize. Protects
    # against the TOCTOU race when two peers are evaluating the same human
    # anchor concurrently.
    _peer_react_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self, deps: Deps) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(intents=intents)
        self.deps = deps
        self.ready_event = asyncio.Event()
        self._home_channel_id: Optional[int] = (
            _read_env_int(self.home_channel_env) if self.home_channel_env else None
        )

    async def on_ready(self) -> None:  # type: ignore[override]
        user = self.user
        logger.info("%s online as %s (id=%s)", self.name, user, getattr(user, "id", "?"))
        self.ready_event.set()

    def _is_home_channel(self, channel_id: int) -> bool:
        return self._home_channel_id is not None and self._home_channel_id == channel_id

    def _resolve_model(self, override: Optional[str]) -> str:
        return override or self.preferred_model or anthropic_client.default_model()

    async def core(
        self,
        *,
        latest: str,
        history: Optional[list[dict[str, str]]] = None,
        model: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        """Single source of truth for a persona turn.

        Pulls the full tool surface from ``deps.registry``; every persona
        sees every tool. Lane discipline is enforced by the persona prompt.
        """
        issue_index = anthropic_client.format_issue_index(
            self.deps.corpus.corpus["issues"]
        )
        return await agent_loop.run_async(
            persona=self.persona,
            user_message=latest or "(no new content; continue from history)",
            history=history or [],
            tools=self.deps.registry.all_names(),
            deps=self.deps,
            model=self._resolve_model(model),
            issue_index=issue_index,
        )

    async def on_message(self, message: discord.Message) -> None:  # type: ignore[override]
        # Always ignore self.
        if message.author == self.user:
            return
        if message.guild is None:
            return
        if self.user is None:
            return

        # Inter-agent reactions in #workshop only. (#chatter is a status
        # firehose — agents post there but never react to each other.) One
        # reaction per "round" (anchored on the last human message in this
        # channel). LLM decides whether to PASS.
        if message.author.bot:
            if message.channel.id not in dialog_channel_ids():
                return
            # Don't peer-react to messages the team orchestrator posted —
            # the team is already running each persona in sequence.
            if self.deps.team is not None and self.deps.team.is_team_post(message.id):
                return
            async with PersonaBot._peer_react_lock:
                if not await self._can_react_to_peer(message.channel):
                    return
                await self._react_to_peer(message)
            return

        is_self_mention = self.user in message.mentions
        role_id = team_role_id()
        is_team_mention = bool(
            role_id
            and any(str(r.id) == role_id for r in (message.role_mentions or []))
        )
        # "Stopping by my desk" — Jamie posts in this persona's home channel
        # without an @-mention. Yield to any specific persona he @-mentioned.
        is_home = self._is_home_channel(message.channel.id)
        other_bot_mentioned = any(
            m.bot and m != self.user for m in (message.mentions or [])
        )
        home_dispatch = is_home and not other_bot_mentioned

        if not (is_self_mention or is_team_mention or home_dispatch):
            return

        body, model = self._parse_body(message)
        try:
            attachment_text = await discord_io.read_text_attachments(message)
        except Exception:  # noqa: BLE001 — Discord's attachment errors are unlabeled
            logger.exception("%s: attachment read failed", self.name)
            attachment_text = ""

        # Team mention: only one bot orchestrates the round; the rest bow out.
        if is_team_mention and self.deps.team is not None:
            if not await self.deps.team.claim(message.id):
                return
            logger.info("%s claimed team round for message %s", self.name, message.id)
            try:
                await self.deps.team.orchestrate(
                    message=message, body=body, attachment=attachment_text, model=model,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("%s: team orchestration raised", self.name)
                try:
                    await message.reply(
                        f"Sorry — team round hit an error: `{type(exc).__name__}: {exc}`"[:1900],
                        mention_author=False,
                    )
                except discord.DiscordException:
                    logger.error("could not reply with error: %s", traceback.format_exc())
            return

        # Single-persona path.
        history: list[dict[str, str]] = await conversation.build_history(
            message.channel,
            before=message,
            bot_user_id=self.user.id,
        )

        try:
            await self.handle(
                message=message,
                body=body,
                attachment=attachment_text,
                model=model,
                history=history,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s: handler raised", self.name)
            err = f"Sorry — something went wrong: `{type(exc).__name__}: {exc}`"
            try:
                await message.reply(err[:1900], mention_author=False)
            except discord.DiscordException:
                logger.error("could not reply with error: %s", traceback.format_exc())

    async def handle(
        self,
        *,
        message: discord.Message,
        body: str,
        attachment: str,
        model: str,
        history: list[dict[str, str]],
    ) -> None:
        """Default handler: run the agent loop, log the run, send chunked reply.

        Subclasses can override for specialized behavior; most don't need to.
        """
        latest = (attachment or body).strip()
        if not latest and not history:
            await message.reply(self.empty_greeting, mention_author=False)
            return

        async with message.channel.typing():
            with db.AgentRun(self.persona, trigger="mention") as run:
                answer, meta = await self.core(
                    latest=latest, history=history, model=model
                )
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
                    "%s reply #%d (%d iter, %d tool calls)",
                    self.persona,
                    output_id,
                    meta.get("iterations", 0),
                    len(meta.get("tool_calls") or []),
                )

        await discord_io.send_chunked(message, answer)

    def _parse_body(self, message: discord.Message) -> tuple[str, Optional[str]]:
        """Strip mentions + model flags, return (body, model_override).

        ``model_override`` is None unless Jamie included a ``--haiku`` /
        ``--sonnet`` / ``--opus`` flag.
        """
        text = message.content or ""
        # Strip our own user mention.
        text = text.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "")
        # Strip the team role mention if present.
        role_id = team_role_id()
        if role_id:
            text = text.replace(f"<@&{role_id}>", "")

        # --haiku / --sonnet / --opus flags override the persona/env default.
        model: Optional[str] = None
        match = MODEL_FLAG_RE.search(text)
        if match:
            model = MODEL_FLAGS[match.group(1)]
            text = MODEL_FLAG_RE.sub("", text)

        return text.strip(), model

    # ---- Inter-agent reactions ----

    async def _can_react_to_peer(self, channel) -> bool:
        """Slot rule: there must be a human round anchor in recent history,
        and this bot must not have already posted since that anchor.
        """
        try:
            self_count = 0
            async for msg in channel.history(limit=ROUND_HISTORY_DEPTH):
                if not msg.author.bot:
                    return self_count == 0  # found human anchor; have I spoken?
                if msg.author.id == self.user.id:
                    self_count += 1
        except Exception:  # noqa: BLE001
            logger.exception("%s: round-anchor scan failed", self.name)
        return False  # no human anchor → don't react

    async def _react_to_peer(self, message: discord.Message) -> None:
        # Build the same kind of history we'd build for a normal turn.
        history = await conversation.build_history(
            message.channel,
            before=message,
            bot_user_id=self.user.id,
        )

        peer_name = (
            getattr(message.author, "display_name", "") or message.author.name or "a colleague"
        )
        peer_name = conversation.short_bot_name(peer_name)

        peer_text = (message.content or "").strip()
        if not peer_text:
            return

        meta = (
            f"[META: This is {peer_name}'s message in #{getattr(message.channel, 'name', '?')} "
            "— you were NOT addressed. Default is PASS. Silence is the right answer for "
            "most overheard exchanges. Only break in if Jamie specifically needs YOUR "
            "lens here (editorial, promotion, supporter, or link-curation — whichever "
            "you are). Do NOT react just to be social, supportive, or to add color. Do "
            "NOT validate or echo what they said. If you do react, your reply must be "
            "1-3 short sentences, no preamble, no \"good point\", no headings. If in "
            "any doubt, respond with exactly: PASS]"
        )
        body = f"{meta}\n\n[{peer_name}] {peer_text}"

        # Reuse the persona's core() — same agent loop, same tools.
        try:
            answer, run_meta = await self.handle_peer(
                body=body, history=history, model=None,
            )
        except Exception:  # noqa: BLE001
            logger.exception("%s: peer reaction core failed", self.name)
            return

        if not answer or is_pass_response(answer):
            logger.info("%s PASS on peer message from %s", self.name, peer_name)
            return

        logger.info(
            "%s reacting to %s (%d iter, %d tool calls)",
            self.name, peer_name,
            (run_meta or {}).get("iterations", 0),
            len((run_meta or {}).get("tool_calls") or []),
        )
        try:
            for chunk in discord_io.split_for_discord(answer):
                await message.channel.send(chunk)
        except discord.DiscordException:
            logger.exception("%s: failed to send peer reaction", self.name)

    async def handle_peer(
        self,
        *,
        body: str,
        history: list[dict[str, str]],
        model: Optional[str] = None,
    ) -> tuple[str, dict]:
        """Persona-level peer reaction. Default: dispatch through core()."""
        return await self.core(latest=body, history=history, model=model)
