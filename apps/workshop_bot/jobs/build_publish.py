"""``build-publish`` — assemble ``publish.md`` from ``final.md`` + assets.

The ship artifact, byte-shaped like a real Weekly Thing issue body (the
thing ``pipeline/content/content.py publish`` posts to Buttondown). In
order: a leading ``<!-- buttondown-editor-mode: plaintext -->`` comment
glommed onto the intro → ``## Currently`` (if present) → the cover image
block → each non-empty section as ``## Header\n\n{content}`` (Notable,
Journal, Briefly — an absent ``currently.json`` / ``currently.md`` or any
empty section just drops out, "a section that didn't run is a clean NULL")
→ the CTAs at their placements, each wrapped in the membership-block Liquid
scaffold (premium / regular + Stripe buttons / else + ``{{ subscribe_form }}``)
→ ``A haiku to leave you with…`` + the bold/hard-break haiku + the closing
"discuss on Reddit" line + the email-only Tinylytics open-tracking pixel.
The parts are joined ``---``-fenced; the ``<!-- block:… -->`` markers from
``draft.md`` / ``final.md`` never appear in ``publish.md``. The ``.html``
preview is a Liquid-stripped, regular-subscriber rendering — best-effort.

Refuses (PASSes loudly) if any required asset is missing: ``final.md``,
``haiku.md``, ``metadata.json``, ``intro.md``, ``cover.jpg``. Posts the
missing list to ``#editorial`` with the slash command(s) to run.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

from ..tools.content import draft as draft_mod
from ..tools import render, s3
from . import _base, _llm_job, _cover, _currently

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

# (block name → published heading). intro / the cover block / haiku are
# special-cased in the assembly; the rest are emitted in `_ORDER`, each only
# if its content is non-empty. Issue layout: intro → `## Currently` (when
# present) → cover image → Notable → Journal → Briefly → the closing haiku.
_SECTION_HEADINGS = {
    "currently": "## Currently",
    "notable": "## Notable",
    "journal": "## Journal",
    "brief": "## Briefly",
}
_ORDER = ("notable", "journal", "brief")  # Currently is placed above the cover; see the assembly

# The closing boilerplate every issue ends with, after the haiku (no `---`
# between the haiku and this — they're one chunk).
_CLOSING = (
    "Would you like to discuss the topics in the Weekly Thing further? "
    "Check out the [Weekly Thing on Reddit](https://www.reddit.com/r/weeklything/). 👋\n\n"
    "👨‍💻"
)

# Buttondown marks plaintext-mode emails with this comment at the top of the
# body (glommed onto the first line, as the raw archive bodies have it).
_EDITOR_MODE_COMMENT = "<!-- buttondown-editor-mode: plaintext -->"

# Public (browser-script / pixel) Tinylytics id — the email open-tracking
# pixel uses it. Same id as the site's analytics; overridable for tests.
_DEFAULT_TINYLYTICS_UID = "a2YQr3ZMqkySNYSwz4uF"


def _tinylytics_uid() -> str:
    return (os.environ.get("TINYLYTICS_SITE_UID") or _DEFAULT_TINYLYTICS_UID).strip()


def _pixel_block(issue_number: int) -> str:
    """The email-only Tinylytics open-tracking pixel — Liquid-gated like the
    raw bodies (no-op outside ``medium == 'email'``; the archive build strips it)."""
    return (
        "{% if medium == 'email' %}\n"
        f'<img src="https://tinylytics.app/pixel/{_tinylytics_uid()}.gif?path=/email/{issue_number}/" '
        'alt="" style="width:1px;height:1px;border:0;" />\n'
        "{% endif %}"
    )


# Membership-block scaffold each composed CTA is wrapped in (mirrors the
# iOS-Shortcut template): premium and regular subscribers see the CTA copy;
# regular subscribers additionally get the two Stripe Payment Link buttons;
# everyone else gets the subscribe form. The Stripe links are the permanent
# issue-email Payment Links (the same ones recent issues use — these live in
# the Shortcut template, not a repo data file). ``__CTA__`` is the slot for
# the composed copy.
_MEMBERSHIP_BLOCK = """{% if subscriber.subscriber_type == 'premium' %}

__CTA__

{% elif subscriber.subscriber_type == 'regular' %}

__CTA__

<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td width="50%" valign="top" style="padding:10px; text-align:center; font-size: 16px; font-weight: bold;">
<buttondown-button href="https://buy.stripe.com/3cs7w5eX6aXBbhm144?prefilled_email={{ subscriber.email | urlencode }}">$4 monthly</buttondown-button>
</td><td width="50%" valign="top" style="padding:10px; text-align:center; font-size: 16px; font-weight: bold;">
<buttondown-button href="https://buy.stripe.com/eVa3fP2ak3v91GMdQR?prefilled_email={{ subscriber.email | urlencode }}">$40 yearly</buttondown-button>
</td></tr></table>

