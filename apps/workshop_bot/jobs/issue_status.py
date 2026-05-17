"""``issue-status`` — read-only state report on the in-flight issue.

Reports section completeness (from parsing ``draft.md``) and
required/optional asset presence (from the workspace listing) plus
days-to-pub. Delegates the computation to ``tools.draft.section_status``.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..tools import db
from ..tools.content import draft as draft_mod
from . import _base

logger = logging.getLogger("workshop.jobs.issue_status")

NAME = "issue-status"


def _days_to(target_iso: str) -> str:
    try:
        d = (datetime.strptime(target_iso, "%Y-%m-%d").date() - datetime.now().date()).days
    except (TypeError, ValueError):
        return "?"
    if d == 0:
        return "today"
    if d > 0:
        return f"in {d}d"
    return f"{-d}d ago"


def render_status_card(window: dict, st: dict) -> str:
    """Render the readiness checklist as a Discord-ready markdown card.

    Shared with ``update-draft`` so the post-update snapshot to ``#editorial``
    is byte-identical to what ``/eddy issue status`` prints.
    """
    n = int(window["issue_number"])

    def m(flag: bool) -> str:
        return "✅" if flag else "❌"

    sec = st["sections"]

    def secline(name: str, label: str) -> str:
        s = sec[name]
        if s["placeholder"]:
            tag = "⚠️ placeholder"
        elif s["present"]:
            tag = f"{s['item_count']} item{'s' if s['item_count'] != 1 else ''}"
        else:
            tag = "empty"
        return f"  {m(s['present'])} {label} ({tag})"

    lines = [
        f"📋 **WT{n}** — issue status · pub {window['pub_date']} ({_days_to(window['pub_date'])}) · cutoff {window['end_date']}",
        f"draft.md: {m(st['assets'].get('draft.md', False))}  ·  final.md: {m(st['assets'].get('final.md', False))}  ·  publish.md: {m(st['assets'].get('publish.md', False))}  ·  ~{st['word_count']} words",
        "",
        "**Required for ship:**",
        secline("notable", "Notable"),
        secline("brief", "Briefly"),
        secline("journal", "Journal"),
        f"  {m(st['assets'].get('haiku.md', False))} `haiku.md`" + ("" if st["assets"].get("haiku.md") else " → `/eddy issue haiku`"),
        f"  {m(st['assets'].get('metadata.json', False))} `metadata.json`" + ("" if st["assets"].get("metadata.json") else " → `/eddy issue subject`"),
        f"  {m(st['intro_present'])} `intro.md`" + ("" if st["intro_present"] else " → write it, push via Shortcut"),
        f"  {m(st['cover_present'])} `cover.jpg`",
        f"  {m(st['assets'].get('final.md', False))} `final.md`" + ("" if st["assets"].get("final.md") else " → `/eddy issue final`"),
        "",
        "**Optional:**",
        f"  {m(st['currently_present'])} `currently.json` (or legacy `currently.md`)",
        "  " + (f"✅ CTAs: {', '.join('`' + c + '`' for c in st['cta_files'])}" if st["cta_files"] else "⚪ CTAs: none (compose-cta not run / 0 CTAs)"),
        "",
        ("✅ **ship-ready** — `build-publish` would proceed." if st["ship_ready"]
         else f"❌ **not ship-ready** — missing: {', '.join(st['required_missing'])}"),
    ]
    return "\n".join(lines)


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "No active issue window. Run `/eddy issue start <n> <pub-date> <days>`."
        )
    n = int(window["issue_number"])
    try:
        st = draft_mod.section_status(n)
    except Exception as exc:  # noqa: BLE001
        logger.exception("issue-status: section_status failed for #%d", n)
        return _base.JobResult(False, f"❌ couldn't read the workspace for #{n}: `{type(exc).__name__}: {exc}`")

    return _base.JobResult(True, render_status_card(window, st), data={"issue_number": n, "section_status": st})
