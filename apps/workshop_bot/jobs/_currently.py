"""Render the issue's ``## Currently`` section from ``workshop.db``.

Source of truth is the ``currently_entries`` table (per-issue values
keyed by canonical type) joined with ``currently_types`` (the pool of
canonical labels). Entries render as ``**Label:** value`` lines, one
blank line between, in ``position`` order — the same shape the
published issue uses. Empty / no entries → ``""``, and the section
drops out of the published issue.

Shared by ``update-draft`` (the draft's ``currently`` block) and
``build-publish`` (the ``## Currently`` section in ``publish.md``) so
the two never diverge.

The legacy iOS-Shortcut path (``currently.json`` / ``currently.md`` in
S3) is retired. A one-time backfill in ``db._bootstrap_currently_from_s3``
seeds the in-flight issue from any leftover ``currently.json`` on first
boot; from there everything happens through the ``currently__*`` agent
tools, the ``/eddy currently`` slash subgroup, and Eddy's conversational
flow in ``#editorial``.
"""

from __future__ import annotations

import logging

from ..tools import db

logger = logging.getLogger("workshop.jobs.currently")


def render(issue_number: int) -> str:
    n = int(issue_number)
    entries = db.currently_get_entries(n)
    lines: list[str] = []
    for row in entries:
        label = str(row.get("type_label") or "").strip().rstrip(":").strip()
        value = str(row.get("value") or "").strip()
        if label and value:
            lines.append(f"**{label}:** {value}")
    return "\n\n".join(lines)
