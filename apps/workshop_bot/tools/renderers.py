"""Pure renderers for the three issue artifact formats.

The three formats — Buttondown email body, website archive, and audio
transcript — each consume the same structured inputs (atoms + section
bodies + features + metadata) and emit their own bytes directly. No
shared intermediate text body that one format mutates and another
strips. Each renderer can diverge freely without coupling to the other
two.

This module is the public API the daily-render pipeline calls. The
existing job wrappers (``build_publish``, ``compose_archive``,
``compose_transcript``) delegate to it during the migration so byte
parity is preserved while we shift consumers.

Conventions:

- All functions are pure: no S3 reads, no DB lookups, no file writes.
  Inputs are dicts and strings; outputs are strings or tuples thereof.
- ``atoms`` keys: ``intro``, ``currently``, ``cover``, ``outro``,
  ``haiku``. Missing keys default to empty.
- ``sections`` keys: ``notable``, ``journal``, ``brief``. Rendered
  section bodies — may carry inline ``<!-- cta:N -->`` /
  ``<!-- thanks:N -->`` markers in the email path.
- ``features``: ``[(promoted_position, '## Heading\\n\\nbody'), ...]``
  with positions like ``"after_notable"`` / ``"before_notable"`` /
  ``"after_journal"`` / etc.
- ``cta_atoms``: ``{"cta:1": "supporter ask copy", "thanks:1": "..."}``
  — already-loaded copy strings keyed by ``kind:slot_n``. Slots whose
  copy is empty or missing leave the marker in place (build_publish's
  current behavior; later steps may strip empty slots cleanly).

Email-specific Liquid blocks stay inside ``render_email_body``;
website-specific YAML front matter stays inside ``render_archive``;
transcript-specific block-split logic stays inside
``render_transcript_blocks``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from . import issue_assembly


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


def supporter_block(cta_body: str) -> str:
    """Audience-aware Liquid wrapper for a non-member CTA.

    ``regular`` subscribers see the CTA + two Stripe payment-link
    buttons (``$4 monthly`` / ``$40 yearly``). Anyone else without a
    premium membership sees the CTA + ``{{ subscribe_form }}``.
    Premium members fall through to nothing.
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


def thanks_block(thanks_body: str) -> str:
    """Audience-aware Liquid wrapper for a premium-only thank-you.

    Premium subscribers see the thanks; everyone else falls through
    to nothing."""
    body = thanks_body.strip()
    return (
        "{% if subscriber.subscriber_type == 'premium' %}\n\n"
        f"{body}\n\n"
        "{% endif %}"
    )


def _build_marker_substitution(cta_atoms: dict[str, str]):
    """Build the ``MARKER_RE.sub`` callback that replaces inline
    ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers with the
    audience-aware Liquid block sourced from ``cta_atoms``.

    Empty-copy slots leave the marker in place — caller is expected to
    have validated copy presence pre-render."""

    def _replace(match):
        kind = match.group(1)
        slot_n = int(match.group(2))
        key = f"{kind}:{slot_n}"
        copy = (cta_atoms.get(key) or "").strip()
        if not copy:
            return match.group(0)
        return supporter_block(copy) if kind == "cta" else thanks_block(copy)

    return _replace


def render_email_body(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    issue_number: int,
    cta_atoms: Optional[dict[str, str]] = None,
    closer: str = "",
    include_pixel: bool = True,
) -> str:
    """Build the buttondown.md body from structured inputs.

    Returns the full body string: editor-mode comment + assembled body
    (no block markers, with CTA / thanks markers substituted to Liquid)
    + email-only tracking pixel.
    """
    marker_substitution = (
        _build_marker_substitution(cta_atoms) if cta_atoms else None
    )
    return issue_assembly.assemble_publish(
        atoms=atoms,
        section_bodies=sections,
        features=features,
        issue_number=issue_number,
        pixel_block=pixel_block(issue_number) if include_pixel else None,
        marker_substitution=marker_substitution,
        closer=closer,
    )


# ---------- email preview (buttondown.html input — Liquid stripped) ----------


