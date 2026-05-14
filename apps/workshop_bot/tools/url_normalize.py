"""URL normalisation for cross-source dedup.

The :func:`dedup_key` form is **in-memory only** — both the dedup table
(``pinboard_popular_seen``) and the sightings log (``popular_seen_sightings``)
store the *original* URL each feed handed us, so a future tighter or
looser normalisation rule doesn't invalidate stored rows. The key is
just a comparison form: lowercase the host, strip a trailing ``/``
(except on bare-domain URLs), and drop tracking query params that
different feeds add as referer fingerprints (utm_*, fbclid, etc.).

Two feeds that surface the same article shouldn't be treated as
distinct because one ships ``?utm_source=hn``.
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
    return urlunsplit((parts.scheme.lower(), host, path, query, parts.fragment))
