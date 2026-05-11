"""``issue-status`` — read-only state report on the in-flight issue.

Lists which required / optional assets are present in the per-issue
workspace. Step 4 adds section-completeness (``draft__section_status``)
and queue-depth context; for now this is a file-presence report.
"""

from __future__ import annotations

import logging

from ..tools import db, s3
from . import _base

logger = logging.getLogger("workshop.jobs.issue_status")

NAME = "issue-status"

# Required-for-ship assets (build-publish refuses without these). The
# Notable / Brief / Journal *sections* are also required — Step 4's
# draft__section_status check covers those; here we just confirm draft.md
# exists.
REQUIRED_FILES = ("final.md", "haiku.md", "metadata.json", "intro.md", "cover.jpg")
OPTIONAL_FILES = ("currently.md",)


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "No active issue window. Run `/workshop job start-issue <n> <pub-date> <days>`."
        )
    n = int(window["issue_number"])
    try:
        listing = s3.list_issue(n)
        files = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
    except Exception as exc:  # noqa: BLE001
        logger.exception("issue-status: failed to list workspace for #%d", n)
        return _base.JobResult(
            False, f"❌ couldn't list the workspace for #{n}: `{type(exc).__name__}: {exc}`"
        )

    def mark(name: str) -> str:
        return "✅" if name in files else "❌"

    cta_files = sorted(f for f in files if f.startswith("cta-") and f.endswith(".md"))

    lines = [
        f"📋 **WT{n}** — issue status · pub {window['pub_date']} · cutoff {window['end_date']}",
        "",
        f"{'✅' if 'draft.md' in files else '❌'} `draft.md`"
        + (f" · {'✅' if 'final.md' in files else '⚪'} `final.md`"
           f" · {'✅' if 'publish.md' in files else '⚪'} `publish.md`"),
        "",
        "**Required for ship:**",
    ]
    for name in REQUIRED_FILES:
        lines.append(f"  {mark(name)} `{name}`")
    lines.append("")
    lines.append("**Optional:**")
    for name in OPTIONAL_FILES:
        lines.append(f"  {mark(name)} `{name}`")
    lines.append(
        "  " + (f"✅ CTAs: {', '.join('`' + c + '`' for c in cta_files)}" if cta_files
                else "⚪ CTAs: none yet")
    )
    return _base.JobResult(
        True, "\n".join(lines), data={"issue_number": n, "files": sorted(files)}
    )
