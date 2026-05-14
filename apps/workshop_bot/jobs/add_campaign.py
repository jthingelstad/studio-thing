"""``add-campaign`` — register an ad campaign for Marky to track.

Writes a row into the ``campaigns`` SQLite table. Pure DB write, no LLM,
no Discord post beyond the invoker ack. ``daily-metrics`` then polls the
campaign and appends a ``campaign_metrics`` row each run.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.add_campaign")

NAME = "add-campaign"

# Case-preserving: Tinylytics records the ?ref= value verbatim and matches it
# case-sensitively, so a ref set up as `DenseDiscovery-388` must be stored
# exactly that way or daily-metrics polls the wrong key and sees 0 traffic.
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,63}$")


def _as_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def run(
    ctx: "_base.JobContext",
    *,
    name: str,
    ref: str,
    expected_signups=None,
    expected_traffic=None,
    copy=None,
) -> "_base.JobResult":
    name = (name or "").strip()
    ref = (ref or "").strip()
    copy = (str(copy).strip() or None) if copy is not None else None
    if not name:
        return _base.JobResult(False, "❌ campaign name is required.")
    if not _REF_RE.match(ref):
        return _base.JobResult(
            False,
            f"❌ ref tag {ref!r} must match the ?ref= value exactly — letters/digits plus `.`/`_`/`-`/`~`, "
            "≤64 chars (e.g. `DenseDiscovery-388`). Case is preserved.",
        )
    es, et = _as_int(expected_signups), _as_int(expected_traffic)
    created = db.insert_campaign(name=name, ref=ref, expected_signups=es, expected_traffic=et, copy=copy)
    if not created:
        existing = db.get_campaign(name) or {}
        return _base.JobResult(
            False,
            f"⚠️ a campaign named `{name}` already exists (ref `{existing.get('ref')}`, "
            f"status `{existing.get('status')}`). Pick a different name.",
        )
    bits = [f"✅ Campaign **{name}** registered (ref `{ref}`, status `live`)."]
    if es is not None:
        bits.append(f"Expected signups: {es}.")
    if et is not None:
        bits.append(f"Expected traffic: {et}.")
    if copy:
        bits.append("Copy recorded.")
    else:
        bits.append("No copy yet — add it with `/workshop campaign copy`.")
    bits.append("`daily-metrics` will poll it each run; `/workshop campaign report` for a summary.")
    return _base.JobResult(True, " ".join(bits), data={"name": name, "ref": ref, "has_copy": bool(copy)})
