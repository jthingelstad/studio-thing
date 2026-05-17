"""``build-publish`` — assemble ``publish.md`` from ``final.md`` + assets.

The ship artifact, byte-shaped like a real Weekly Thing issue body (the
thing ``pipeline/content/content.py publish`` posts to Buttondown). In
order: a leading ``<!-- buttondown-editor-mode: plaintext -->`` comment
glommed onto the intro → ``## Currently`` (if present) → the cover image
block → each non-empty section as ``## Header\\n\\n{content}`` (Notable,
Journal, Briefly — an absent section or any empty section just drops out)
→ the optional ``outro.md`` prose → ``A haiku to leave you with…`` + the
bold/hard-break haiku + the closing "discuss on Reddit" line + the
email-only Tinylytics open-tracking pixel.

**Membership-block resolution.** ``final.md`` carries inline
``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers placed by
``create-final``. ``build-publish`` resolves each marker by reading the
corresponding ``cta-N.md`` / ``thanks-N.md`` file and substituting an
**audience-aware Buttondown Liquid block**:

- ``cta:N`` → non-members only. ``regular`` subscribers see the CTA copy
  plus the two Stripe upgrade buttons; anyone else without a premium
  membership sees the CTA copy plus the subscribe form. Premium members
  fall through to nothing — they're not asked again.
- ``thanks:N`` → premium members only. Everyone else falls through to
  nothing.

The wrapping is done here (not by ``create-final`` or ``compose-cta``)
so the per-issue files (``cta-N.md`` / ``thanks-N.md``) stay clean —
audience-aware Liquid is a publishing concern, not an authoring one.

The parts are joined ``---``-fenced; the ``<!-- block:… -->`` markers
from ``draft.md`` / ``final.md`` never appear in ``publish.md``. The
``.html`` preview is a Liquid-stripped, regular-subscriber rendering —
best-effort.

Refuses (PASSes loudly) if any required asset is missing: ``final.md``,
``haiku.md``, ``metadata.json``, ``intro.md``, ``cover.jpg``. Also
refuses if a marker in ``final.md`` doesn't have its corresponding copy
file written (so a ``<!-- cta:1 -->`` declared by Eddy but never filled
by Patty fails loud rather than shipping with an empty membership
block).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

from ..tools import render, s3
from . import _base, _llm_job

logger = logging.getLogger("workshop.jobs.build_publish")

NAME = "build-publish"

REQUIRED = ("final.md", "haiku.md", "metadata.json", "intro.md", "cover.jpg")

_FIX_HINT = {
    "haiku.md": "→ `/eddy issue haiku`",
    "metadata.json": "→ `/eddy issue subject`",
    "intro.md": "→ write it, push via Shortcut",
    "cover.jpg": "→ Shortcuts uploads this",
    "final.md": "→ `/eddy issue final`",
}

# Section heading map kept for the test helpers; the assembler doesn't
# need it any more (final.md already carries the headings).
_SECTION_HEADINGS = {
    "currently": "## Currently",
    "notable": "## Notable",
    "journal": "## Journal",
    "brief": "## Briefly",
}

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

# Marker pattern create-final places inline in final.md. ``\d+`` for the
# 1-indexed slot number; the ``(cta|thanks)`` group routes to the right
# copy file + Liquid wrapper. Markers are paragraph-isolated on their own
# line in final.md, but the substitution doesn't require that — any
# location works.
_MARKER_RE = re.compile(r"<!--\s*(cta|thanks):(\d+)\s*-->")


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


# ---------- audience-aware Liquid wrappers ----------
#
# Non-members see the supporter CTA (with Stripe upsell buttons for
# ``regular`` subscribers, the subscribe form otherwise). Premium
# subscribers see the thank-you only — they're never asked again, and they
# never see the CTA copy.

def _supporter_block(cta_body: str) -> str:
    """Wrap Patty's supporter-CTA body in the non-member Liquid conditional.

    ``regular`` subscribers (free) see the CTA + two Stripe payment-link
    buttons (``$4 monthly`` / ``$40 yearly``). Anyone else without a
    premium membership — including web previews and non-subscribers —
    sees the CTA + the ``{{ subscribe_form }}``. Premium members fall
    through to nothing.

    The Stripe URLs are the same permanent issue-email payment links
    today's iOS-Shortcut template uses; they live here rather than in a
    data file because they're rarely-changing and audit-trail-noisy.
    """
    body = cta_body.strip()
    return (
        "{% if subscriber.subscriber_type == 'regular' %}\n\n"
        f"{body}\n\n"
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td width="50%" valign="top" style="padding:10px; text-align:center; font-size: 16px; font-weight: bold;">\n'
        '<buttondown-button href="https://buy.stripe.com/3cs7w5eX6aXBbhm144?prefilled_email={{ subscriber.email | urlencode }}">$4 monthly</buttondown-button>\n'
        '</td><td width="50%" valign="top" style="padding:10px; text-align:center; font-size: 16px; font-weight: bold;">\n'
        '<buttondown-button href="https://buy.stripe.com/eVa3fP2ak3v91GMdQR?prefilled_email={{ subscriber.email | urlencode }}">$40 yearly</buttondown-button>\n'
        "</td></tr></table>\n\n"
        "{% elsif subscriber.subscriber_type != 'premium' %}\n\n"
        f"{body}\n\n"
        "{{ subscribe_form }}\n\n"
        "{% endif %}"
    )


def _thanks_block(thanks_body: str) -> str:
    """Wrap Patty's thank-you body in the premium-only Liquid conditional.

    Premium subscribers see the thanks; everyone else falls through to
    nothing — no ask, no acknowledgment they're not in the audience for."""
    body = thanks_body.strip()
    return (
        "{% if subscriber.subscriber_type == 'premium' %}\n\n"
        f"{body}\n\n"
        "{% endif %}"
    )