{% else %}

Enjoying the Weekly Thing?

{{ subscribe_form }}

{% endif %}"""


def _membership_block(cta_body: str) -> str:
    return _MEMBERSHIP_BLOCK.replace("__CTA__", cta_body.strip())


def _for_preview(text: str) -> str:
    """Best-effort Liquid strip for the ``publish.html`` preview: drop the
    editor-mode comment and the email-only pixel block, keep just the
    ``regular``-subscriber branch of each membership block, then remove any
    leftover ``{% … %}`` / ``{{ … }}`` tags. The delivered email keeps the
    full Liquid; this only shapes the preview."""
    t = re.sub(r"<!--\s*buttondown-editor-mode:[^>]*-->\s*", "", text, flags=re.IGNORECASE)
    t = re.sub(r"\{%\s*if\s+medium\s*==\s*'email'\s*%\}.*?\{%\s*endif\s*%\}", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(
        r"\{%\s*if\s+subscriber\.subscriber_type[^%]*%\}.*?"
        r"\{%\s*elif\s+subscriber\.subscriber_type\s*==\s*'regular'\s*%\}(.*?)"
        r"\{%\s*else\s*%\}.*?\{%\s*endif\s*%\}",
        lambda m: m.group(1),
        t,
        flags=re.DOTALL,
    )
    t = re.sub(r"\{%[^%]*%\}", "", t)
    t = re.sub(r"\{\{[^}]*\}\}", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


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
                "currently": _currently.render(n),  # currently.json (preferred) or legacy currently.md
            }
            intro_text = _read(n, "intro.md").strip()
            cover_text = _cover.render(n)  # cover.json (preferred) or legacy cover.md
            cover_alt = _cover.alt(n)
            from html import escape as _esc
            cover_img = (
                f'<img src="https://files.thingelstad.com/weekly-thing/{n}/cover.jpg" '
                f'alt="{_esc(cover_alt, quote=True)}" />'
            )
            cover_block = f"{cover_img}\n\n{cover_text}" if cover_text else ""
            haiku_text = _read(n, "haiku.md").strip()

            # CTAs by placement (cta-1.md / cta-2.md, ordered). Each composed
            # CTA body is wrapped in the membership-block Liquid scaffold.
            cta_by_placement: dict[str, list[str]] = {}
            for cta_name in sorted(f for f in files if f.startswith("cta-") and f.endswith(".md")):
                raw = _read(n, cta_name)
                if not raw.strip():
                    continue
                meta, cta_body = _strip_frontmatter(raw)
                if not cta_body.strip():
                    continue
                placement = (meta.get("placement") or _llm_job.DEFAULT_PLACEMENT).strip()
                if placement not in _llm_job.PLACEMENTS:
                    placement = _llm_job.DEFAULT_PLACEMENT
                cta_by_placement.setdefault(placement, []).append(_membership_block(cta_body))

            parts: list[str] = []
            if intro_text:
                parts.append(intro_text)
            # Currently sits between the intro and the cover image.
            currently_content = section_content.get("currently", "")
            if currently_content:
                parts.append(f"{_SECTION_HEADINGS['currently']}\n\n{currently_content}")
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
            # Haiku close + the email-only Tinylytics pixel — one chunk, no
            # `---` between them and the closing line.
            close = f"A haiku to leave you with…\n\n{_base.format_haiku(haiku_text)}\n\n{_CLOSING}" if haiku_text else _CLOSING
            parts.append(f"{close}\n\n{_pixel_block(n)}")

            # Each top-level part is `---`-fenced; the editor-mode comment is
            # glommed onto the very front (as the raw bodies have it).
            body = "\n\n---\n\n".join(p.strip() for p in parts if p.strip()).strip() + "\n"
            published = f"{_EDITOR_MODE_COMMENT}{body}"
            preview = _for_preview(published)
            s3.write_issue_file(n, "publish.md", published)
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "publish", preview,
                title=f"Weekly Thing {n}", subtitle=None,
            )
            view = f"\n📄 [view it]({html_url})" if html_url else ""
            await ctx.post(
                "DISCORD_CHANNEL_EDITORIAL",
                f"✅ `publish.md` ready for **WT{n}** (~{len(preview.split())} words){view}\n"
                f"Push via `pipeline/content/content.py publish --issue {n}` (creates a Buttondown draft) when you're ready.",
                persona="eddy",
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `build-publish` is already running ({exc.holder_desc}).")
    return _base.JobResult(
        True,
        f"publish.md written for #{n} (~{len(preview.split())} words){f' · 📄 {html_url}' if html_url else ''}.",
        data={"issue_number": n, "preview_url": html_url},
    )
