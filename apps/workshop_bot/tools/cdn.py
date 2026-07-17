"""CloudFront cache invalidation for the public assets bucket.

``files.thingelstad.com`` is fronted by a CloudFront distribution, so an
object we overwrite (e.g. ``draft.html`` daily) stays cached until it's
either evicted or invalidated. ``invalidate(paths)`` issues a CloudFront
invalidation for the given paths — best-effort: it never raises, and it
no-ops (with a log line) if no distribution id is configured. The
distribution id comes from ``WEEKLY_THING_CDN_DISTRIBUTION_ID``
(defaulting to the production one). HTML previews are also uploaded with
``Cache-Control: no-cache``, so even between invalidations a browser
revalidates rather than serving stale.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("workshop.cdn")

DEFAULT_DISTRIBUTION_ID = "E3AEA6KRKI2B7E"


def distribution_id() -> str:
    """The CloudFront distribution to invalidate. Unset → the prod default;
    set to empty (``WEEKLY_THING_CDN_DISTRIBUTION_ID=``) → disabled
    (returns "" → ``invalidate`` no-ops)."""
    raw = os.environ.get("WEEKLY_THING_CDN_DISTRIBUTION_ID")
    if raw is None:
        return DEFAULT_DISTRIBUTION_ID
    return raw.strip()


def invalidate(paths: list[str]) -> Optional[str]:
    """Issue a CloudFront invalidation for ``paths`` (each is forced to
    start with ``/``). Returns the invalidation id, or None if skipped /
    failed. Never raises — invalidation is best-effort."""
    dist = distribution_id()
    if not dist:
        logger.debug("cdn: no distribution id configured; skipping invalidation of %s", paths)
        return None
    items = [p if p.startswith("/") else f"/{p}" for p in paths if p]
    if not items:
        return None
    try:
        import boto3

        client = boto3.client("cloudfront")
        resp = client.create_invalidation(
            DistributionId=dist,
            InvalidationBatch={
                "Paths": {"Quantity": len(items), "Items": items},
                "CallerReference": f"workshop-{int(time.time() * 1000)}",
            },
        )
        inv_id = (resp.get("Invalidation") or {}).get("Id")
        logger.info("cdn: invalidated %s on %s (id=%s)", items, dist, inv_id)
        return inv_id
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("cdn: invalidation of %s skipped (%s)", items, exc)
        return None
