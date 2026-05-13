"""Render the issue's cover block text (caption + date/location) and alt text.

Prefers a structured ``cover.json`` — ``{"caption": …, "location": …,
"timestamp": …, "alt": …}`` rendered as ``caption\n\ntimestamp  \nlocation``
(the shape the published issue uses, with a markdown hard break between
the timestamp and the location). Falls back to a verbatim ``cover.md``
(the legacy iOS-Shortcut form). Empty / missing either way → ``""``.

``alt(issue_number)`` returns the cover's alt text: ``cover.json.alt`` if
the operator set one (manual override wins), else a vision-generated alt
(cached in ``image_alt_cache`` under key ``cover-{N}``), else ``""``. The
caption is passed to the vision call so the generated alt doesn't
duplicate the text printed directly below the image.

This is *only* the text/alt for the cover; both ``update-draft`` and
``build-publish`` prepend the cover image themselves, so the two stay in
sync via this one helper.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..tools import alt_text, s3

logger = logging.getLogger("workshop.jobs.cover")

JSON_FILE = "cover.json"
MD_FILE = "cover.md"

# The cover image URL pattern (mirrors ``update_draft._COVER_IMAGE``). Defined
# here so ``alt(n)`` can fetch the bytes for the vision call from the same
# URL Jamie would publish.
COVER_IMAGE_URL = "https://files.thingelstad.com/weekly-thing/{n}/cover.jpg"


def render(issue_number: int) -> str:
    n = int(issue_number)
    raw = s3.read_issue_file(n, JSON_FILE)
    if raw.get("found") and isinstance(raw.get("text"), str) and raw["text"].strip():
        rendered = _render_json(raw["text"], n)
        if rendered:
            return rendered
        # malformed/empty JSON → fall through to the legacy markdown form
    md = s3.read_issue_file(n, MD_FILE)
    text = md.get("text") if md.get("found") else None
    return text.strip() if isinstance(text, str) else ""


def alt(issue_number: int) -> str:
    """Return the cover's alt text — operator override (``cover.json.alt``)
    wins, else vision-generated (cached), else ``""``. The caption is
    passed to the vision call so a generated alt doesn't repeat it."""
    n = int(issue_number)
    data = _load_cover_json(n)
    manual = ""
    caption: Optional[str] = None
    if data is not None:
        manual = str(data.get("alt") or "").strip()
        caption = str(data.get("caption") or "").strip() or None
    key = f"cover-{n}"
    if manual:
        # Persist the manual override so subsequent runs / the hygiene
        # review can read it from the same cache journal images use.
        try:
            alt_text.set_manual_alt(image_key=key, alt=manual)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cover: couldn't cache manual alt for #%d: %s", n, exc)
        return manual
    try:
        return alt_text.get_or_generate_alt(
            image_key=key,
            image_url=COVER_IMAGE_URL.format(n=n),
            context="",
            caption=caption,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover: alt generation failed for #%d: %s", n, exc)
        return ""


def _load_cover_json(issue_number: int) -> Optional[dict]:
    raw = s3.read_issue_file(int(issue_number), JSON_FILE)
    if not raw.get("found") or not isinstance(raw.get("text"), str) or not raw["text"].strip():
        return None
    try:
        data = json.loads(raw["text"])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _render_json(text: str, issue_number: int) -> str:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        logger.warning("cover.json for #%d isn't valid JSON; falling back to cover.md", issue_number)
        return ""
    if not isinstance(data, dict):
        logger.warning("cover.json for #%d isn't a JSON object; falling back to cover.md", issue_number)
        return ""
    caption = str(data.get("caption") or "").strip()
    timestamp = str(data.get("timestamp") or "").strip()
    location = str(data.get("location") or "").strip()
    meta = "  \n".join(p for p in (timestamp, location) if p)  # date — hard break — location
    return "\n\n".join(p for p in (caption, meta) if p)