def render_email_preview(email_body: str) -> str:
    """Best-effort Liquid strip for the ``buttondown.html`` preview.

    Renders as a *regular* (free-subscriber) view: keeps the
    supporter-CTA text + Stripe buttons, hides the premium-only thanks,
    drops the editor-mode comment and the email-only pixel, strips
    leftover Liquid tags. The delivered email keeps the full Liquid;
    this only shapes the preview render at
    ``https://files.thingelstad.com/weekly-thing/{N}/buttondown.html``.
    """
    t = re.sub(r"<!--\s*buttondown-editor-mode:[^>]*-->\s*", "", email_body, flags=re.IGNORECASE)
    t = re.sub(
        r"\{%\s*if\s+medium\s*==\s*'email'\s*%\}.*?\{%\s*endif\s*%\}",
        "", t, flags=re.DOTALL | re.IGNORECASE,
    )
    t = re.sub(
        r"\{%\s*if\s+subscriber\.subscriber_type\s*==\s*'regular'\s*%\}(.*?)"
        r"\{%\s*elif\s+subscriber\.subscriber_type\s*!=\s*'premium'\s*%\}.*?"
        r"\{%\s*endif\s*%\}",
        lambda m: m.group(1),
        t,
        flags=re.DOTALL,
    )
    t = re.sub(
        r"\{%\s*if\s+subscriber\.subscriber_type\s*==\s*'premium'\s*%\}.*?\{%\s*endif\s*%\}",
        "", t, flags=re.DOTALL,
    )
    t = re.sub(r"\{%[^%]*%\}", "", t)
    t = re.sub(r"\{\{[^}]*\}\}", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


# ---------- archive (archive.md + links.json) ----------

# Strip the inline cta/thanks markers entirely on the way to archive
# (the website doesn't host supporter callouts inline). Matches
# compose_archive._strip_membership_markers.
_ARCHIVE_MARKER_RE = re.compile(r"\n?<!--\s*(?:cta|thanks):\d+\s*-->\n?")


def _strip_archive_markers(body: str) -> str:
    cleaned = _ARCHIVE_MARKER_RE.sub("\n", body)
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def render_archive_body(
    *,
    atoms: dict[str, str],
    sections: dict[str, str],
    features: list[tuple[str, str]],
    closer: str = "",
) -> str:
    """Build the archive.md body (post-frontmatter) from structured
    inputs. No block markers, no editor-mode comment, no CTA / thanks
    markers — the website body is pure prose + headings + section
    content."""
    body = issue_assembly.assemble_final(
        atoms=atoms, section_bodies=sections, features=features, closer=closer,
    )
    body = issue_assembly._strip_block_markers(body)
    body = _strip_archive_markers(body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip() + "\n"


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
    closer: str = "",
) -> tuple[str, dict]:
    """Render archive.md (full text including front matter) + links.json
    (as a dict). One-shot version of the three render_archive_* helpers
    for callers that want both outputs."""
    body = render_archive_body(
        atoms=atoms, sections=sections, features=features, closer=closer,
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


def render_transcript_blocks(archive_md: str) -> list[tuple[str, str]]:
    """Split the archive body into per-block transcript files, named
    ``NNN-{slug}.txt`` in editorial order. The audio pipeline TTSes
    each block as its own utterance so breath placement falls at
    editorial boundaries.

    Returns a list of ``(filename, content)`` tuples. Each ``content``
    ends with a trailing newline (matches the on-disk shape).

    Raises ``ValueError`` if ``archive_md`` is missing front matter
    (the body-to-audio transform needs the metadata)."""
    fm, body = _parse_archive_frontmatter(archive_md)
    body_to_audio_script, split_into_blocks = _import_audio_helpers()
    script = body_to_audio_script(body, fm)
    blocks = split_into_blocks(script)
    out: list[tuple[str, str]] = []
    for index, block in enumerate(blocks):
        first_line = block.splitlines()[0] if block else ""
        slug = _slugify(first_line)
        out.append((f"{index:03d}-{slug}.txt", block.rstrip() + "\n"))
    return out
