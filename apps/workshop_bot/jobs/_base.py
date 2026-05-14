"""Job runtime — context, single-asset locking, draft-block helpers.

Every workshop_bot user-facing action is a *job*: deterministic Python in
this package, fired by the ``/workshop …`` slash surface (commands grouped by content artifact) and (for
some) by cron. A job reads from source systems and the per-issue S3
workspace, may make small encapsulated LLM calls, and writes back into the
workspace or workshop.db.

**Concurrency.** Jobs run serialized *per asset*. The lock unit is the file
a job intends to write, not the issue — two jobs that write the same file
can't overlap; jobs that touch different files can. Locks live in the
``job_locks`` SQLite table and are released on completion (success or
failure). A lock held by a dead process is treated as stale and stolen.

**Draft blocks.** ``update-draft`` fills named blocks delimited by
``<!-- block:NAME -->`` … ``<!-- /block:NAME -->`` markers in ``draft.md``.
``replace_block`` swaps the content between a pair wholesale.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from ..tools import db, discord_io

logger = logging.getLogger("workshop.jobs")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# ---------- result ----------

@dataclass
class JobResult:
    """What a job hands back. ``message`` is rendered to the invoker;
    ``data`` carries structured bits a chained/parent job may want."""

    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


# ---------- context ----------

class JobContext:
    """Per-run context handed to a job.

    Carries the shared ``Deps`` (corpus, registry, team) when the job runs
    inside the bot process, plus a ``trigger`` label ('manual',
    'scheduled', 'chained'). Jobs that touch neither Discord nor the agent
    loop can ignore all of it.
    """

    def __init__(self, *, deps: Any = None, trigger: str = "manual") -> None:
        self.deps = deps
        self.trigger = trigger

    @property
    def team(self):
        return getattr(self.deps, "team", None)

    def channel(self, env_var: str, *, persona: Optional[str] = None):
        """Resolve a Discord channel from an env var, optionally bound to a
        persona's client so ``channel.send`` posts under that avatar."""
        team = self.team
        if team is None:
            logger.warning("job: no team registry; cannot resolve %s", env_var)
            return None
        cid_raw = (os.environ.get(env_var) or "").strip()
        if not cid_raw:
            logger.warning("job: %s not set; channel unavailable", env_var)
            return None
        try:
            cid = int(cid_raw)
        except ValueError:
            logger.warning("job: %s=%r is not a channel id", env_var, cid_raw)
            return None
        if persona is not None:
            bot = team.bots.get(persona)
            if bot is None or bot.user is None:
                logger.warning("job: persona %r unavailable for channel %s", persona, env_var)
                return None
            return bot.get_channel(cid)
        for bot in team.bots.values():
            if bot.user is None:
                continue
            ch = bot.get_channel(cid)
            if ch is not None:
                return ch
        logger.warning("job: channel %s not visible to any persona", cid)
        return None

    async def post(
        self,
        channel_or_env,
        text: str,
        *,
        persona: Optional[str] = None,
        suppress_embeds: bool = True,
    ) -> bool:
        """Post ``text`` (chunked) to a channel. ``channel_or_env`` may be a
        channel object or an env-var name to resolve. Returns True if sent."""
        if not text or not text.strip():
            return False
        ch = channel_or_env
        if isinstance(channel_or_env, str):
            ch = self.channel(channel_or_env, persona=persona)
        if ch is None:
            return False
        for chunk in discord_io.split_for_discord(text):
            await ch.send(chunk, suppress_embeds=suppress_embeds)
        return True

    async def send_one(
        self,
        channel_or_env,
        text: str,
        *,
        persona: Optional[str] = None,
        suppress_embeds: bool = True,
    ):
        """Post ``text`` as a single Discord message (no chunk-splitting)
        and return the resulting :class:`discord.Message`, or ``None`` if
        the channel couldn't be resolved or the text was empty. Callers
        that need the message id (e.g. to record a reply target) use this
        instead of :meth:`post`."""
        if not text or not text.strip():
            return None
        ch = channel_or_env
        if isinstance(channel_or_env, str):
            ch = self.channel(channel_or_env, persona=persona)
        if ch is None:
            return None
        # Discord caps a message at 2000 chars; clamp here rather than
        # silently fragment, since recording the wrong message id would
        # break the reply lookup.
        body = text if len(text) <= 1990 else text[:1990].rstrip() + "…"
        return await ch.send(body, suppress_embeds=suppress_embeds)


