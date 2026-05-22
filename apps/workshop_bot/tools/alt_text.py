"""Vision-generated alt text for journal and cover images.

Owns the cache + the Claude vision call. Two surfaces:

  ``get_or_generate_alt(*, image_key, image_url, context, caption=None)``
      Returns the alt text for one image — cached forever once generated,
      so a daily ``update-draft`` re-run is free for images we've already
      seen. On a miss: fetches the (already-resized) image bytes from
      ``image_url``, asks Sonnet for a tight one-line description, persists
      on success. Failure / cap-exhaustion → returns ``""`` (the hygiene
      review picks up empty alts as a flag).

  ``begin_run()``
      Resets the per-run vision-call cap. Call at the start of each
      ``update-draft`` so a single run can't fan out to dozens of vision
      calls — the cap is configurable via ``WORKSHOP_ALT_VISION_CAP``
      (default 15). The remaining images fill on subsequent runs.

``image_key`` is the cache key — content-addressed: the rehosted journal
filename (``428e3db12e.jpg`` — micro.blog uploads are already content-hashed
basenames) for journal images, ``cover-{N}`` for an issue's cover. Same
image used in two issues → same key → one vision call total.

Prompt guardrails: ≤120 chars, factual, no "photo of"/"image of"/"picture
of" preamble, no emoji, no quotes / ampersands / angle brackets (so it's
safe to write straight into an ``<img alt="...">`` attribute without
worrying about breaking the tag — defense in depth on top of the
``html.escape`` the caller does).
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Optional

import requests

from . import db
from .llm import anthropic_client

logger = logging.getLogger("workshop.alt_text")

_DEFAULT_CAP = 15
_FETCH_TIMEOUT = 20.0
_FETCH_MAX_BYTES = 6 * 1024 * 1024     # 6 MB — rehosted images are well under
_VISION_MAX_TOKENS = 200
_VISION_MODEL_KEY = "sonnet"
_UA = "WeeklyThing-WorkshopBot/1.0"

# Module-level counter — reset by begin_run(); workshop_bot is single-process
# and update-draft's _gather_fills runs serially in one thread, so no lock.
_calls_remaining = _DEFAULT_CAP

_PROMPT_BASE = (
    "Generate alt text for the attached image, for a screen-reader user "
    "who cannot see it.\n\n"
    "Constraints:\n"
    "- 120 characters or fewer.\n"
    "- Factual and concrete — describe what's actually visible (the "
    "subject, setting, action).\n"
    "- No preamble like \"photo of\", \"image of\", \"picture of\", \"a "
    "view of\" — start with the subject itself.\n"
    "- One single line. No emoji. No quote marks, ampersands, or angle "
    "brackets (the text goes straight into an HTML alt attribute).\n"
    "- Skip people's identities you can't be confident about; describe "
    "what they're doing or wearing instead.\n"
)

_RESPONSE_HINT = (
    "Respond with just the alt text on one line — no leading/trailing "
    "quotes, no \"alt:\" prefix, no explanation."
)


def _cap() -> int:
    raw = os.environ.get("WORKSHOP_ALT_VISION_CAP")
    if raw is None:
        return _DEFAULT_CAP
    try:
        v = int(raw)
        return v if v >= 0 else _DEFAULT_CAP
    except ValueError:
        return _DEFAULT_CAP


def begin_run() -> None:
    """Reset the per-run vision-call counter. Call once at the top of
    ``update-draft``'s ``_gather_fills``."""
    global _calls_remaining
    _calls_remaining = _cap()


def calls_remaining() -> int:
    return _calls_remaining


def _fetch_image_bytes(url: str) -> Optional[tuple[bytes, str]]:
    """Download the image; return ``(bytes, media_type)`` or ``None`` on
    failure. Treats non-image responses as failure."""
    try:
        resp = requests.get(url, timeout=_FETCH_TIMEOUT, headers={"User-Agent": _UA}, stream=True)
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if not ctype.startswith("image/"):
            logger.warning("alt_text: %s is not an image (%s)", url, ctype)
            return None
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > _FETCH_MAX_BYTES:
                logger.warning("alt_text: %s exceeds %d bytes; aborting", url, _FETCH_MAX_BYTES)
                return None
            chunks.append(chunk)
        return b"".join(chunks), ctype
    except Exception as exc:  # noqa: BLE001
        logger.warning("alt_text: fetch %s failed: %s", url, exc)
        return None