# ---------- preview rendering (Liquid strip) ----------

def _for_preview(text: str) -> str:
    """Best-effort Liquid strip for the ``publish.html`` preview.

    Renders as a *regular* (free-subscriber) view: keeps the supporter-CTA
    text + the Stripe buttons, hides the premium-only thanks block, drops
    the editor-mode comment and the email-only pixel block, then strips
    any leftover ``{% … %}`` / ``{{ … }}`` tags. The delivered email keeps
    the full Liquid; this only shapes the preview at
    ``https://files.thingelstad.com/weekly-thing/{N}/publish.html``.
    """
    t = re.sub(r"<!--\s*buttondown-editor-mode:[^>]*-->\s*", "", text, flags=re.IGNORECASE)
    # Strip the email-only tinylytics pixel.
    t = re.sub(
        r"\{%\s*if\s+medium\s*==\s*'email'\s*%\}.*?\{%\s*endif\s*%\}",
        "", t, flags=re.DOTALL | re.IGNORECASE,
    )
    # Supporter block: keep the regular-subscriber branch (CTA + Stripe).
    t = re.sub(
        r"\{%\s*if\s+subscriber\.subscriber_type\s*==\s*'regular'\s*%\}(.*?)"
        r"\{%\s*elif\s+subscriber\.subscriber_type\s*!=\s*'premium'\s*%\}.*?"
        r"\{%\s*endif\s*%\}",
        lambda m: m.group(1),
        t,
        flags=re.DOTALL,
    )
    # Thanks block: hide entirely (regulars don't see thanks).
    t = re.sub(
        r"\{%\s*if\s+subscriber\.subscriber_type\s*==\s*'premium'\s*%\}.*?\{%\s*endif\s*%\}",
        "", t, flags=re.DOTALL,
    )
    # Any leftover Liquid tags (e.g. {{ subscriber.email | urlencode }} in
    # the Stripe URLs) — drop them; the preview doesn't need a real subscriber.
    t = re.sub(r"\{%[^%]*%\}", "", t)
    t = re.sub(r"\{\{[^}]*\}\}", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


# ---------- I/O helpers ----------

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


def _filename_for(kind: str, n: int) -> str:
    return f"cta-{n}.md" if kind == "cta" else f"thanks-{n}.md"


def _read_membership_copy(issue_number: int, kind: str, slot_n: int) -> str:
    """Read the body (post-frontmatter) of ``cta-N.md`` or ``thanks-N.md``."""
    raw = _read(issue_number, _filename_for(kind, slot_n))
    if not raw.strip():
        return ""
    _meta, body = _strip_frontmatter(raw)
    return body.strip()


# ---------- marker discovery + missing-list ----------

def _discover_marker_slots(final_text: str) -> list[tuple[str, int]]:
    """Walk ``final.md`` and return declared slots as ``[(kind, num), ...]``
    in visual order, deduped."""
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for m in _MARKER_RE.finditer(final_text or ""):
        slot = (m.group(1), int(m.group(2)))
        if slot in seen:
            continue
        seen.add(slot)
        out.append(slot)
    return out


def _unfilled_marker_missing_list(
    issue_number: int, slots: list[tuple[str, int]],
) -> list[str]:
    """For each declared marker slot, ensure the copy file exists with a
    non-empty body. Return the missing-list entries (formatted to slot in
    next to the per-asset entries from REQUIRED)."""
    missing: list[str] = []
    for kind, slot_n in slots:
        filename = _filename_for(kind, slot_n)
        body = _read_membership_copy(issue_number, kind, slot_n)
        if not body:
            label = "supporter CTA" if kind == "cta" else "thank-you"
            missing.append(
                f"`{filename}` body empty ({label} slot `{kind}:{slot_n}`) → `/patty cta`"
            )
    return missing


# ---------- marker substitution ----------

def _substitute_markers(body: str, issue_number: int) -> str:
    """Replace every ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` in ``body``
    with the audience-aware Liquid block for the corresponding copy file.

    Callers should have already validated that every marker has its copy
    file written; an empty-body slot here is a programming error.
    """
    def _replace(m: re.Match[str]) -> str:
        kind = m.group(1)
        slot_n = int(m.group(2))
        copy = _read_membership_copy(issue_number, kind, slot_n)
        if not copy:
            # Defensive: validated upstream, but if it slips through, leave
            # the marker in place rather than emitting a broken Liquid
            # block. A visible marker in publish.md is easier to spot than
            # silent omission.
            return m.group(0)
        if kind == "cta":
            return _supporter_block(copy)
        return _thanks_block(copy)

    return _MARKER_RE.sub(_replace, body)


# ---------- main ----------

async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    """Transform ``final.md`` into ``publish.md``.

    ``final.md`` is already body-shaped after the row-backed rework:
    promoted (featured) sections splice inline at create-final time,
    cta/thanks markers sit at their declared positions, atoms are
    pulled from their files and embedded in block markers. The
    transformation here is small:

    1. Required-asset gate (``final.md`` / ``haiku.md`` /
       ``metadata.json`` / ``intro.md`` / ``cover.jpg``).
    2. Marker-copy gate (every ``<!-- cta:N -->`` declared in
       ``final.md`` has a non-empty ``cta-N.md``, same for thanks).
    3. Strip block markers (``<!-- block:* -->``).
    4. Substitute cta/thanks markers with audience-aware Liquid blocks
       sourced from ``cta-N.md`` / ``thanks-N.md``.
    5. Prepend ``<!-- buttondown-editor-mode: plaintext -->``
       (glommed onto the first paragraph, mirroring raw Buttondown
       bodies).
    6. Append the Tinylytics email-only tracking pixel.

    Writes ``publish.md`` and a Liquid-stripped ``publish.html`` preview.
    """
    from ..tools import db

    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(False, "❌ no active issue window — run `/eddy issue start` first.")
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

            final_text = _read(n, "final.md") if "final.md" in files else ""
            marker_slots = _discover_marker_slots(final_text)
            marker_missing = _unfilled_marker_missing_list(n, marker_slots)

            if missing or marker_missing:
                lines = [f"⛔ `build-publish` for **WT{n}** can't run yet — missing:"]
                for r in missing:
                    lines.append(f"  ❌ `{r}` {_FIX_HINT.get(r, '')}".rstrip())
                for entry in marker_missing:
                    lines.append(f"  ❌ {entry}")
                msg = "\n".join(lines)
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(
                    False, msg,
                    data={
                        "issue_number": n,
                        "missing": missing,
                        "marker_missing": marker_missing,
                    },
                )

            # Transform final.md → publish.md. The body shape is already
            # correct; we just strip block markers, substitute the
            # membership-block markers, prepend the editor-mode comment,
            # and append the tracking pixel.
            from ..tools import issue_assembly

            body = issue_assembly._strip_block_markers(final_text)
            body = _substitute_markers(body, n)
            # Append the tinylytics pixel before the closing line? No —
            # the pixel sits after the closing emoji at the very end,
            # matching the existing raw-body shape.
            body = body.rstrip() + "\n\n" + _pixel_block(n) + "\n"
            published = _EDITOR_MODE_COMMENT + body

            preview = _for_preview(published)
            s3.write_issue_file(n, "publish.md", published)
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "publish", preview,
                title=f"Weekly Thing {n}", subtitle=None,
            )
            md_url = f"https://files.thingelstad.com/weekly-thing/{n}/publish.md"
            view = (
                f"\n📄 [HTML]({html_url}) · 📝 [markdown]({md_url})"
                if html_url
                else f"\n📝 [markdown]({md_url})"
            )
            await ctx.post(
                "DISCORD_CHANNEL_EDITORIAL",
                f"✅ `publish.md` ready for **WT{n}** (~{len(preview.split())} words){view}\n"
                f"Push to Buttondown with `/eddy issue send` (creates or updates the draft idempotently).",
                persona="eddy",
            )
    except _base.JobLocked as exc:
        return _base.JobResult(False, f"⏳ `build-publish` is already running ({exc.holder_desc}).")
    return _base.JobResult(
        True,
        f"publish.md written for #{n} (~{len(preview.split())} words){f' · 📄 {html_url}' if html_url else ''}.",
        data={"issue_number": n, "preview_url": html_url},
    )
