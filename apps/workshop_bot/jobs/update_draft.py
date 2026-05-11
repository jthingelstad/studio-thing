"""``update-draft`` — project upstream state into ``draft.md``.

A *pure projection*: re-run it and you get the same output (modulo
upstream changes). Each section block is replaced wholesale by its fill
function — no additive merge, no preserve-on-conflict logic. Real
authoring lives upstream (Pinboard for links, micro.blog for the journal,
Drafts → Shortcut for ``intro.md`` / ``currently.md``); the haiku is a
composed asset (``compose-haiku`` writes ``haiku.md``).

**This build (Step 3).** The Pinboard/micro.blog fills (notable, brief,
journal) return placeholder text; the standalone-asset fills (intro,
currently, haiku) read their ``.md`` file from the workspace, leaving the
block empty if absent. Step 4 swaps the placeholders for real source
pulls, writes a ``draft_digests`` row, runs Eddy's post-update review
(silent Sun/Mon), and refuses to run once ``final.md`` exists.
"""

from __future__ import annotations

import logging

from ..tools import db, s3
from . import _base

logger = logging.getLogger("workshop.jobs.update_draft")

NAME = "update-draft"

# The order section blocks appear in the rendered draft. The fills are
# independent; only the output order matters.
SECTION_BLOCKS = ("intro", "notable", "brief", "journal", "currently", "haiku")

# Stub fill content for the source-driven sections — replaced with real
# Pinboard / micro.blog pulls in Step 4.
_PLACEHOLDER = {
    "notable": "_Notable links — pulled from Pinboard (in-window items, not tagged `_brief`)._",
    "brief": "_Briefly items — pulled from Pinboard (in-window items tagged `_brief`)._",
    "journal": "_Journal — pulled from micro.blog (all in-window posts)._",
}

# Standalone assets each section reads when it's a file-backed block.
_ASSET_FILE = {"intro": "intro.md", "currently": "currently.md", "haiku": "haiku.md"}


def _read_asset(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"].strip()
    return ""


def _fill(block: str, issue_number: int) -> str:
    if block in _PLACEHOLDER:
        return _PLACEHOLDER[block]
    asset = _ASSET_FILE.get(block)
    if asset:
        return _read_asset(issue_number, asset)
    return ""


def _load_draft(issue_number: int) -> str:
    res = s3.read_issue_file(issue_number, "draft.md")
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    # Defensive: start-issue seeds draft.md, but fall back to the template
    # so a manual update-draft on a half-set-up issue still produces sane
    # output rather than crashing.
    return _base.starter_template()


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False,
            "❌ no active issue window — run `/workshop job start-issue <n> <pub-date> <days>` first.",
        )
    n = int(window["issue_number"])
    asset = f"{n}/draft.md"
    try:
        with _base.job_lock([asset], NAME):
            draft = _load_draft(n)
            for block in SECTION_BLOCKS:
                draft = _base.replace_block(draft, block, _fill(block, n))
            try:
                s3.write_issue_file(n, "draft.md", draft)
            except Exception as exc:  # noqa: BLE001
                logger.exception("update-draft: write failed for #%d", n)
                return _base.JobResult(
                    False, f"❌ couldn't write `draft.md` for #{n}: `{type(exc).__name__}: {exc}`"
                )
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `update-draft` is already running ({exc.holder_desc}) — try again shortly."
        )

    word_count = len(draft.split())
    return _base.JobResult(
        True,
        f"refreshed `draft.md` for #{n} (~{word_count} words; notable/brief/journal are still placeholder in this build).",
        data={"issue_number": n, "word_count": word_count},
    )
