"""``build-publish`` — assemble ``publish.md`` from ``final.md`` + assets.

The ship artifact. Reads ``final.md`` (post-Eddy, block-structured) and
inlines the standalone assets at their positions: ``intro.md`` at the top
(the intro block), ``haiku.md`` at the end (the haiku block),
``currently.md`` if present (the currently block), and ``cta-*.md`` at
their declared placements. Strips the ``<!-- block:… -->`` markers. Writes
``publish.md`` — the artifact the existing pipeline/content push reads.

Refuses (PASSes loudly) if any required asset is missing: ``final.md``,
``haiku.md``, ``metadata.json``, ``intro.md``, ``cover.jpg``. Posts the
missing list to ``#editorial`` with the slash command(s) to run.
"""

from __future__ import annotations

import logging
import re

from ..tools import s3
from . import _base

logger = logging.getLogger("workshop.jobs.build_publish")

NAME = "build-publish"

REQUIRED = ("final.md", "haiku.md", "metadata.json", "intro.md", "cover.jpg")

_FIX_HINT = {
    "haiku.md": "→ `/workshop job compose-haiku`",
    "metadata.json": "→ `/workshop job compose-meta`",
    "intro.md": "→ write it, push via Shortcut",
    "cover.jpg": "→ Shortcuts uploads this",
    "final.md": "→ `/workshop job create-final`",
}

# CTA placement → where it goes in the body. ``after_X`` = immediately
# after the closing block marker for X; ``before_haiku`` = right before
# the ## Haiku heading. Never above the intro.
_PLACEMENTS = ("after_notable", "after_brief", "after_journal", "before_haiku")


def _read(issue_number: int, filename: str) -> tuple[bool, str]:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return True, res["text"]
    return bool(res.get("found")), ""


def _strip_frontmatter(text: str) -> tuple[dict, str]:
    """If ``text`` starts with a YAML frontmatter block (``---`` … ``---``),
    parse the simple ``key: value`` lines and return (meta, body)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, m.group(2).lstrip("\n")


def _insert_cta(body: str, placement: str, cta_text: str) -> str:
    cta_block = f"\n\n{cta_text.strip()}\n"
    if placement == "before_haiku":
        anchor = "## Haiku"
        i = body.find(anchor)
        if i >= 0:
            return body[:i] + cta_text.strip() + "\n\n" + body[i:]
        return body.rstrip() + cta_block  # fallback: append
    section = {"after_notable": "notable", "after_brief": "brief", "after_journal": "journal"}.get(placement)
    if section:
        marker = f"<!-- /block:{section} -->"
        i = body.find(marker)
        if i >= 0:
            j = i + len(marker)
            return body[:j] + cta_block + body[j:]
    # Unknown placement → drop it after Briefly as a safe default.
    marker = "<!-- /block:brief -->"
    i = body.find(marker)
    if i >= 0:
        j = i + len(marker)
        return body[:j] + cta_block + body[j:]
    return body.rstrip() + cta_block


def _strip_block_markers(text: str) -> str:
    text = re.sub(r"<!--\s*/?block:[a-z0-9_-]+\s*-->\n?", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    from ..tools import db
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — run `/workshop job start-issue` first.")
    n = int(window["issue_number"])

    asset = f"{n}/publish.md"
    try:
        with _base.job_lock([asset], NAME):
            try:
                listing = s3.list_issue(n)
                files = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
            except Exception:  # noqa: BLE001
                files = set()
            missing = [r for r in REQUIRED if r not in files]
            if missing:
                lines = [f"⛔ `build-publish` for **WT{n}** can't run yet — missing:"]
                for r in missing:
                    lines.append(f"  ❌ `{r}` {_FIX_HINT.get(r, '')}".rstrip())
                msg = "\n".join(lines)
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(False, msg, data={"issue_number": n, "missing": missing})

            ok_final, final_text = _read(n, "final.md")
            ok_intro, intro_text = _read(n, "intro.md")
            ok_haiku, haiku_text = _read(n, "haiku.md")
            ok_currently, currently_text = _read(n, "currently.md")

            body = _base.replace_block(final_text, "intro", intro_text)
            body = _base.replace_block(body, "haiku", haiku_text)
            if ok_currently and currently_text.strip():
                body = _base.replace_block(body, "currently", currently_text)

            # CTAs — read cta-1.md / cta-2.md, place by frontmatter.
            for cta_name in sorted(f for f in files if f.startswith("cta-") and f.endswith(".md")):
                _ok, raw = _read(n, cta_name)
                if not raw.strip():
                    continue
                meta, cta_body = _strip_frontmatter(raw)
                placement = (meta.get("placement") or "after_brief").strip()
                if placement not in _PLACEMENTS:
                    placement = "after_brief"
                body = _insert_cta(body, placement, cta_body)

            published = _strip_block_markers(body)
            s3.write_issue_file(n, "publish.md", published)
            await ctx.post(
                "DISCORD_CHANNEL_EDITORIAL",
                f"✅ `publish.md` ready for **WT{n}** (~{len(published.split())} words) — "
                "push via the existing `pipeline/content/` Buttondown flow whenever you're ready.",
                persona="eddy",
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `build-publish` is already running ({exc.holder_desc}).")
    return _base.JobResult(True, f"publish.md written for #{n} (~{len(published.split())} words).",
                           data={"issue_number": n})
