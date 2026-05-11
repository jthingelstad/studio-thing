"""``build-publish`` — assemble ``publish.md`` from ``final.md`` + assets.

The ship artifact. Walks the issue's sections in order and emits each as
``## Header\n\n{content}`` — but **only when the content is non-empty**, so
an absent ``currently.md`` (or any optional section) just drops out rather
than leaving a bare heading (the "a section that didn't run is a clean
NULL" pattern). The intro goes at the very top with no header; the haiku
closes the issue; CTAs are inserted at their declared placements. The
``<!-- block:… -->`` markers from ``draft.md`` / ``final.md`` never appear
in ``publish.md``.

Refuses (PASSes loudly) if any required asset is missing: ``final.md``,
``haiku.md``, ``metadata.json``, ``intro.md``, ``cover.jpg``. Posts the
missing list to ``#editorial`` with the slash command(s) to run.
"""

from __future__ import annotations

import logging
import re

from ..tools import draft as draft_mod
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

# (block name, published heading). intro/haiku are special-cased (no
# header / closes the issue); the rest are emitted in this order, each
# only if its content is non-empty.
_SECTION_HEADINGS = {
    "notable": "## Notable",
    "brief": "## Briefly",
    "journal": "## Journal",
    "currently": "## Currently",
}
_ORDER = ("notable", "brief", "journal", "currently")

_PLACEMENTS = ("after_notable", "after_brief", "after_journal", "before_haiku")


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

            final_text = _read(n, "final.md")
            blocks = draft_mod.parse_blocks(final_text)
            # intro / currently / haiku are file-backed; their blocks in
            # final.md are empty (they get filled here).
            section_content = {
                "notable": (blocks.get("notable") or "").strip(),
                "brief": (blocks.get("brief") or "").strip(),
                "journal": (blocks.get("journal") or "").strip(),
                "currently": _read(n, "currently.md").strip(),
            }
            intro_text = _read(n, "intro.md").strip()
            haiku_text = _read(n, "haiku.md").strip()

            # CTAs by placement (cta-1.md / cta-2.md, ordered).
            cta_by_placement: dict[str, list[str]] = {}
            for cta_name in sorted(f for f in files if f.startswith("cta-") and f.endswith(".md")):
                raw = _read(n, cta_name)
                if not raw.strip():
                    continue
                meta, cta_body = _strip_frontmatter(raw)
                placement = (meta.get("placement") or "after_brief").strip()
                if placement not in _PLACEMENTS:
                    placement = "after_brief"
                cta_by_placement.setdefault(placement, []).append(cta_body.strip())

            parts: list[str] = []
            if intro_text:
                parts.append(intro_text)
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
                parts.append(f"## Haiku\n\n{haiku_text}")

            published = "\n\n".join(p.strip() for p in parts if p.strip()).strip() + "\n"
            s3.write_issue_file(n, "publish.md", published)
            await ctx.post(
                "DISCORD_CHANNEL_EDITORIAL",
                f"✅ `publish.md` ready for **WT{n}** (~{len(published.split())} words) — "
                f"push via `pipeline/content/content.py publish --issue {n}` (creates a Buttondown draft) when you're ready.",
                persona="eddy",
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `build-publish` is already running ({exc.holder_desc}).")
    return _base.JobResult(True, f"publish.md written for #{n} (~{len(published.split())} words).",
                           data={"issue_number": n})
