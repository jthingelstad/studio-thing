"""Shared helpers for the compose-* jobs and create-final.

These jobs all: (1) read the issue's final.md (or draft.md as a fallback
before create-final has run), (2) run a persona's agent loop with a job
prompt, (3) parse a JSON payload out of the reply, (4) post options /
proposals to a channel and wait for Jamie's reaction, (5) write the
accepted artifact to the workspace.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ..tools import s3
from . import _base

logger = logging.getLogger("workshop.jobs.compose")

# Cap how much of the issue body we feed the model.
ISSUE_BODY_CAP = 20_000


def final_or_draft(issue_number: int) -> str:
    """``final.md`` if it exists, else ``draft.md`` (so the compose jobs
    can be run manually before create-final). Empty string if neither."""
    for name in ("final.md", "draft.md"):
        res = s3.read_issue_file(issue_number, name)
        if res.get("found") and isinstance(res.get("text"), str) and res["text"].strip():
            return res["text"]
    return ""


def parse_json_payload(reply: str) -> Optional[dict[str, Any]]:
    """Extract and parse the first JSON object in ``reply`` (the model is
    asked to return only JSON; tolerate code fences / surrounding prose)."""
    if not reply:
        return None
    m = re.search(r"\{.*\}", reply, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_bot_and_channel(ctx: "_base.JobContext", persona: str, channel_env: str):
    """Return ``(bot, channel, None)`` for ``persona`` (its discord.Client
    and the env-named channel bound to it), or ``(None, None, reason)`` if
    either is unavailable. ``bot`` has ``wait_for`` (it's a discord.Client
    subclass); ``channel`` has ``send`` and yields messages with
    ``add_reaction``."""
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return None, None, "no Discord (team registry unavailable)"
    bot = team.bots.get(persona)
    if bot is None or getattr(bot, "user", None) is None:
        return None, None, f"{persona} unavailable"
    channel = ctx.channel(channel_env, persona=persona)
    if channel is None:
        return None, None, f"can't resolve {channel_env}"
    return bot, channel, None
