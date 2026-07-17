"""Render the issue's cover block text (caption + date/location) and alt text.

Reads the structured ``cover.json`` — ``{"caption": …, "location": …,
"timestamp": …, "alt": …}`` rendered as ``caption\n\ntimestamp  \nlocation``
(the shape the published issue uses, with a markdown hard break between
the timestamp and the location). Empty / missing / malformed → ``""``.
(The legacy verbatim ``cover.md`` iOS-Shortcut fallback died with the
Shortcuts pipeline.)

``alt(issue_number)`` returns the cover's alt text. ``cover.json.alt``
*is* the source of truth — if Jamie set one on the web cover form, that
wins. If the field is missing or empty, ``alt`` makes one vision call,
writes the result back into ``cover.json``, and returns it. The caption
is passed to the vision call so the generated alt doesn't duplicate the
text printed below the image.

This is *only* the text/alt for the cover; the renderers prepend the
cover image themselves, so all formats stay in sync via this one helper.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..tools import alt_text, content_store

logger = logging.getLogger("workshop.jobs.cover")

JSON_FILE = "cover.json"

# The cover image URL pattern (mirrors ``update_draft._COVER_IMAGE``). Defined
# here so ``alt(n)`` can fetch the bytes for the vision call from the same
# URL Jamie would publish.
COVER_IMAGE_URL = "https://files.thingelstad.com/weekly-thing/{n}/cover.jpg"


def render(issue_number: int) -> str:
    n = int(issue_number)
    raw = content_store.read_issue(n, JSON_FILE)
    if raw and raw.strip():
        return _render_json(raw, n) or ""
    return ""


def alt(issue_number: int) -> str:
    """Return the cover's alt text. ``cover.json.alt`` (operator-set or
    previously written by this function) wins; if missing/empty, makes
    one vision call, writes it back into ``cover.json`` on S3, and
    returns it. Returns ``""`` when ``cover.json`` is missing, when the
    image isn't yet on S3, or when the vision call fails (the hygiene
    review picks empty alts up)."""
    n = int(issue_number)
    data = _load_cover_json(n)
    if data is None:
        return ""
    manual = str(data.get("alt") or "").strip()
    if manual:
        return manual
    caption = str(data.get("caption") or "").strip() or None
    try:
        generated = alt_text.generate_alt(
            image_url=COVER_IMAGE_URL.format(n=n),
            context="",
            caption=caption,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover: alt generation failed for #%d: %s", n, exc)
        return ""
    if not generated:
        return ""
    # Persist the generated alt into the same cover.json so this becomes
    # a one-time vision call per issue — the next render reads it as the
    # manual path above. Best-effort: if the write fails, we still return
    # the alt for the current render and the next run will re-generate.
    data["alt"] = generated
    try:
        content_store.write_issue(n, JSON_FILE, json.dumps(data, indent=2))
        logger.info("cover: persisted generated alt to cover.json for #%d", n)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "cover: couldn't persist generated alt to cover.json for #%d: %s",
            n,
            exc,
        )
    return generated


def _load_cover_json(issue_number: int) -> Optional[dict]:
    raw = content_store.read_issue(int(issue_number), JSON_FILE)
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError, TypeError:
        return None
    return data if isinstance(data, dict) else None


def _render_json(text: str, issue_number: int) -> str:
    try:
        data = json.loads(text)
    except ValueError, TypeError:
        logger.warning(
            "cover.json for #%d isn't valid JSON; falling back to cover.md", issue_number
        )
        return ""
    if not isinstance(data, dict):
        logger.warning(
            "cover.json for #%d isn't a JSON object; falling back to cover.md", issue_number
        )
        return ""
    caption = str(data.get("caption") or "").strip()
    timestamp = str(data.get("timestamp") or "").strip()
    location = str(data.get("location") or "").strip()
    meta = "  \n".join(p for p in (timestamp, location) if p)  # date — hard break — location
    return "\n\n".join(p for p in (caption, meta) if p)
