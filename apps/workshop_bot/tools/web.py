"""Light-weight URL fetcher for Linky's research tool.

Fetches a URL with a sensible timeout, drops navigation/script chrome,
and returns a plain-text excerpt the LLM can reason over without
exploding the context window. Hardened against runaway pages and
binary blobs (rejects on Content-Type and on size).
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger("workshop.web")

DEFAULT_TIMEOUT = 15
MAX_BYTES = 1_500_000  # 1.5 MB hard cap
MAX_TEXT_CHARS = 12_000
USER_AGENT = (
    "Mozilla/5.0 (compatible; WeeklyThing-WorkshopBot/1.0; "
    "+https://weekly.thingelstad.com/about/)"
)


def _allowed_content_type(value: str) -> bool:
    value = (value or "").lower()
    return value.startswith("text/") or "html" in value or "xml" in value


def fetch_text(url: str, *, max_chars: int = MAX_TEXT_CHARS) -> dict[str, Any]:
    """Fetch ``url`` and return ``{title, text, url, status, truncated}``.

    Returns an ``error`` field instead of raising when the response is
    binary, oversized, or the request fails. The agent loop turns the
    return value into a tool_result either way.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        with requests.get(
            url, headers=headers, timeout=DEFAULT_TIMEOUT, stream=True,
            allow_redirects=True,
        ) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if not _allowed_content_type(ctype):
                return {"url": url, "error": f"non-text content-type: {ctype}"}

            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_BYTES:
                    return {
                        "url": url,
                        "error": f"response exceeded {MAX_BYTES} bytes; aborted",
                        "status": resp.status_code,
                    }
                chunks.append(chunk)
            body = b"".join(chunks)
            status = resp.status_code
            final_url = str(resp.url)
    except requests.RequestException as exc:
        logger.info("web.fetch_text: %s -> %s", url, exc)
        return {"url": url, "error": f"{type(exc).__name__}: {exc}"}

    try:
        decoded = body.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "error": f"decode failed: {exc}", "status": status}

    # Imported lazily so the module loads without bs4 in dev/test environments.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(decoded, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "") or ""
    for tag in soup(["script", "style", "noscript", "nav", "footer", "form", "aside"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    logger.info("web.fetch_text: %s status=%s text=%d", final_url, status, len(text))
    return {
        "url": final_url,
        "status": status,
        "title": title,
        "text": text,
        "truncated": truncated,
    }
