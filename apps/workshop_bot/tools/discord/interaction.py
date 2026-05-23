"""Button-based interaction primitive for jobs that need Jamie's call.

Several jobs (``create-final``, the compose-* jobs) post options and wait for
Jamie to choose. This wraps that pattern with **Discord buttons** (reactions
were the original mechanism — buttons are the clearer UX):

- :func:`await_choice` — post ``prompt`` + numbered options as buttons (plus a
  Refresh button), wait for Jamie's click, return the chosen index (0-based),
  ``"refresh"``, or ``None`` on timeout.
- :func:`await_approval` — post ``prompt`` with Accept / Skip (plus Refresh),
  wait, return ``True`` / ``False`` / ``"refresh"`` / ``None``.

Signatures + return contracts are unchanged from the reaction era, so callers
(and their tests) are untouched. The job typically holds its asset lock for the
duration — a concurrent re-fire bounces. Only Jamie's clicks count: callbacks
filter on ``DISCORD_OWNER_USER_ID``. If that env var isn't set, the helper logs
and returns ``None`` immediately (no operator to ask). The ``bot`` argument is
retained for signature compatibility but is no longer used.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Union

import discord

from . import discord_io

logger = logging.getLogger("workshop.interaction")

# Kept for any external reference / readability; the buttons render numbers.
DIGIT_EMOJI = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")
REFRESH_EMOJI = "\U0001f504"   # 🔄
YES_EMOJI = "✅"
NO_EMOJI = "❌"
_MAX_OPTIONS = 5

DEFAULT_TIMEOUT = 6 * 60 * 60.0  # 6h — generous; Jamie may step away

ChoiceResult = Union[int, str, None]      # int index, "refresh", or None (timeout)
ApprovalResult = Union[bool, str, None]   # True/False, "refresh", or None (timeout)


def _owner_id() -> Optional[str]:
    raw = (os.environ.get("DISCORD_OWNER_USER_ID") or "").strip()
    return raw or None


class _PickView(discord.ui.View):
    """A transient picker: owner-filtered buttons whose first click sets a
    result + an asyncio.Event the caller awaits. Not persistent — it lives only
    for the single pick (its asset-locked job holds it open)."""

    def __init__(self, *, owner: str, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self._owner = owner
        self._event = asyncio.Event()
        self.result = None

    def add_choice(self, value, label: str, *, emoji: Optional[str] = None, style=None) -> None:
        btn = discord.ui.Button(
            label=label, emoji=emoji,
            style=style or discord.ButtonStyle.secondary,
            custom_id=f"pick:{value}",
        )
        btn.callback = self._make_cb(value)
        self.add_item(btn)

    def _make_cb(self, value):
        async def _cb(interaction) -> None:
            if str(getattr(getattr(interaction, "user", None), "id", "")) != self._owner:
                try:
                    await interaction.response.send_message("This pick is Jamie's.", ephemeral=True)
                except Exception:  # noqa: BLE001
                    pass
                return
            self.result = value
            try:
                await interaction.response.defer()
            except Exception:  # noqa: BLE001
                pass
            self._event.set()
            self.stop()

        return _cb

    async def wait_pick(self, timeout: float):
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except asyncio.TimeoutError:
            return None
        return self.result


async def _post_with_view(channel, text: str, view) -> Optional[object]:
    """Send (chunked); attach the view to the *last* message. Return it."""
    msg = None
    chunks = discord_io.split_for_discord(text)
    for i, chunk in enumerate(chunks):
        last = i == len(chunks) - 1
        try:
            if last:
                msg = await channel.send(chunk, suppress_embeds=True, view=view)
            else:
                msg = await channel.send(chunk, suppress_embeds=True)
        except Exception:  # noqa: BLE001
            logger.exception("interaction: post failed")
            return None
    return msg


async def await_choice(
    bot,
    channel,
    options: list[str],
    *,
    prompt: str,
    timeout: float = DEFAULT_TIMEOUT,
    allow_refresh: bool = True,
) -> ChoiceResult:
    """Post ``prompt`` + a numbered list of ``options`` as buttons, and wait for
    Jamie to click. Returns the 0-based index, ``"refresh"``, or ``None`` on
    timeout."""
    n = min(len(options), _MAX_OPTIONS)
    if n == 0:
        return None
    owner = _owner_id()
    if owner is None:
        logger.warning("interaction: DISCORD_OWNER_USER_ID not set; can't wait for a pick")
        return None

    lines = [prompt, ""]
    for i in range(n):
        lines.append(f"**{i + 1}.** {options[i]}")
    if allow_refresh:
        lines += ["", "Tap a number to pick, or **Refresh** for fresh options."]

    view = _PickView(owner=owner, timeout=timeout)
    for i in range(n):
        view.add_choice(i, str(i + 1), style=discord.ButtonStyle.primary)
    if allow_refresh:
        view.add_choice("refresh", "Refresh", emoji=REFRESH_EMOJI)

    msg = await _post_with_view(channel, "\n".join(lines), view)
    if msg is None:
        return None
    return await view.wait_pick(timeout)


async def await_approval(
    bot,
    channel,
    *,
    prompt: str,
    timeout: float = DEFAULT_TIMEOUT,
    allow_refresh: bool = True,
) -> ApprovalResult:
    """Post ``prompt`` with Accept / Skip (and Refresh) buttons, wait. Returns
    ``True`` (accept), ``False`` (skip), ``"refresh"``, or ``None`` on timeout."""
    owner = _owner_id()
    if owner is None:
        logger.warning("interaction: DISCORD_OWNER_USER_ID not set; can't wait for approval")
        return None

    view = _PickView(owner=owner, timeout=timeout)
    view.add_choice(True, "Accept", emoji=YES_EMOJI, style=discord.ButtonStyle.success)
    view.add_choice(False, "Skip", emoji=NO_EMOJI, style=discord.ButtonStyle.danger)
    if allow_refresh:
        view.add_choice("refresh", "Refresh", emoji=REFRESH_EMOJI)

    msg = await _post_with_view(channel, prompt, view)
    if msg is None:
        return None
    return await view.wait_pick(timeout)
