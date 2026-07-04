"""Pure renderers for the four issue artifact formats.

draft.md, archive.md, buttondown.md, and transcript/*.txt each have
their own composition path. Every format takes the same structured
inputs (atoms + section bodies + features + metadata + cta atoms +
echoes) and emits its own bytes directly. There is no shared
intermediate text body that one format mutates while another strips.
Each format embraces its medium's strengths: the website carries
front matter + links extraction, the email carries audience-aware
Liquid blocks + a tracking pixel, the audio path strips the cover
atom at composition time and runs the body-to-script transform for
TTS-shape work.

The single shared piece is ``_compose_published_body`` — a structural
helper that joins `---`-fenced parts. It takes optional per-section
trailers (the email's Liquid splice hook) but doesn't insert markers
or mutate text on the way out. Each renderer calls it once and adds
its own format-specific touches.

Conventions:

- All functions are pure: no S3 reads, no DB lookups, no file writes.
  Inputs are dicts and strings; outputs are strings or tuples thereof.
- ``atoms`` keys: ``intro``, ``currently``, ``cover``, ``outro``,
  ``haiku``. Missing keys default to empty.
- ``sections`` keys: ``notable``, ``journal``, ``brief``. Rendered
  section bodies, no CTA / thanks markers — supporter callouts only
  enter the body via render_email_body's trailer hook.
- ``features``: ``[(promoted_position, '## Heading\\n\\nbody'), ...]``
  with positions ``"before_notable"`` / ``"after_notable"`` / etc.
- ``cta_atoms``: ``{"cta:1": "supporter ask copy", "thanks:1": "..."}``
  — already-loaded copy strings keyed by ``kind:slot_n``. Empty
  slots are simply skipped (no Liquid block emitted).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional

import yaml

logger = logging.getLogger("workshop.renderers")


# ---------- email (buttondown.md) ----------

# Buttondown's plaintext-mode marker — glommed to the top of the body.
_EDITOR_MODE_COMMENT = "<!-- buttondown-editor-mode: plaintext -->"

# Public tinylytics site UID for the email open-tracking pixel. Mirrors
# the one in jobs/build_publish.py — duplicated here so the pure
# renderer doesn't reach into a jobs module. Overridable via env for
# tests.
_DEFAULT_TINYLYTICS_UID = "a2YQr3ZMqkySNYSwz4uF"


def _tinylytics_uid() -> str:
    import os
    return (os.environ.get("TINYLYTICS_SITE_UID") or _DEFAULT_TINYLYTICS_UID).strip()


def pixel_block(issue_number: int) -> str:
    """The email-only Tinylytics open-tracking pixel. Wrapped in a
    Liquid ``{% if medium == 'email' %}`` guard so Buttondown's
    web-rendered view doesn't fire it. Public so impure callers can
    re-use it; pure renderers compose it in directly."""
    return (
        "{% if medium == 'email' %}\n"
        f'<img src="https://tinylytics.app/pixel/{_tinylytics_uid()}.gif?path=/email/{issue_number}/" '
        'alt="" style="width:1px;height:1px;border:0;" />\n'
        "{% endif %}"
    )


def supporter_block(cta_body: str, *, issue_number: int) -> str:
    """Audience-aware Liquid wrapper for a non-member CTA.

    ``regular`` subscribers see the CTA + a single "Become a Supporting
    Member" button linking to the website's ``/members/`` page (which
    explains the offer and routes onward — no direct Stripe links from
    the email). The link carries the subscriber's email (so the members
    page can prefill it) and ``?ref=WT{N}`` so traffic-by-issue is
    legible to ``tinylytics`` analytics.

    Everyone else (premium members, anonymous web visitors viewing the
    archive page) falls through to nothing — no CTA, no subscribe form.

    The leading ``---`` divider lives *inside* the conditional, so the
    audience that doesn't see the CTA doesn't see an empty divider
    either — adjacent sections collapse to one ``<hr/>`` instead of two.
    """
    body = cta_body.strip()
    n = int(issue_number)
    member_url = (
        "https://weekly.thingelstad.com/members/"
        f"?email={{{{ subscriber.email | urlencode }}}}&ref=WT{n}"
    )
    return (
        "{% if subscriber.subscriber_type == 'regular' %}\n\n"
        "---\n\n"
        f"{body}\n\n"
        '<p style="text-align:center; padding:10px 0; font-size: 16px; font-weight: bold;">\n'
        f'<buttondown-button href="{member_url}">Become a Supporting Member</buttondown-button>\n'
        "</p>\n\n"
        "{% endif %}"
    )


def thanks_block(thanks_body: str) -> str:
    """Audience-aware Liquid wrapper for a premium-only thank-you.

    Premium subscribers see the thanks; everyone else falls through
    to nothing. The leading ``---`` divider lives inside the
    conditional so non-premium audiences don't see two ``<hr/>`` in a
    row where the empty thanks would otherwise sit between two
    dividers.
    """
    body = thanks_body.strip()
    return (
        "{% if subscriber.subscriber_type == 'premium' %}\n\n"
        "---\n\n"
        f"{body}\n\n"
        "{% endif %}"
    )


_SECTION_HEADINGS = {
    "currently": "## Currently",
    "notable": "## Notable",
    "journal": "## Journal",
    "brief": "## Briefly",
}

_CLOSING = (
    "Would you like to discuss the topics in the Weekly Thing further? "
    "Check out the [Weekly Thing on Reddit](https://www.reddit.com/r/weeklything/). 👋\n\n"
    "👨‍💻"
)


def _format_haiku_block(haiku: str) -> str:
    """The haiku close — the lead-in line, then the haiku itself
    (already bold + hard-broken upstream by `_base.format_haiku`).
    Returns "" if no haiku."""
    haiku = (haiku or "").strip()
    if not haiku:
        return ""
    return f"A haiku to leave you with…\n\n{haiku}"


def _section_part(
    section_name: str,
    sections: dict[str, str],
    features: list[tuple[str, str]],
    *,
    after_trailer: str = "",
) -> str:
    """Compose one parent section's part: heading + body + optional
    trailer (e.g. an email Liquid CTA block) + any features declared at
    the ``after_{section_name}`` position.

    Features get ``---``-joined to the section body (they're standalone
    H2 sections that promoted out of Journal, so they need a real
    divider). The trailer, by contrast, is glued on with just a blank
    line — Liquid CTA / thanks blocks carry their own ``---`` inside
    their conditional so an audience that doesn't match the conditional
    doesn't see an orphan divider.

    Returns "" if the parent section's body is empty — empty sections
    drop out cleanly. Trailer + after-features are tied to the section
    visually; if the section is gone, they go with it.
    """
    body = (sections.get(section_name) or "").strip()
    if not body:
        return ""
    heading = _SECTION_HEADINGS[section_name]
    text = f"{heading}\n\n{body}"
    trailer = (after_trailer or "").strip()
    if trailer:
        text = f"{text}\n\n{trailer}"
    chunks = [text]
    pos_label = f"after_{section_name}"
    for pos, feat_body in features:
        if pos == pos_label:
            chunks.append(feat_body.strip())
    return "\n\n---\n\n".join(chunks)


def _join_body_parts(parts: list[str]) -> str:
    """Drop empty parts; `---`-join the rest; ensure a trailing newline.
    The single composition primitive shared by all three formats."""
    parts = [p.rstrip() for p in parts if p and p.strip()]
    return "\n\n---\n\n".join(parts) + "\n"


def _compose_published_body(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    echoes: str,
    section_trailers: Optional[dict[str, str]] = None,
) -> str:
    """The published body shape every format (archive, email, audio)
    composes from. No block markers, no marker substitution — the
    body is emitted directly with each part already in its final form.
    Empty atoms / empty sections drop out naturally.

    ``section_trailers`` is the email-only Liquid-splice hook keyed by
    parent section name (``"notable"`` / ``"journal"`` / ``"brief"``).
    Archive and audio pass nothing here.
    """
    trailers = section_trailers or {}
    parts: list[str] = []

    intro = (atoms.get("intro") or "").strip()
    if intro:
        parts.append(intro)

    currently = (atoms.get("currently") or "").strip()
    if currently:
        parts.append(f"{_SECTION_HEADINGS['currently']}\n\n{currently}")

    cover = (atoms.get("cover") or "").strip()
    if cover:
        parts.append(cover)

    # Featured (Featured-category journal entries) before Notable.
    for pos, body in features:
        if pos == "before_notable":
            parts.append(body.strip())

    parts.append(_section_part("notable", sections, features, after_trailer=trailers.get("notable", "")))
    parts.append(_section_part("journal", sections, features, after_trailer=trailers.get("journal", "")))
    parts.append(_section_part("brief", sections, features, after_trailer=trailers.get("brief", "")))

    outro = (atoms.get("outro") or "").strip()
    if outro:
        parts.append(outro)

    # Haiku close + optional ## Echoes paragraph + Reddit-discuss + 👨‍💻
    haiku_block = _format_haiku_block(atoms.get("haiku", ""))
    echoes_text = (echoes or "").strip()
    echoes_block = f"## Echoes\n\n{echoes_text}" if echoes_text else ""
    tail_pieces = [p for p in (haiku_block, echoes_block, _CLOSING) if p]
    if tail_pieces:
        parts.append("\n\n".join(tail_pieces))

    return _join_body_parts(parts)


def render_email_body(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    issue_number: int,
    cta_atoms: Optional[dict[str, str]] = None,
    echoes: str = "",
    include_pixel: bool = True,
) -> str:
    """Build the buttondown.md body directly from structured inputs.

    CTA / thanks Liquid blocks are spliced in at hardcoded positions
    (see ``CTA_SLOT_POSITIONS`` below) — no marker round-trip. Slots
    whose atom is empty are simply omitted.

    Returns the full body: editor-mode comment + composed body +
    email-only tracking pixel.
    """
    cta_atoms = cta_atoms or {}

    # cta:1 → after Notable (free subscribers see CTA + Stripe buttons).
    # cta:2 → after Journal.
    # thanks:1 → after Briefly (premium subscribers see the thanks).
    trailers: dict[str, str] = {}
    cta_1 = (cta_atoms.get("cta:1") or "").strip()
    cta_2 = (cta_atoms.get("cta:2") or "").strip()
    thanks_1 = (cta_atoms.get("thanks:1") or "").strip()
    if cta_1:
        trailers["notable"] = supporter_block(cta_1, issue_number=issue_number)
    if cta_2:
        trailers["journal"] = supporter_block(cta_2, issue_number=issue_number)
    if thanks_1:
        trailers["brief"] = thanks_block(thanks_1)

    body = _compose_published_body(
        atoms=atoms, sections=sections, features=features,
        echoes=echoes, section_trailers=trailers,
    )

    body = _EDITOR_MODE_COMMENT + body
    if include_pixel:
        body = body.rstrip() + "\n\n" + pixel_block(issue_number) + "\n"
    return body


# ---------- archive (archive.md + links.json) ----------


def render_archive_body(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    echoes: str = "",
) -> str:
    """Build the archive.md body (post-frontmatter) directly from
    structured inputs. The website-shaped body: pure prose + headings
    + section content. No editor-mode preamble, no Liquid blocks, no
    CTA / thanks anything — supporter callouts are email-only.
    """
    return _compose_published_body(
        atoms=atoms, sections=sections, features=features, echoes=echoes,
        section_trailers=None,
    )


def render_archive_frontmatter(
    *, metadata: dict, body: str,
) -> tuple[dict, dict]:
    """Compose the archive front matter dict from ``metadata.json``
    and a freshly-rendered body. Also returns the structured link
    extraction (used for links.json downstream).

    Field order matches what's already committed in
    ``data/issues/{N}/archive.md`` so re-renders stay byte-stable.
    """
    from librarian_core.links import count_words, extract_domains, extract_links

    link_data = extract_links(body)
    all_curated = link_data["all_curated"]
    return {
        "buttondown_id": metadata.get("buttondown_id", "") or "",
        "number": int(metadata["number"]),
        "subject": metadata.get("subject", "") or "",
        "publish_date": metadata.get("publish_date", "") or "",
        "slug": str(metadata.get("slug", "") or ""),
        "description": metadata.get("description", "") or "",
        "image": metadata.get("image", "") or "",
        "absolute_url": metadata.get("absolute_url", "") or "",
        "domains": extract_domains(all_curated),
        "links": all_curated,
        "word_count": count_words(body),
    }, link_data


def render_archive_links_json(front_matter: dict, link_data: dict) -> dict:
    """Compose the ``links.json`` dict from the same inputs front matter
    used. Returned as a dict; caller serializes to JSON."""
    return {
        "notable_links": link_data["notable"],
        "briefly_links": link_data["briefly"],
        "domains": front_matter["domains"],
        "word_count": front_matter["word_count"],
    }


def render_archive(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    metadata: dict,
    echoes: str = "",
) -> tuple[str, dict]:
    """Render archive.md (full text including front matter) + links.json
    (as a dict). One-shot version of the three render_archive_* helpers
    for callers that want both outputs."""
    body = render_archive_body(
        atoms=atoms, sections=sections, features=features, echoes=echoes,
    )
    front_matter, link_data = render_archive_frontmatter(metadata=metadata, body=body)
    links_json = render_archive_links_json(front_matter, link_data)
    fm_str = yaml.dump(
        front_matter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    archive_md = f"---\n{fm_str}---\n{body}"
    return archive_md, links_json


# ---------- transcript (per-block .txt) ----------

# Per-block writes carry a slug derived from the block's first line,
# capped so S3 keys stay sane. Pure-text fallback when the slug
# derivation can't extract anything meaningful.
_MAX_SLUG_LEN = 40
_SLUG_FALLBACK = "block"


def _slugify(line: str) -> str:
    text = line.strip().lower()
    text = re.sub(r"[\"']", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if not text:
        return _SLUG_FALLBACK
    return text[:_MAX_SLUG_LEN].rstrip("-")


def _parse_archive_frontmatter(archive_md: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.+?)\n---\n(.*)$", archive_md, re.DOTALL)
    if not m:
        raise ValueError("archive.md is missing YAML front matter")
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, m.group(2)


def _import_audio_helpers():
    """Reach into the audio pipeline for the script-rendering primitives.
    pipeline/audio/ isn't a proper package — its files use
    ``from script import …`` so we add it to sys.path on demand."""
    repo = Path(__file__).resolve().parents[3]
    audio_dir = repo / "pipeline" / "audio"
    if str(audio_dir) not in sys.path:
        sys.path.insert(0, str(audio_dir))
    from script import body_to_audio_script  # noqa: E402
    from synthesize import split_into_blocks  # noqa: E402

    return body_to_audio_script, split_into_blocks


def render_audio_body(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    echoes: str = "",
) -> str:
    """Build the audio-purpose body directly from structured inputs.

    Same compose path as archive, with the cover atom dropped (cover
    image + caption + dateline + location are purely visual, never
    belong in TTS). The body-to-audio script transform handles the
    rest of the text-level shaping (number-to-word, URL stripping,
    section-heading cues, etc.).

    The ``strip_cover_blocks`` regex in ``pipeline/audio/script/common.py``
    still matters for the legacy backfill path that reads
    ``apps/site/archive/{N}.md`` directly. The workshop pipeline never
    needs it — the cover is gone before the body is composed.
    """
    audio_atoms = dict(atoms)
    audio_atoms["cover"] = ""
    return _compose_published_body(
        atoms=audio_atoms, sections=sections, features=features, echoes=echoes,
        section_trailers=None,
    )


def render_transcript_blocks(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    metadata: dict,
    echoes: str = "",
) -> list[tuple[str, str]]:
    """Build per-block transcript files from structured inputs.
    Independent of the archive body — never composes the cover or any
    other visual-only element. Returns ``[(filename, content), ...]``
    in editorial order; each filename is ``NNN-{slug}.txt``.

    Mirrors the inputs of ``render_archive`` and ``render_email`` so
    all three formats are siblings, not a chain.
    """
    body = render_audio_body(
        atoms=atoms, sections=sections, features=features, echoes=echoes,
    )
    # body_to_audio_script's frontmatter param wants the same keys
    # ``apps/site/archive/{N}.md`` exposes (number, subject,
    # publish_date) — synthesize one from metadata.
    fm = {
        "number": int(metadata.get("number", 0)),
        "subject": metadata.get("subject", "") or "",
        "publish_date": metadata.get("publish_date", "") or "",
    }
    body_to_audio_script, split_into_blocks = _import_audio_helpers()
    script = body_to_audio_script(body, fm)
    blocks = split_into_blocks(script)
    out: list[tuple[str, str]] = []
    for index, block in enumerate(blocks):
        first_line = block.splitlines()[0] if block else ""
        slug = _slugify(first_line)
        out.append((f"{index:03d}-{slug}.txt", block.rstrip() + "\n"))
    return out


def concat_transcript_for_review(
    blocks: list[tuple[str, str]],
    *,
    issue_number: Optional[int] = None,
) -> str:
    """Concatenate per-block transcript files into a single review
    document with visible segment markers between blocks.

    Each block is prefixed with a header line naming its source
    filename so Jamie can see exactly where the audio pipeline's
    utterance boundaries fall. The output is plain text — not consumed
    by the audio pipeline, just for review.
    """
    parts: list[str] = []
    if issue_number is not None:
        parts.append(
            f"Weekly Thing {issue_number} — full transcript ({len(blocks)} segments)"
        )
        parts.append("")
    for filename, content in blocks:
        parts.append(f"═══ {filename} ═══")
        parts.append("")
        parts.append(content.rstrip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


# =====================================================================
# Impure wrappers — read inputs from S3 + DB, call the pure renderers,
# write outputs to S3 + the local repo mirror. Called daily by
# update-draft so the four artifacts always reflect the current
# issue state.
# =====================================================================

_REPO_ROOT = Path(__file__).resolve().parents[3]
# The local repo mirror for rendered issue artifacts — the ship sequence
# commits these files (``publish website``), and Studio CI builds corpus +
# Weekly inputs from the committed tree. ``WORKSHOP_ISSUES_DIR`` overrides
# the location so test runs can never dirty the real ``data/issues/``
# (``tests/_stubs.install()`` always sets it to a temp dir).
ISSUES_LOCAL_DIR = (
    Path(os.environ["WORKSHOP_ISSUES_DIR"])
    if os.environ.get("WORKSHOP_ISSUES_DIR")
    else _REPO_ROOT / "data" / "issues"
)

# CTA / Thanks slot positions in the email. Hardcoded so Eddy doesn't
# need to declare placement editorially — Patty authors the copy
# (cta-1.md / cta-2.md / thanks-1.md) and the renderer splices it in
# at these fixed positions. Slots whose atom file is missing are
# simply skipped (no marker, no Liquid block, nothing).
CTA_SLOT_POSITIONS: dict[str, str] = {
    # "cta:1" splices after the Notable section (between Notable and
    # the next divider). "cta:2" splices after Journal. "thanks:1"
    # splices after Briefly. These are deliberate editorial calls —
    # change in coordination with the prompt-author flow.
    "cta:1": "after_notable",
    "cta:2": "after_journal",
    "thanks:1": "after_brief",
}


def _read_atom(issue_number: int, filename: str) -> str:
    """Read authored content for the issue; return its stripped text (or empty).
    Content lives in the DB store now (S3 is publishing-only)."""
    from . import content_store

    body = content_store.read_issue(issue_number, filename)
    return body.strip() if body else ""




def _read_atom_body_after_frontmatter(issue_number: int, filename: str) -> str:
    """Read an atom file and return its body, stripping any leading
    YAML front matter block (used by ``cta-N.md`` / ``thanks-N.md``
    which carry a ``kind: supporter`` front matter from compose-cta)."""
    raw = _read_atom(issue_number, filename)
    if not raw:
        return ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.DOTALL)
    if not m:
        return raw
    return m.group(2).lstrip("\n").strip()


def _load_metadata(issue_number: int, window: Optional[dict] = None) -> dict:
    """Load metadata.json with placeholder fallback fields so the
    daily renderers can run on day 1 of an issue (before compose-meta).
    Missing fields default to empty strings; ``number`` always present
    (from the active window if no metadata.json yet)."""
    raw = _read_atom(issue_number, "metadata.json")
    metadata: dict = {}
    if raw:
        try:
            metadata = json.loads(raw) or {}
        except (ValueError, TypeError):
            metadata = {}
    metadata.setdefault("number", issue_number)
    metadata.setdefault("subject", f"Weekly Thing {issue_number} — (pending)")
    metadata.setdefault("slug", str(issue_number))
    metadata.setdefault("description", "")
    metadata.setdefault("image",
                        f"https://files.thingelstad.com/weekly-thing/{issue_number}/cover.jpg")
    metadata.setdefault("absolute_url", "")
    metadata.setdefault("buttondown_id", "")
    if window:
        metadata.setdefault("publish_date", window.get("pub_date", "") + "T12:00:00Z" if window.get("pub_date") else "")
    else:
        metadata.setdefault("publish_date", "")
    # Publish-stamped fields live on the issue window (the newsletter's publish
    # record), not in the authored content row — overlay them so the archive
    # front matter + status gate see the real Buttondown id / URL.
    from . import db
    pub = window if (window and "buttondown_id" in window) else db.get_issue_window(issue_number)
    if pub:
        if pub.get("buttondown_id"):
            metadata["buttondown_id"] = pub["buttondown_id"]
        if pub.get("absolute_url"):
            metadata["absolute_url"] = pub["absolute_url"]
    return metadata


def _gather_inputs_for_issue(issue_number: int, *, window: Optional[dict] = None) -> dict:
    """Read every input the renderers need: atoms, section bodies (from
    DB rows), featured sections, metadata, cta atoms. Returns a dict
    the per-format wrappers consume."""
    from html import escape as _html_escape

    from ..jobs import _base, _cover, _currently
    from . import db, issue_items, issue_items_render

    if window is None:
        window = db.get_active_issue_window() or {"issue_number": issue_number}

    # Atoms (file-backed authored content).
    intro = _read_atom(issue_number, "intro.md")
    outro = _read_atom(issue_number, "outro.md")
    haiku_raw = _read_atom(issue_number, "haiku.md")
    cover_text = _cover.render(issue_number)
    if cover_text:
        # Cover block leads with the issue's cover image as a native <img>
        # tag (alt sourced from cover.json or vision-generated cache).
        cover_alt = _cover.alt(issue_number) or ""
        cover_img = (
            f'<img src="https://files.thingelstad.com/weekly-thing/{issue_number}/cover.jpg" '
            f'alt="{_html_escape(cover_alt, quote=True)}" />'
        )
        cover_text = f"{cover_img}\n\n{cover_text}"

    atoms = {
        "intro": intro,
        "currently": _currently.render(issue_number),
        "cover": cover_text,
        "outro": outro,
        "haiku": _base.format_haiku(haiku_raw) if haiku_raw else "",
    }

    # Sections from DB rows. Featured-promoted rows are excluded from
    # the parent section bodies (the sync layer flags them) and
    # rendered separately as standalone H2 sections.
    notable_rows = issue_items.list_items(issue_number, section="notable", include_promoted=False)
    brief_rows = issue_items.list_items(issue_number, section="brief", include_promoted=False)
    journal_rows = issue_items.list_items(issue_number, section="journal", include_promoted=False)
    sections = {
        "notable": issue_items_render.render_notable(notable_rows, issue_number),
        "journal": issue_items_render.render_journal(journal_rows),
        "brief": issue_items_render.render_brief(brief_rows),
    }

    featured_rows = [
        r for r in issue_items.list_items(issue_number, section="journal", include_promoted=True)
        if r.get("is_promoted")
    ]
    features = [
        (r.get("promoted_position") or "before_notable",
         issue_items_render.render_featured_section(r))
        for r in featured_rows
    ]

    # CTA / Thanks copy atoms (email-only; missing atoms = empty slot).
    cta_atoms = {
        "cta:1": _read_atom_body_after_frontmatter(issue_number, "cta-1.md"),
        "cta:2": _read_atom_body_after_frontmatter(issue_number, "cta-2.md"),
        "thanks:1": _read_atom_body_after_frontmatter(issue_number, "thanks-1.md"),
    }

    metadata = _load_metadata(issue_number, window)

    # Echoes (Thingy's archive note) — optional atom.
    echoes = _read_atom(issue_number, "echoes.md")

    return {
        "atoms": atoms,
        "sections": sections,
        "features": features,
        "metadata": metadata,
        "cta_atoms": cta_atoms,
        "echoes": echoes,
    }


def render_body_for_issue(
    issue_number: int, *, window: Optional[dict] = None,
) -> str:
    """The issue body rendered straight from current DB state — **no S3, no
    local writes, no artifacts**. The DB is the draft; this is how you read
    it. Consumers: the LLM jobs (compose-*, reorder, promotion-prep, Eddy's
    review) and the web preview."""
    inputs = _gather_inputs_for_issue(issue_number, window=window)
    return render_archive_body(
        atoms=inputs["atoms"],
        sections=inputs["sections"],
        features=inputs["features"],
        echoes=inputs["echoes"],
    )


def _splice_cta_into_sections(
    sections: dict[str, str], cta_atoms: dict[str, str],
) -> dict[str, str]:
    """Splice CTA / Thanks atom copy directly into the section bodies
    at their hardcoded positions. Returns a new sections dict with the
    CTA marker line appended to the parent section's body — the
    assembler then substitutes those markers with audience-aware
    Liquid blocks via the cta_atoms dict.

    Slots whose atom copy is empty or missing produce no marker (the
    splice is skipped entirely)."""
    spliced = dict(sections)
    for slot_label, position in CTA_SLOT_POSITIONS.items():
        if not cta_atoms.get(slot_label):
            continue
        # position is "after_notable" / "after_journal" / "after_brief"
        # — strip the "after_" prefix to get the parent section name.
        if not position.startswith("after_"):
            continue
        parent = position[len("after_"):]
        if parent not in spliced:
            continue
        marker = f"<!-- {slot_label.replace(':', ':')} -->"
        # Marker syntax expected by the assembler: ``<!-- cta:1 -->``.
        body = spliced[parent]
        if marker in body:
            continue
        spliced[parent] = (body.rstrip() + f"\n\n{marker}").strip()
    return spliced


# ---------- per-issue artifact writers ----------


def _write_pair_if_changed(
    *,
    local_path: Path,
    body: str,
    s3_write: "Callable[[], None]",
) -> bool:
    """Write ``body`` to ``local_path`` + S3 only when content actually
    differs. Returns True if a write happened, False if it was a no-op.

    The local mirror is treated as canonical for comparison: the
    renderers keep it in lock-step with S3 (write S3 first; local
    write only happens on S3 success), so if local matches body both
    sides are already up-to-date. Saves S3 PUTs on no-op refreshes
    where the underlying inputs (atoms / sections / metadata) haven't
    moved enough to change the output."""
    if local_path.exists():
        try:
            if local_path.read_text(encoding="utf-8") == body:
                return False
        except OSError:
            pass
    s3_write()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(body, encoding="utf-8")
    return True


def render_email_for_issue(issue_number: int, *, window: Optional[dict] = None) -> str:
    """Render the issue's buttondown.md from current DB + atom state
    and write it to S3 + the local repo mirror. Tolerates missing
    atoms — empty intro becomes an empty block, missing haiku skips
    the haiku close, missing cta atom skips that slot. Returns the
    rendered text."""
    from ..tools import s3 as _s3

    inputs = _gather_inputs_for_issue(issue_number, window=window)
    sections_with_markers = _splice_cta_into_sections(
        inputs["sections"], inputs["cta_atoms"],
    )
    body = render_email_body(
        atoms=inputs["atoms"],
        sections=sections_with_markers,
        features=inputs["features"],
        issue_number=issue_number,
        cta_atoms=inputs["cta_atoms"],
        echoes=inputs["echoes"],
    )
    # Local repo mirror for downstream consumers (ship sequence).
    local_path = ISSUES_LOCAL_DIR / str(issue_number) / "buttondown.md"
    _write_pair_if_changed(
        local_path=local_path,
        body=body,
        s3_write=lambda: _s3.write_issue_file(issue_number, "buttondown.md", body),
    )
    return body


def render_archive_for_issue(
    issue_number: int, *, window: Optional[dict] = None,
) -> tuple[str, dict]:
    """Render the issue's archive.md + links.json from current DB +
    atom state and write them to S3 + local repo mirror. Tolerates
    missing atoms / metadata via the placeholder fallback in
    ``_load_metadata``. Returns ``(archive_md, links_json)``."""
    from ..tools import s3 as _s3

    inputs = _gather_inputs_for_issue(issue_number, window=window)
    archive_md, links_json = render_archive(
        atoms=inputs["atoms"],
        sections=inputs["sections"],
        features=inputs["features"],
        metadata=inputs["metadata"],
        echoes=inputs["echoes"],
    )
    local_dir = ISSUES_LOCAL_DIR / str(issue_number)
    # archive.md — local + S3 in lock-step.
    _write_pair_if_changed(
        local_path=local_dir / "archive.md",
        body=archive_md,
        s3_write=lambda: _s3.write_issue_file(issue_number, "archive.md", archive_md),
    )
    # links.json — same pattern.
    links_body = json.dumps(links_json, indent=2) + "\n"
    _write_pair_if_changed(
        local_path=local_dir / "links.json",
        body=links_body,
        s3_write=lambda: _s3.write_issue_file(issue_number, "links.json", links_body),
    )
    # metadata.json — local mirror only (S3 owns the canonical copy via
    # the atoms/ writes; this is the ship-sequence's read source).
    metadata_body = json.dumps(inputs["metadata"], indent=2) + "\n"
    metadata_path = local_dir / "metadata.json"
    if not (metadata_path.exists() and metadata_path.read_text(encoding="utf-8") == metadata_body):
        local_dir.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(metadata_body, encoding="utf-8")
    return archive_md, links_json


def render_transcript_for_issue(
    issue_number: int, *, window: Optional[dict] = None,
) -> list[tuple[str, str]]:
    """Render the issue's transcript/*.txt files from current DB +
    atom state. Independent of render_archive_for_issue: builds an
    audio-purpose body directly via ``render_audio_body`` (cover atom
    dropped — never composed for audio) and runs the body-to-script
    transform on it. Writes per-block files to S3 + local repo
    mirror, wipes stale files from prior runs, and writes a
    concatenated ``transcript-full.txt`` review file. Returns the
    ``[(filename, content), ...]`` list."""
    from ..tools import s3 as _s3

    inputs = _gather_inputs_for_issue(issue_number, window=window)
    try:
        blocks = render_transcript_blocks(
            atoms=inputs["atoms"],
            sections=inputs["sections"],
            features=inputs["features"],
            metadata=inputs["metadata"],
            echoes=inputs["echoes"],
        )
    except Exception:  # noqa: BLE001 — degrade to no-op, but never silently
        # A crash in the pure transform is a real bug, not an empty issue.
        # Log it so render_all_for_issue's "transcript: False" is diagnosable
        # rather than indistinguishable from a legitimately empty issue.
        logger.exception("render_transcript_blocks failed for #%d", issue_number)
        return []
    if not blocks:
        return []

    # S3 mirror — wipe stale files from prior runs.
    new_names = {name for name, _ in blocks}
    try:
        existing = _s3.list_transcript_files(issue_number)
    except Exception:  # noqa: BLE001
        logger.warning(
            "render_transcript_for_issue: couldn't list S3 transcript files "
            "for #%d; skipping stale-file cleanup", issue_number,
        )
        existing = []
    for name in existing:
        if name not in new_names:
            try:
                _s3.delete_transcript_file(issue_number, name)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "render_transcript_for_issue: couldn't delete stale "
                    "transcript %s for #%d", name, issue_number,
                )

    # Local mirror.
    local_dir = ISSUES_LOCAL_DIR / str(issue_number) / "transcript"
    local_dir.mkdir(parents=True, exist_ok=True)
    for stale in local_dir.glob("*.txt"):
        if stale.name not in new_names:
            stale.unlink()

    for name, content in blocks:
        _write_pair_if_changed(
            local_path=local_dir / name,
            body=content,
            s3_write=lambda c=content, n=name: _s3.write_transcript_file(issue_number, n, c),
        )

    # Concatenated review file — single document with segment markers
    # so Jamie can scan the full transcript and see where the audio
    # pipeline's utterance breaks fall. Lives at the issue root (not
    # in the transcript/ subdir, which the audio pipeline scans). Not
    # consumed by anything downstream — review-only.
    review = concat_transcript_for_review(blocks, issue_number=issue_number)
    _write_pair_if_changed(
        local_path=ISSUES_LOCAL_DIR / str(issue_number) / "transcript-full.txt",
        body=review,
        s3_write=lambda: _s3.write_issue_file(issue_number, "transcript-full.txt", review),
    )
    return blocks


def render_all_for_issue(
    issue_number: int, *, window: Optional[dict] = None,
) -> dict:
    """Render archive + email + transcript in that order. Each writer
    is wrapped in try/except so a single failure doesn't cascade —
    callers (update-draft) want a partial success rather than a hard
    fail on the daily projection. Returns a dict of which artifacts
    succeeded for logging."""
    out: dict = {"archive": False, "email": False, "transcript": False, "errors": {}}
    try:
        render_archive_for_issue(issue_number, window=window)
        out["archive"] = True
    except Exception as exc:  # noqa: BLE001
        logger.exception("render_archive_for_issue failed for #%d", issue_number)
        out["errors"]["archive"] = f"{type(exc).__name__}: {exc}"
    try:
        render_email_for_issue(issue_number, window=window)
        out["email"] = True
    except Exception as exc:  # noqa: BLE001
        logger.exception("render_email_for_issue failed for #%d", issue_number)
        out["errors"]["email"] = f"{type(exc).__name__}: {exc}"
    try:
        blocks = render_transcript_for_issue(issue_number, window=window)
        out["transcript"] = bool(blocks)
        out["transcript_blocks"] = len(blocks)
    except Exception as exc:  # noqa: BLE001
        logger.exception("render_transcript_for_issue failed for #%d", issue_number)
        out["errors"]["transcript"] = f"{type(exc).__name__}: {exc}"
    return out
