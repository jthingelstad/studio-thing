"""Shared helpers for the slash-command surface.

Every persona's slash tree (``/eddy``, ``/linky``, ``/marky``, ``/patty``)
uses the same three building blocks:

- :func:`_ctx(bot)` — produces a :class:`JobContext` bound to that bot's
  ``deps`` so the command's handler can invoke jobs.
- :func:`make_ack(logger_label)` — returns an ``_ack`` coroutine that
  sends an ephemeral followup, swallowing the expired-interaction-token
  error so a slow job hiccup doesn't surface as a command error.
- :func:`make_run_and_ack(_ack, logger_label)` — the fast-job dispatch:
  defer → run → ack with the JobResult message.
- :func:`make_run_interactive(...)` — the interactive-job dispatch (haiku
  picker, subject picker, CTA picker): ack immediately, then run the job
  (which posts its own outcome to a channel because it can wait on a
  reaction far longer than the 15-min interaction token).

The ``logger_label`` argument is just the ``/eddy`` / ``/linky`` / etc.
prefix; it shows up in workshop.log when something goes wrong.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ...jobs import _base as jobs_base

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401

logger = logging.getLogger("workshop.commands")

# Discord ephemeral followup cap is 2000 chars; leave headroom.
MSG_CAP = 1900


def _ctx(bot) -> "jobs_base.JobContext":
    """Build a :class:`JobContext` for a slash invocation off the host bot's deps."""
    return jobs_base.JobContext(deps=getattr(bot, "deps", None), trigger="manual")


def _clip(text: str) -> str:
    return text if len(text) <= MSG_CAP else text[: MSG_CAP - 1] + "…"


def make_ack(logger_label: str):
    """Build the ``_ack`` coroutine for one persona's slash tree."""

    async def _ack(interaction, text: str, *, file: discord.File | None = None) -> None:
        try:
            if file is not None:
                await interaction.followup.send(_clip(text), ephemeral=True, file=file)
            else:
                await interaction.followup.send(_clip(text), ephemeral=True)
        except discord.HTTPException:  # token gone (>15 min) or transient — the work still happened
            logger.warning("%s: couldn't ack invoker (interaction expired?)", logger_label)

    return _ack


def make_run_and_ack(ack_fn, logger_label: str):
    """Build the fast-job dispatch (``_run_and_ack``) for one persona's tree."""

    async def _run_and_ack(interaction, coro_factory, label: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await coro_factory()
        except jobs_base.JobLocked as exc:
            logger.info("%s %s: blocked — %s", logger_label, label, exc.holder_desc)
            await ack_fn(interaction, f"⏳ `{label}` is already running ({exc.holder_desc}) — try again shortly.")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s %s failed", logger_label, label)
            await ack_fn(interaction, f"❌ `{label}` hit an error: `{type(exc).__name__}: {exc}`")
            return
        await ack_fn(interaction, result.message)

    return _run_and_ack


def make_run_interactive(logger_label: str):
    """Build the interactive-job dispatch for one persona's tree.

    Interactive jobs (the compose-* pickers and reorder) post options
    to a channel and wait for Jamie's reaction — possibly far longer than
    the 15-min Discord interaction token. So the command acks
    *immediately* ("started — react in #editorial / …") and then runs the
    job, which posts its own outcome to the channel. The token's already
    used; we don't send a followup.
    """

    async def _run_interactive(interaction, coro_factory, label: str, started: str) -> None:
        await interaction.response.send_message(started, ephemeral=True)
        try:
            await coro_factory()
        except jobs_base.JobLocked as exc:
            logger.info("%s %s: blocked — %s", logger_label, label, exc.holder_desc)
            try:
                await interaction.followup.send(
                    f"⏳ `{label}` is already running ({exc.holder_desc}) — try again shortly.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass
            return
        except Exception:  # noqa: BLE001
            logger.exception("%s %s failed", logger_label, label)
            return

    return _run_interactive
