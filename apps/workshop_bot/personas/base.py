"""PersonaBot — shared base for Eddy's discord.py client.

Eddy sets a few class attributes (name, preferred model, home channel env
var) and inherits the mention/home-channel routing defined here.
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

from ..tools import db
from ..tools.llm import agent_loop, agent_tools, anthropic_client
from ..tools.discord import conversation, discord_io

if TYPE_CHECKING:
    from ..tools.llm.agent_tools import ToolRegistry
    from ..tools.content.corpus import CorpusHandle
    from .team import TeamRegistry

logger = logging.getLogger("workshop.persona")

MODEL_FLAGS: dict[str, str] = {
    "--haiku": "haiku",
    "--sonnet": "sonnet",
    "--opus": "opus",
}
MODEL_FLAG_RE = re.compile(r"\B(--haiku|--sonnet|--opus)\b")

# Strip common markdown / punctuation / quoting; if what's left is just the
# word PASS, treat it as a no-reply signal regardless of how the model wrapped it.
_PASS_STRIP_RE = re.compile(r"[\s*_`~\"'()<>\[\]\.\!\?,;:\\\-—–]+")


def is_pass_response(text: str) -> bool:
    r"""True if ``text`` is a no-reply signal.

    Matches three shapes:

      - The whole response reduces to ``PASS`` after stripping
        markdown/punctuation (``**PASS**``, ``\`PASS\```, ``(PASS).``).
      - The last non-empty line reduces to ``PASS`` — covers the
        common drift where a persona writes its reasoning and then
        closes with ``PASS`` on its own line. Treat the trailing
        token as the verdict and discard the prose.

    "I'll PASS on this proposal" stays in-sentence and does not match.
    """
    if not text:
        return False
    cleaned = _PASS_STRIP_RE.sub("", text)
    if cleaned.upper() == "PASS":
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        last = _PASS_STRIP_RE.sub("", lines[-1])
        if last.upper() == "PASS":
            return True
    return False


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


class PersonaBot(discord.Client):
    """Base class for Eddy.

    Subclasses set:
      - ``persona`` / ``name``         — identity
      - ``home_channel_env``           — env var holding the channel id where
                                         this persona answers without an
                                         @-mention
      - ``empty_greeting``             — reply when @-mentioned with no body
      - ``preferred_model`` (optional) — overrides the WORKSHOP_DEFAULT_MODEL
                                         env default for this persona

    Tool surface comes from ``deps.registry`` (the ``ToolRegistry``
    composed at boot in ``bot.py``).

    ``on_message`` dispatches when:
      - this specific bot is @-mentioned (single-persona reply), or
      - a human posts in this persona's home channel and no other bot is
        mentioned.
    """

    persona: ClassVar[str] = "base"
    name: ClassVar[str] = "Persona"
    home_channel_env: ClassVar[Optional[str]] = None
    empty_greeting: ClassVar[str] = "Hey — what are we looking at?"
    preferred_model: ClassVar[Optional[str]] = None
    # One-line summary of this persona's slash commands, posted as the
    # second line of the startup card. Each subclass sets it.
    slash_commands_summary: ClassVar[str] = ""

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
        # Each persona's __init__ may set self.command_tree (the
        # /<persona> slash tree). on_ready below syncs it.
        self.command_tree = None  # type: ignore[assignment]

    def persistent_views(self) -> list:
        """Persistent (`timeout=None`) views to register on this bot at
        startup so their button clicks route by ``custom_id`` even after a
        restart. Default none; personas that own a long-lived control card
        (e.g. Eddy's ship console) override this."""
        return []

    def _register_persistent_views(self) -> None:
        """Register this persona's persistent views exactly once. ``on_ready``
        can fire on every reconnect, so guard against a double add (discord.py
        raises if the same custom_id is registered twice)."""
        if getattr(self, "_views_registered", False):
            return
        for view in self.persistent_views():
            try:
                self.add_view(view)
            except Exception:  # noqa: BLE001
                logger.exception("%s: failed to register persistent view %r", self.persona, view)
        self._views_registered = True

    async def on_ready(self) -> None:  # type: ignore[override]
        user = self.user
        logger.info("%s online as %s (id=%s)", self.name, user, getattr(user, "id", "?"))
        self.ready_event.set()
        if self.command_tree is not None:
            await self._sync_command_tree()
        try:
            self._register_persistent_views()
        except Exception:  # noqa: BLE001
            logger.exception("%s: register_persistent_views failed", self.persona)
        try:
            await self._post_startup_card()
        except Exception:  # noqa: BLE001
            logger.exception("%s: post_startup_card failed", self.persona)

    async def _post_startup_card(self) -> None:
        """Audit this persona's channels and post a one-line readiness
        card to #chatter under Eddy's avatar. Eddy prepends a deployment
        header (git hash + dirty flag)."""
        from ..tools.discord import startup

        # Lead persona (Eddy by convention) carries the deployment header.
        is_lead = self.persona == startup.ANNOUNCER
        header: Optional[str] = None
        if is_lead:
            mark = startup.git_hash()
            dirty = " (dirty)" if startup.git_dirty() else ""
            header = f"**workshop-bot online** — `{mark}`{dirty}"

        rows = startup.audit_one(self)
        # Slim startup card: just `✓ {Name} online` (lead persona also
        # carries the deployment header). The audit's per-channel rows
        # only render when there's an issue. The slash-verb list is no
        # longer surfaced per boot — operator noise.
        message = startup.format_persona_line(self, rows, header=header)
        await startup.announce(self, message)

    async def _sync_command_tree(self) -> None:
        """Sync the persona's slash tree to the configured guild (or globally
        if no DISCORD_SERVER_ID is set). Guild-scoped sync is instant;
        global sync takes ~1h to propagate to Discord clients."""
        guild_id = (os.environ.get("DISCORD_SERVER_ID") or "").strip()
        try:
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.command_tree.copy_global_to(guild=guild)
                synced = await self.command_tree.sync(guild=guild)
            else:
                synced = await self.command_tree.sync()
            logger.info(
                "%s: command tree synced (%d command(s)%s)",
                self.persona, len(synced),
                f", guild={guild_id}" if guild_id else "",
            )
        except Exception:  # noqa: BLE001
            logger.exception("%s: command tree sync failed", self.persona)

    def _is_home_channel(self, channel_id: int) -> bool:
        return self._home_channel_id is not None and self._home_channel_id == channel_id

    def _resolve_model(self, override: Optional[str]) -> str:
        return override or self.preferred_model or anthropic_client.default_model()

    async def core(
        self,
        *,
        latest: "str | list[dict[str, Any]]",
        history: Optional[list[dict[str, str]]] = None,
        model: Optional[str] = None,
        first_turn_tool_choice: Optional[dict[str, Any]] = None,
    ) -> tuple[str, dict[str, Any]]:
        """Single source of truth for a persona turn.

        ``first_turn_tool_choice`` (e.g. ``{"type": "any"}``) forces a tool
        call on the opening turn for work-not-chat jobs that otherwise
        narrate a plan and never act.

        ``latest`` is the user-message payload — typically a plain string,
        but callers can pass a list of Anthropic content blocks when they
        want to mark a stable leading block with ``cache_control`` (e.g.
        ``_draft_review`` parks its multi-KB review prompt in its own
        cached block).

        Pulls Eddy's allowed tool surface from ``deps.registry``.

        Note: an earlier version of this method also rendered the full
            348-issue archive into a system text block (``issue_index``) so
            the model had a built-in "what issues exist?" cheat sheet. That
            block was ~47.5k tokens on every call. Retired in favour of
            ``archive__search`` (BM25), with ``archive__get_issue`` /
            ``archive__quote_search`` for deeper retrieval.
        """
        if isinstance(latest, str):
            payload: "str | list[dict[str, Any]]" = (
                latest or "(no new content; continue from history)"
            )
        else:
            payload = latest
        return await agent_loop.run_async(
            persona=self.persona,
            user_message=payload,
            history=history or [],
            tools=self.deps.registry.names_for(self.persona),
            deps=self.deps,
            model=self._resolve_model(model),
            first_turn_tool_choice=first_turn_tool_choice,
        )

    async def on_message(self, message: discord.Message) -> None:  # type: ignore[override]
        # Always ignore self.
        if message.author == self.user:
            return
        if message.guild is None:
            return
        if self.user is None:
            return

        if message.author.bot:
            return

        is_self_mention = self.user in message.mentions
        # "Stopping by my desk" — Jamie posts in this persona's home channel
        # without an @-mention. Yield to any specific persona he @-mentioned.
        is_home = self._is_home_channel(message.channel.id)
        other_bot_mentioned = any(
            m.bot and m != self.user for m in (message.mentions or [])
        )
        home_dispatch = is_home and not other_bot_mentioned

        if not (is_self_mention or home_dispatch):
            return

        body, model = self._parse_body(message)
        try:
            attachment_text = await discord_io.read_text_attachments(message)
        except Exception:  # noqa: BLE001 — Discord's attachment errors are unlabeled
            logger.exception("%s: attachment read failed", self.name)
            attachment_text = ""

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
                await message.reply(err[:1900], mention_author=False, suppress_embeds=True)
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
            await message.reply(self.empty_greeting, mention_author=False, suppress_embeds=True)
            return

        token = agent_tools.active_react_target.set(
            (message.channel.id, message.id)
        )
        try:
            async with message.channel.typing():
                with db.AgentRun(self.persona, trigger="mention") as run:
                    answer, meta = await self.core(
                        latest=latest, history=history, model=model
                    )
                    run.record_meta(meta)
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
        finally:
            agent_tools.active_react_target.reset(token)

        await discord_io.send_chunked(message, answer)

    def _parse_body(self, message: discord.Message) -> tuple[str, Optional[str]]:
        """Strip mentions + model flags, return (body, model_override).

        ``model_override`` is None unless Jamie included a ``--haiku`` /
        ``--sonnet`` / ``--opus`` flag.
        """
        text = message.content or ""
        # Strip our own user mention.
        text = text.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "")
        # --haiku / --sonnet / --opus flags override the persona/env default.
        model: Optional[str] = None
        match = MODEL_FLAG_RE.search(text)
        if match:
            model = MODEL_FLAGS[match.group(1)]
            text = MODEL_FLAG_RE.sub("", text)

        return text.strip(), model
