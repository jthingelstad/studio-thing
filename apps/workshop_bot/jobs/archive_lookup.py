"""``/eddy archive <issue>`` — quick lookup of a past issue's overview.

No LLM call — reads the archive file directly and formats a short
summary (subject, publish date, sections present, word count). Useful
for the slash invocation when Jamie wants Eddy to reference a past
issue without paying for an agent-loop turn.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..tools import archive
from . import _base

logger = logging.getLogger("workshop.jobs.archive_lookup")

NAME = "archive-lookup"

# How many leading body characters to include in the summary (a teaser).
_TEASER_LEN = 320


_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _sections_present(body: str) -> list[str]:
    out: list[str] = []
    for m in _SECTION_HEADING_RE.finditer(body or ""):
        title = m.group(1).strip()
        if title and title not in out:
            out.append(title)
    return out


def _teaser(body: str) -> str:
    s = (body or "").strip()
    if not s:
        return ""
    s = s.split("\n\n", 1)[0]  # first paragraph
    if len(s) > _TEASER_LEN:
        s = s[: _TEASER_LEN - 1] + "…"
    return s


async def run(
    ctx: "_base.JobContext",
    *,
    issue_number: int,
    post_to_channel: Optional[str] = "DISCORD_CHANNEL_EDITORIAL",
) -> "_base.JobResult":
    try:
        n = int(issue_number)
    except (TypeError, ValueError):
        return _base.JobResult(False, f"❌ `{issue_number!r}` isn't a valid issue number.")
    if n < 1:
        return _base.JobResult(False, "❌ issue number must be positive.")

    issue = archive.read_issue(n)
    if issue is None:
        return _base.JobResult(False, f"❌ no archive file for issue {n}.")

    fm = issue.get("frontmatter") or {}
    body = issue.get("body") or ""
    subject = fm.get("subject") or "(no subject)"
    pub_date = (fm.get("publish_date") or "")[:10] or "?"
    word_count = len((body or "").split())
    sections = _sections_present(body)
    teaser = _teaser(body)

    lines = [
        f"📚 **WT{n}** · _{pub_date}_ · {word_count:,} words",
        f"**Subject:** {subject}",
    ]
    if sections:
        lines.append("**Sections:** " + " · ".join(sections))
    if teaser:
        lines.append("")
        lines.append("> " + teaser.replace("\n", "\n> "))

    summary = "\n".join(lines)

    posted = False
    if post_to_channel:
        posted = await ctx.post(post_to_channel, summary, persona="eddy")
    return _base.JobResult(
        True,
        summary,
        data={"issue_number": n, "subject": subject, "publish_date": pub_date,
              "word_count": word_count, "sections": sections, "posted": bool(posted)},
    )
