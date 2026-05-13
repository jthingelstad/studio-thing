"""Render the issue's cover block text (caption + date/location).

Prefers a structured ``cover.json`` — ``{"caption": …, "location": …,
"timestamp": …}`` rendered as ``caption\n\ntimestamp  \nlocation`` (the
shape the published issue uses, with a markdown hard break between the
timestamp and the location). Falls back to a verbatim ``cover.md`` (the
legacy iOS-Shortcut form). Empty / missing either way → ``""``.

This is *only* the text that goes below the cover image; both
``update-draft`` and ``build-publish`` prepend ``![](.../cover.jpg)``
themselves, so the two stay in sync via this one helper.
"""

from __future__ import annotations

import json
import logging

from ..tools import s3

logger = logging.getLogger("workshop.jobs.cover")

JSON_FILE = "cover.json"
MD_FILE = "cover.md"


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
