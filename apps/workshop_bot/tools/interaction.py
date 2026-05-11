"""Reaction-based interaction primitive for jobs that need Jamie's call.

Several jobs (``create-final``, the compose-* jobs) post options and wait
for Jamie to react. This wraps that pattern:

- :func:`await_choice` — post ``prompt`` + numbered options, add 1️⃣…N️⃣
  (plus 🔄 to ask for fresh options), wait for Jamie's reaction, return
  the chosen index (0-based), ``"refresh"``, or ``None`` on timeout.
- :func:`await_approval` — post ``prompt``, add ✅/❌ (plus 🔄), wait,
  return ``True`` / ``False`` / ``"refresh"`` / ``None``.

The job typically holds its asset lock for the duration of the
interaction — which is what we want; a concurrent re-fire bounces.

Only Jamie reacts: the wait filters on ``DISCORD_OWNER_USER_ID``. If that
env var isn't set, the helper logs and returns ``None`` immediately (no
operator to ask).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Union

from . import discord_io

logger = logging.getLogger("workshop.interaction")

# Keycap-digit emoji for option N (1-based index -> emoji).
DIGIT_EMOJI = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")
REFRESH_EMOJI = "\U0001f504"   # 🔄
YES_EMOJI = "✅"           # ✅
NO_EMOJI = "❌"            # ❌

DEFAULT_TIMEOUT = 6 * 60 * 60.0  # 6h — generous; Jamie may step away

ChoiceResult = Union[int, str, None]      # int index, "refresh", or None (timeout)
ApprovalResult = Union[bool, str, None]   # True/False, "refresh", or None (timeout)


def _owner_id() -> Optional[str]:
    raw = (os.environ.get("DISCORD_OWNER_USER_ID") or "").strip()
    return raw or None


async def _post(channel, text: str):
    """Send (chunked) and return the *last* message — that's the one we
    attach reactions to and watch."""
    msg = None
    for chunk in discord_io.split_for_discord(text):
        msg = await channel.send(chunk, suppress_embeds=True)
    return msg


async def _wait_for_reaction(bot, message, allowed: set[str], timeout: float) -> Optional[str]:
    owner = _owner_id()
    if owner is None:
        logger.warning("interaction: DISCORD_OWNER_USER_ID not set; can't wait for a reaction")
        return None

    def _check(payload) -> bool:
        if getattr(payload, "message_id", None) != getattr(message, "id", object()):
            return False
        if str(getattr(payload, "user_id", "")) != owner:
            return False
        name = getattr(getattr(payload, "emoji", None), "name", None) or str(getattr(payload, "emoji", ""))
        return name in allowed

    try:
        payload = await bot.wait_for("raw_reaction_add", check=_check, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    name = getattr(getattr(payload, "emoji", None), "name", None) or str(getattr(payload, "emoji", ""))
    return name


async def await_choice(
    bot,
    channel,
    options: list[str],
    *,
    prompt: str,
    timeout: float = DEFAULT_TIMEOUT,
    allow_refresh: bool = True,
) -> ChoiceResult:
    """Post ``prompt`` + a numbered list of ``options``, add reactions, and
    wait for Jamie to react. Returns the 0-based index of the pick, the
    string ``"refresh"`` if he asked for more, or ``None`` on timeout."""
    n = min(len(options), len(DIGIT_EMOJI))
    if n == 0:
        return None
    lines = [prompt, ""]
    for i in range(n):
        lines.append(f"**{i + 1}.** {options[i]}")
    if allow_refresh:
        lines.append("")
        lines.append("React 1️⃣–{}️⃣ to pick, or 🔄 for fresh options.".format(n))
    msg = await _post(channel, "\n".join(lines))
    if msg is None:
        return None
    emojis = list(DIGIT_EMOJI[:n])
    if allow_refresh:
        emojis.append(REFRESH_EMOJI)
    for e in emojis:
        try:
            await msg.add_reaction(e)
        except Exception:  # noqa: BLE001
            logger.exception("interaction: add_reaction %s failed", e)
    picked = await _wait_for_reaction(bot, msg, set(emojis), timeout)
    if picked is None:
        return None
    if picked == REFRESH_EMOJI:
        return "refresh"
    try:
        return DIGIT_EMOJI.index(picked)
    except ValueError:
        return None


async def await_approval(
    bot,
    channel,
    *,
    prompt: str,
    timeout: float = DEFAULT_TIMEOUT,
    allow_refresh: bool = True,
) -> ApprovalResult:
    """Post ``prompt``, add ✅/❌ (and 🔄), wait. Returns ``True`` (✅),
    ``False`` (❌), ``"refresh"`` (🔄), or ``None`` on timeout."""
    suffix = "React ✅ to accept, ❌ to skip" + (", or 🔄 for a fresh take." if allow_refresh else ".")
    msg = await _post(channel, f"{prompt}\n\n{suffix}")
    if msg is None:
        return None
    emojis = [YES_EMOJI, NO_EMOJI] + ([REFRESH_EMOJI] if allow_refresh else [])
    for e in emojis:
        try:
            await msg.add_reaction(e)
        except Exception:  # noqa: BLE001
            logger.exception("interaction: add_reaction %s failed", e)
    picked = await _wait_for_reaction(bot, msg, set(emojis), timeout)
    if picked is None:
        return None
    if picked == YES_EMOJI:
        return True
    if picked == NO_EMOJI:
        return False
    return "refresh"
