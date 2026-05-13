"""Render the issue's ``## Currently`` section from the workspace.

Prefers a structured ``currently.json`` — an object ``{"Label": "value",
…}`` rendered as ``**Label:** value`` lines, one blank line between (the
shape the published issue uses). Falls back to a verbatim ``currently.md``
(the legacy iOS-Shortcut form). Empty / missing either way → ``""``, and
the section drops out of the published issue.

Shared by ``update-draft`` (the draft's ``currently`` block) and
``build-publish`` (the ``## Currently`` section in ``publish.md``) so the
two never diverge.
"""

from __future__ import annotations

import json
import logging

from ..tools import s3

logger = logging.getLogger("workshop.jobs.currently")

JSON_FILE = "currently.json"
MD_FILE = "currently.md"


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
        logger.warning("currently.json for #%d isn't valid JSON; falling back to currently.md", issue_number)
        return ""
    if not isinstance(data, dict):
        logger.warning("currently.json for #%d isn't a JSON object; falling back to currently.md", issue_number)
        return ""
    lines: list[str] = []
    for label, value in data.items():
        label = str(label).strip().rstrip(":").strip()
        value = str(value).strip()
        if label and value:
            lines.append(f"**{label}:** {value}")
    return "\n\n".join(lines)
