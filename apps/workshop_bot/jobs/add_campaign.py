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
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{0,63}$")


def _as_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def run(
    ctx: "_base.JobContext",
    *,
    name: str,
    ref: str,
    url=None,
    platform=None,
    cost=None,
    copy=None,
) -> "_base.JobResult":
    name = (name or "").strip()
    ref = (ref or "").strip()
    url = (str(url).strip() or None) if url is not None else None
    platform = (str(platform).strip() or None) if platform is not None else None
    copy = (str(copy).strip() or None) if copy is not None else None
    if not name:
        return _base.JobResult(False, "❌ campaign name is required.")
    if not _REF_RE.match(ref):
        return _base.JobResult(
            False,
            f"❌ ref tag {ref!r} must match the ?ref= value exactly — letters/digits plus `.`/`_`/`-`/`~`/`:`, "
            "≤64 chars (e.g. `DenseDiscovery-388`). Case is preserved.",
        )
    cost_f = _as_float(cost)
    # Soft-warn if another live campaign is already using this ref — two
    # campaigns sharing a `?ref=` value will read the same Tinylytics /
    # Buttondown numbers, so `daily-metrics` can't tell them apart. Not
    # blocking (a fresh placement under a new name might legitimately
    # reuse a ref), just surfaced in the ack.
    ref_collision = next(
        (c for c in db.active_campaigns() if c.get("ref") == ref and c.get("name") != name),
        None,
    )
    created = db.insert_campaign(
        name=name, ref=ref, url=url, platform=platform, cost=cost_f, copy=copy,
    )
    if not created:
        existing = db.get_campaign(name) or {}
        return _base.JobResult(
            False,
            f"⚠️ a campaign named `{name}` already exists (ref `{existing.get('ref')}`, "
            f"status `{existing.get('status')}`). Pick a different name.",
        )
    bits = [f"✅ Campaign **{name}** registered (ref `{ref}`, status `live`)."]
    if ref_collision is not None:
        bits.append(
            f"⚠️ ref `{ref}` is already live on `{ref_collision['name']}` — "
            "they'll share metrics. Use a different ref unless that's intentional."
        )
    if platform:
        bits.append(f"Platform: {platform}.")
    if url:
        bits.append("URL recorded.")
    if cost_f is not None:
        bits.append(f"Cost: ${cost_f:.2f}.")
    if copy:
        bits.append("Copy recorded.")
    else:
        bits.append("No copy yet — add it with `/marky campaign copy`.")
    bits.append("`daily-metrics` will poll it each run; `/marky campaign report` for a summary.")
    return _base.JobResult(True, " ".join(bits), data={"name": name, "ref": ref, "has_copy": bool(copy)})