# ---------- locking ----------

class JobLocked(Exception):
    """Raised when a job can't acquire a lock because another *running* job
    holds it. Catch it and surface a friendly "already running" message."""

    def __init__(self, asset: str, holder: dict[str, Any]) -> None:
        self.asset = asset
        self.holder = holder
        super().__init__(
            f"asset {asset!r} is locked by job "
            f"{holder.get('job', '?')!r} (started {holder.get('started_at', '?')})"
        )

    @property
    def holder_desc(self) -> str:
        return (
            f"`{self.holder.get('job', '?')}`, started "
            f"{self.holder.get('started_at', '?')} UTC"
        )


@contextmanager
def job_lock(assets: list[str], job: str) -> Iterator[None]:
    """Hold ``assets`` for the duration of the block; release on exit.

    Raises :class:`JobLocked` if any asset is held by another live job.
    Locks held by a dead process are stolen. Acquired locks are released
    even if the body raises.
    """
    acquired: list[str] = []
    pid = os.getpid()
    try:
        for asset in assets:
            holder = db.acquire_job_lock(asset=asset, job=job, pid=pid)
            if holder is not None:
                raise JobLocked(asset, holder)
            acquired.append(asset)
        yield
    finally:
        for asset in acquired:
            try:
                db.release_job_lock(asset)
            except Exception:  # noqa: BLE001
                logger.exception("job: failed to release lock on %s", asset)


# ---------- draft blocks ----------

def _open_tag(name: str) -> str:
    return f"<!-- block:{name} -->"


def _close_tag(name: str) -> str:
    return f"<!-- /block:{name} -->"


def get_block(text: str, name: str) -> Optional[str]:
    """Return the (stripped) content between a block's markers, or None if
    the block isn't present."""
    open_tag, close_tag = _open_tag(name), _close_tag(name)
    i = text.find(open_tag)
    if i < 0:
        return None
    j = text.find(close_tag, i + len(open_tag))
    if j < 0:
        return None
    return text[i + len(open_tag):j].strip()


def replace_block(text: str, name: str, content: str) -> str:
    """Replace a block's content wholesale. Returns ``text`` unchanged if
    the block markers aren't present (so a malformed template fails loud
    elsewhere rather than silently dropping content here)."""
    open_tag, close_tag = _open_tag(name), _close_tag(name)
    i = text.find(open_tag)
    if i < 0:
        return text
    j = text.find(close_tag, i + len(open_tag))
    if j < 0:
        return text
    body = (content or "").strip()
    inner = f"\n{body}\n" if body else "\n"
    return text[: i + len(open_tag)] + inner + text[j:]


def starter_template() -> str:
    return (TEMPLATES_DIR / "draft_starter.md").read_text(encoding="utf-8")


# ---------- content-formatting helpers ----------

def format_haiku(text: str) -> str:
    """Render a haiku the way the published issue does:
    ``**line one  \\nline two  \\nline three**`` — bold-wrapped, with a
    markdown hard break (two trailing spaces) between lines. Idempotent:
    peels an existing ``** … **`` wrapper and trailing hard-break spaces
    first, so re-running it doesn't double up. Returns ``""`` for empty
    input."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if len(raw) > 4 and raw.startswith("**") and raw.endswith("**"):
        raw = raw[2:-2].strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return ""
    return "**" + "  \n".join(lines) + "**"
