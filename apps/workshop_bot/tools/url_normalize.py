"""URL normalisation for cross-source dedup.

The :func:`dedup_key` form is the canonical comparison key for every
"have we seen this URL?" question in workshop_bot — both the in-scan
classifier in ``jobs/pinboard_scan.py`` and the DB-layer helpers in
``tools/db.py`` (``pinboard_popular_seen``, ``popular_seen_sightings``,
``pinboard_research_done``) normalise URLs through this function on
write and read, so cross-scan dedup tolerates the cosmetic URL drift
upstream feeds throw at us.

Normalisation rules:

- Lowercase the host.
- Strip a trailing ``/`` from the path (except on bare-domain URLs).
- Drop tracking query params (``utm_*``, ``fbclid``, ``gclid``,
  ``mc_cid``, ``mc_eid``, ``ref``, ``ref_src``).
- **Drop the fragment.** A fragment like ``#fnref1`` or ``#section-2``
  is a UI anchor inside the same resource — two URLs that differ only
  by fragment are the same article. (Was previously preserved; the
  ``homewithinnowhere.com/posts/.../one-line.html`` duplicate on
  2026-05-14 was the regression that flipped this rule.)

Two feeds that surface the same article shouldn't be treated as
distinct because one ships ``?utm_source=hn`` or because one
hand-linked the URL with a footnote anchor.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query-param names dropped from the dedup key. Conservative — these are
# *unambiguously* tracking params; anything we're not sure about
# (e.g. `id=`, `q=`) stays in the key. Add to this set when a new
# tracker shows up cluttering the queue.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}


def _strip_tracking(query: str) -> str:
    if not query:
        return ""
    kept: list[tuple[str, str]] = []
    for k, v in parse_qsl(query, keep_blank_values=True):
        lk = k.lower()
        if lk in _TRACKING_PARAM_EXACT:
            continue
        if any(lk.startswith(p) for p in _TRACKING_PARAM_PREFIXES):
            continue
        kept.append((k, v))
    if not kept:
        return ""
    return urlencode(kept, doseq=False)


def dedup_key(url: str) -> str:
    """Normalised in-memory comparison form for ``url``. Returns ``""``
    if the input is empty or unparseable."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    host = parts.netloc.lower()
    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = _strip_tracking(parts.query)
    # Fragment dropped — see module docstring.
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))
