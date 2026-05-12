"""``build-publish`` — assemble ``publish.md`` from ``final.md`` + assets.

The ship artifact, shaped like a real Weekly Thing issue. Top-level parts —
the intro (which carries its own ``---`` and cover block), each non-empty
section as ``## Header\n\n{content}`` (an absent ``currently.md`` or any
empty section just drops out — "a section that didn't run is a clean
NULL"), the CTAs at their placements, and ``A haiku to leave you with…`` +
the bold/hard-break haiku + the closing "discuss on Reddit" line — are
joined ``---``-fenced. The ``<!-- block:… -->`` markers from ``draft.md`` /
``final.md`` never appear in ``publish.md``.

Refuses (PASSes loudly) if any required asset is missing: ``final.md``,
``haiku.md``, ``metadata.json``, ``intro.md``, ``cover.jpg``. Posts the
missing list to ``#editorial`` with the slash command(s) to run.
"""

from __future__ import annotations

import asyncio
import logging
import re

from ..tools import draft as draft_mod
from ..tools import render, s3
from . import _base

logger = logging.getLogger("workshop.jobs.build_publish")

NAME = "build-publish"

REQUIRED = ("final.md", "haiku.md", "metadata.json", "intro.md", "cover.jpg")

_FIX_HINT = {
    "haiku.md": "→ `/workshop issue haiku`",
    "metadata.json": "→ `/workshop issue subject`",
    "intro.md": "→ write it, push via Shortcut",
    "cover.jpg": "→ Shortcuts uploads this",
    "final.md": "→ `/workshop issue final`",
}

# (block name → published heading). intro/haiku are special-cased (no
# header / closes the issue); the rest are emitted in this order, each
# only if its content is non-empty. The order mirrors recently-published
# issues: Currently (when present) sits up top after the intro, then
# Notable, then Journal, then Briefly, then the closing haiku.
_SECTION_HEADINGS = {
    "currently": "## Currently",
    "notable": "## Notable",
    "journal": "## Journal",
    "brief": "## Briefly",
}
_ORDER = ("currently", "notable", "journal", "brief")

_PLACEMENTS = ("after_notable", "after_journal", "after_brief", "before_haiku")
_DEFAULT_PLACEMENT = "after_notable"

# The closing boilerplate every issue ends with, after the haiku (no `---`
# between the haiku and this — they're one chunk).
_CLOSING = (
    "Would you like to discuss the topics in the Weekly Thing further? "
    "Check out the [Weekly Thing on Reddit](https://www.reddit.com/r/weeklything/). 👋\n\n"
    "👨‍💻"
)


def _read(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    return ""


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


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    from ..tools import db

    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — run `/workshop issue start` first.")
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

            final_text = _read(n, "final.md")
            blocks = draft_mod.parse_blocks(final_text)
            # intro / cover / currently / haiku are file-backed; their
            # blocks in final.md are empty (they get filled here).
            section_content = {
                "notable": (blocks.get("notable") or "").strip(),
                "brief": (blocks.get("brief") or "").strip(),
                "journal": (blocks.get("journal") or "").strip(),
                "currently": _read(n, "currently.md").strip(),
            }
            intro_text = _read(n, "intro.md").strip()
            cover_text = _read(n, "cover.md").strip()
            cover_block = (
                f"![](https://files.thingelstad.com/weekly-thing/{n}/cover.jpg)\n\n{cover_text}"
                if cover_text else ""
            )
            haiku_text = _read(n, "haiku.md").strip()

            # CTAs by placement (cta-1.md / cta-2.md, ordered).
            cta_by_placement: dict[str, list[str]] = {}
            for cta_name in sorted(f for f in files if f.startswith("cta-") and f.endswith(".md")):
                raw = _read(n, cta_name)
                if not raw.strip():
                    continue
                meta, cta_body = _strip_frontmatter(raw)
                placement = (meta.get("placement") or _DEFAULT_PLACEMENT).strip()
                if placement not in _PLACEMENTS:
                    placement = _DEFAULT_PLACEMENT
                cta_by_placement.setdefault(placement, []).append(cta_body.strip())

            parts: list[str] = []
            if intro_text:
                parts.append(intro_text)
            if cover_block:
                parts.append(cover_block)
            for name in _ORDER:
                content = section_content.get(name, "")
                if not content:
                    continue
                parts.append(f"{_SECTION_HEADINGS[name]}\n\n{content}")
                for cta in cta_by_placement.get(f"after_{name}", []):
                    parts.append(cta)
            for cta in cta_by_placement.get("before_haiku", []):
                parts.append(cta)
            if haiku_text:
                parts.append(
                    f"A haiku to leave you with…\n\n{_base.format_haiku(haiku_text)}\n\n{_CLOSING}"
                )
            else:
                parts.append(_CLOSING)

            # Each top-level part is `---`-fenced, the way a published issue is.
            published = "\n\n---\n\n".join(p.strip() for p in parts if p.strip()).strip() + "\n"
            s3.write_issue_file(n, "publish.md", published)
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "publish", published,
                title=f"Weekly Thing {n}", subtitle=None,
            )
            view = f"\n📄 [view it]({html_url})" if html_url else ""
            await ctx.post(
                "DISCORD_CHANNEL_EDITORIAL",
                f"✅ `publish.md` ready for **WT{n}** (~{len(published.split())} words){view}\n"
                f"Push via `pipeline/content/content.py publish --issue {n}` (creates a Buttondown draft) when you're ready.",
                persona="eddy",
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `build-publish` is already running ({exc.holder_desc}).")
    return _base.JobResult(
        True,
        f"publish.md written for #{n} (~{len(published.split())} words){f' · 📄 {html_url}' if html_url else ''}.",
        data={"issue_number": n, "preview_url": html_url},
    )
