"""``send-to-buttondown`` — push the issue's ``publish.md`` to Buttondown as a draft.

The bot's job is to **create or update the Buttondown draft idempotently**.
On the first run for an issue, it POSTs ``/emails`` to create the draft
and writes the freshly-minted Buttondown email id back to ``metadata.json``
(field: ``buttondown_id``). On every subsequent run for the same issue,
it PATCHes that same draft so re-running the command is safe — Jamie can
fix a typo in ``intro.md``, re-run ``/eddy issue publish`` → ``/eddy
issue send``, and the existing Buttondown draft is updated in place
rather than creating a duplicate.

**``publish_date`` is never sent.** The bot only stages the draft;
scheduling and the actual send happen by hand in the Buttondown UI after
Jamie reviews. The fields pushed are subject, body, slug, description,
image, and ``status=draft`` — that's it.

If Jamie deletes the draft in Buttondown's UI between runs (so the
``buttondown_id`` we have on file 404s on PATCH), the job falls through
to POST and overwrites the local id with the new one.

The actual API work lives in :func:`pipeline.content.content.buttondown_publish_idempotent`
— this job is a thin async wrapper that surfaces the result to
``#editorial``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from ..tools import db, s3
from . import _base

logger = logging.getLogger("workshop.jobs.send_to_buttondown")

NAME = "send-to-buttondown"


def _import_pipeline_content():
    """Lazy-load ``pipeline/content/content.py`` via ``sys.path``. The
    pipeline isn't a Python package (no ``__init__.py``), so the
    workshop_bot side matches the import pattern used by the existing
    ``PublishToButtondownTests``."""
    repo = Path(__file__).resolve().parents[3]
    pipeline_content_dir = str(repo / "pipeline" / "content")
    if pipeline_content_dir not in sys.path:
        sys.path.insert(0, pipeline_content_dir)
    import content  # noqa: F401
    return content


def _draft_url(buttondown_id: str) -> str:
    """Buttondown's web URL for an email by id. Used in the success card
    so Jamie can click straight from Discord into the draft for review."""
    return f"https://buttondown.com/emails/{buttondown_id}"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — run `/eddy issue start` first.")
    n = int(window["issue_number"])

    # Sanity: publish.md must exist; if it doesn't, point Jamie at the
    # step that creates it rather than punting the error through to
    # Buttondown's API.
    pub_res = await asyncio.to_thread(s3.read_issue_file, n, "publish.md")
    if not (pub_res.get("found") and isinstance(pub_res.get("text"), str) and pub_res["text"].strip()):
        msg = (
            f"❌ `send-to-buttondown` for **WT{n}** can't run — no `publish.md` "
            "in the workspace. Run `/eddy issue publish` first (it assembles "
            "`publish.md` from `final.md` + the compose-\\* assets)."
        )
        await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
        return _base.JobResult(False, msg)

    asset = f"{n}/metadata.json"  # the publisher writes buttondown_id back here
    try:
        with _base.job_lock([asset], NAME):
            pipeline_content = await asyncio.to_thread(_import_pipeline_content)
            try:
                # Off-loop: this hits Buttondown over HTTP and may also
                # write metadata.json back to S3 on a fresh create.
                result: dict[str, Any] = await asyncio.to_thread(
                    pipeline_content.buttondown_publish_idempotent, str(n),
                )
            except pipeline_content.ButtondownPublishError as exc:
                msg = f"❌ `send-to-buttondown` for **WT{n}**: {exc}"
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n})
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `send-to-buttondown` already running ({exc.holder_desc}).")

    action = result["action"]
    bid = result["id"]
    subject = result["subject"]
    draft_url = _draft_url(bid)
    if action == "created":
        head = f"✅ Created Buttondown draft for **WT{n}** — `{subject}`"
        tail = "Re-run `/eddy issue send` to push more edits to the same draft."
    else:
        head = f"♻️ Updated Buttondown draft for **WT{n}** — `{subject}`"
        tail = "Re-run `/eddy issue send` any time to push more edits."
    msg = (
        f"{head}\n"
        f"📨 [open in Buttondown]({draft_url}) — review, schedule, and send when you're ready.\n"
        f"_{tail}_"
    )
    await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
    return _base.JobResult(
        True,
        f"`send-to-buttondown` for WT{n}: {action} (id=`{bid}`).",
        data={
            "issue_number": n,
            "action": action,
            "buttondown_id": bid,
            "draft_url": draft_url,
        },
    )
