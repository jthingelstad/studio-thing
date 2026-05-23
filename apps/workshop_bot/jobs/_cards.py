"""Shared machinery for the per-phase publishing cards.

Each phase of the publishing spine (Build → Publish → Share — see
`docs/publishing-process.md`) has **one persistent card**: a Discord message
the bot edits in place and re-finds across restarts via the `issue_cards`
table. This module holds what all three cards share — the post-or-edit + pin
lifecycle and a few small render primitives — so `build_card.py`,
`publish_card.py`, and `share_card.py` only differ in *what state they gather
and how they render it*.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import discord

from ..tools import db, s3
from . import _base  # noqa: F401 — re-exported type hint convenience

logger = logging.getLogger("workshop.jobs.cards")

EDITORIAL_ENV = "DISCORD_CHANNEL_EDITORIAL"
PROMOTION_ENV = "DISCORD_CHANNEL_PROMOTION"


# ---------- small render primitives ----------

def mark(flag: bool) -> str:
    return "✅" if flag else "☐"


def section_tag(s: dict) -> tuple[str, str]:
    """(icon, label) for one section's readiness, from `section_status`."""
    if s.get("placeholder"):
        return "⚠️", "placeholder"
    if s.get("present"):
        c = s.get("item_count", 0)
        return "✅", f"{c} item{'' if c == 1 else 's'}"
    return "☐", "empty"


def read_metadata_raw(n: int) -> dict:
    """Read metadata.json verbatim (no placeholder injection) so callers can
    tell *authored* fields from *absent* ones. Empty dict on any miss."""
    try:
        res = s3.read_issue_file(n, "metadata.json")
    except Exception:  # noqa: BLE001
        return {}
    if not (res.get("found") and isinstance(res.get("text"), str)):
        return {}
    try:
        data = json.loads(res["text"])
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def issue_files(n: int) -> set:
    """The set of filenames present in the issue's S3 workspace (atoms/
    collapsed to bare names by `s3.list_issue`). Empty set on failure."""
    try:
        listing = s3.list_issue(n)
        return {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
    except Exception:  # noqa: BLE001
        return set()


# ---------- card lifecycle (post / edit / pin / unpin) ----------

async def upsert_card(
    ctx,
    *,
    kind: str,
    channel_env: str,
    persona: str,
    n: int,
    embed: "discord.Embed",
    view,
    pin: bool = True,
) -> Optional[int]:
    """Edit the issue's recorded `kind` card in place, or post + pin a fresh
    one and record it. Returns the message id, or None if the channel couldn't
    be resolved. Best-effort — a Discord hiccup logs and returns."""
    channel = ctx.channel(channel_env, persona=persona)
    if channel is None:
        logger.warning("cards: %s channel unavailable; %s card not posted", channel_env, kind)
        return None

    recorded = db.get_issue_card(n, kind)
    if recorded:
        try:
            msg = await channel.fetch_message(recorded["message_id"])
            await msg.edit(embed=embed, view=view)
            return recorded["message_id"]
        except discord.NotFound:
            logger.info("cards: recorded %s card %s gone; reposting", kind, recorded["message_id"])
        except Exception:  # noqa: BLE001
            logger.exception("cards: %s card edit failed; reposting", kind)

    try:
        msg = await channel.send(embed=embed, view=view)
    except Exception:  # noqa: BLE001
        logger.exception("cards: %s card post failed for #%d", kind, n)
        return None
    if pin:
        try:
            await msg.pin()
        except Exception:  # noqa: BLE001
            logger.warning("cards: couldn't pin %s card for #%d (Manage Messages?)", kind, n)
    try:
        db.set_issue_card(n, kind, message_id=int(msg.id), channel_id=int(channel.id))
    except Exception:  # noqa: BLE001
        logger.exception("cards: failed to record %s card id for #%d", kind, n)
    return int(getattr(msg, "id", 0)) or None


async def finalize_card(
    ctx,
    *,
    kind: str,
    channel_env: str,
    persona: str,
    n: int,
    embed: "discord.Embed",
) -> None:
    """Edit a card to a final (static) embed and unpin it — used when a phase
    ends (e.g. `mark built` finalizes the Build card). Leaves the record so the
    message stays editable; `clear_card` forgets it entirely. Best-effort."""
    card = db.get_issue_card(n, kind)
    if not card:
        return
    channel = ctx.channel(channel_env, persona=persona)
    if channel is None:
        return
    try:
        msg = await channel.fetch_message(card["message_id"])
        await msg.edit(embed=embed, view=None)
        await msg.unpin()
    except Exception:  # noqa: BLE001
        logger.warning("cards: couldn't finalize %s card for #%d", kind, n)


async def clear_card(ctx, *, kind: str, channel_env: str, persona: str, n: int) -> None:
    """Unpin + forget an issue's `kind` card (used at put-to-bed). Best-effort."""
    card = db.get_issue_card(n, kind)
    if card:
        channel = ctx.channel(channel_env, persona=persona)
        if channel is not None:
            try:
                msg = await channel.fetch_message(card["message_id"])
                await msg.unpin()
            except Exception:  # noqa: BLE001
                logger.warning("cards: couldn't unpin %s card for #%d", kind, n)
    db.clear_issue_cards(n, kind)