def _build_messages(*, image_b64: str, media_type: str, context: str, caption: Optional[str]) -> list[dict]:
    """Compose the vision-call user content blocks."""
    text_parts = [_PROMPT_BASE]
    if caption and caption.strip():
        text_parts.append(
            "Do NOT repeat this caption (it appears as text near the "
            f"image, so a screen-reader user already gets it): {caption.strip()!r}"
        )
    if context and context.strip():
        # Cap context at ~1500 chars so we don't ship the whole post.
        ctx = context.strip()
        if len(ctx) > 1500:
            ctx = ctx[:1500].rsplit(" ", 1)[0] + "…"
        text_parts.append("For background, here is the prose around the image:\n\n" + ctx)
    text_parts.append(_RESPONSE_HINT)
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                },
                {"type": "text", "text": "\n\n".join(text_parts)},
            ],
        }
    ]


def _clean_alt(raw: str) -> str:
    """Trim whitespace/quotes/angle brackets/ampersands; collapse to one
    line; cap at 200 chars (the prompt asks for ≤120; this is the hard
    backstop)."""
    if not raw:
        return ""
    s = raw.strip()
    # If the model wrapped the alt in quotes, strip them.
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    # Strip any "Alt:" / "Alt text:" prefix the model added despite the hint.
    s = re.sub(r"^(alt(\s+text)?\s*:\s*)", "", s, flags=re.IGNORECASE)
    # Strip the chars that would break the attribute (do this before the
    # whitespace collapse so the " and " replacement doesn't leave double
    # spaces).
    s = s.replace('"', "").replace("&", " and ").replace("<", "").replace(">", "")
    # One line, single-spaced.
    s = " ".join(s.split())
    if len(s) > 200:
        s = s[:200].rsplit(" ", 1)[0]
    return s.strip()


def _generate_via_vision(*, image_url: str, context: str, caption: Optional[str]) -> str:
    """Make one vision call; return the cleaned alt or ``""`` on any failure."""
    fetched = _fetch_image_bytes(image_url)
    if fetched is None:
        return ""
    body, media_type = fetched
    b64 = base64.b64encode(body).decode("ascii")
    try:
        client = anthropic_client.client()
        resp = client.messages.create(
            model=anthropic_client.MODELS[_VISION_MODEL_KEY],
            max_tokens=_VISION_MAX_TOKENS,
            messages=_build_messages(
                image_b64=b64, media_type=media_type, context=context, caption=caption,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("alt_text: vision call failed for %s: %s", image_url, exc)
        return ""
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    cleaned = _clean_alt(text)
    if not cleaned:
        logger.warning("alt_text: model returned empty/unusable alt for %s", image_url)
    return cleaned


def get_or_generate_alt(
    *,
    image_key: str,
    image_url: str,
    context: str = "",
    caption: Optional[str] = None,
) -> str:
    """Cache-or-generate alt for one image. ``image_key`` is the stable
    cache key (content-addressed for journal images, issue-scoped for the
    cover). Returns ``""`` on cap exhaustion / fetch failure / vision
    failure (a hygiene-review-flaggable signal)."""
    global _calls_remaining
    if not image_key or not image_url:
        return ""
    cached = db.get_cached_alt(image_key)
    if cached:
        return cached
    if _calls_remaining <= 0:
        logger.info("alt_text: vision cap reached; %s left empty for this run", image_key)
        return ""
    _calls_remaining -= 1
    alt = _generate_via_vision(image_url=image_url, context=context, caption=caption)
    if alt:
        db.cache_alt(image_key=image_key, alt=alt, source="vision")
    return alt


def generate_alt(
    *,
    image_url: str,
    context: str = "",
    caption: Optional[str] = None,
) -> str:
    """Generate alt text via one vision call. **No cache, no DB I/O** —
    used by the new ``microblog.fill_missing_alts`` flow where the alt
    lives on micro.blog itself as the source of truth.

    Returns the cleaned alt on success, or ``""`` on cap exhaustion /
    image fetch failure / vision failure. Decrements the per-run vision
    cap on a real call (the cap is shared with ``get_or_generate_alt``
    so a single ``update-draft`` run can't fan out to dozens of vision
    calls). ``begin_run()`` resets the counter at the top of the run.
    """
    global _calls_remaining
    if not image_url:
        return ""
    if _calls_remaining <= 0:
        logger.info("alt_text: vision cap reached; %s left empty for this run", image_url)
        return ""
    _calls_remaining -= 1
    return _generate_via_vision(image_url=image_url, context=context, caption=caption)


def set_manual_alt(*, image_key: str, alt: str) -> None:
    """Record an operator-supplied alt (e.g. from ``cover.json.alt``) in
    the cache. A subsequent ``get_or_generate_alt`` returns it without
    touching the vision API."""
    if not alt or not alt.strip():
        return
    db.cache_alt(image_key=image_key, alt=alt, source="manual")
