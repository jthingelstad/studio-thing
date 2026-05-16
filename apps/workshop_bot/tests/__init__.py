"""Workshop bot test package."""

from __future__ import annotations

import logging
import os

# The suite intentionally exercises many degraded-runtime paths (Discord
# send failures, S3 failures, bad JSON fallbacks, HTTP fetch failures). Keep
# successful test runs readable while leaving an escape hatch for debugging.
if (os.environ.get("WORKSHOP_TEST_LOGS") or "").lower() not in {"1", "true", "yes"}:
    logging.disable(logging.CRITICAL)
