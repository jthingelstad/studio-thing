"""Re-host micro.blog journal images into the issue workspace.

Journal posts embed images served from Jamie's micro.blog upload host(s)
at full resolution (megabyte-scale photos). For the Weekly Thing we copy
each one into ``s3://files.thingelstad.com/weekly-thing/{N}/journal/<name>``,
resized down for email — the email shouldn't carry full-res photos, and
keeping a local copy makes the issue self-contained instead of hot-linking
the website.

``rehost_in_markdown(content_md, issue_number)`` does this for one journal
post's markdown: it finds ``<img src=…>`` and ``![](…)`` references on the
blog's upload host(s), rehosts each (skipping any already in the workspace
— a cheap HEAD check, so the daily ``update-draft`` re-run is cheap),
rewrites the reference to the local URL, and normalizes ``<img>`` tags to
``![alt](url)``. Images on other hosts are left untouched (URL unchanged);
a per-image failure leaves that one alone rather than breaking the post.

Configurable via env:
  - ``MICROBLOG_IMAGE_HOSTS`` — csv of hosts whose images we rehost
    (default: ``www.thingelstad.com``, ``micro.thingelstad.com``,
    ``cdn.uploads.micro.blog``, ``uploads.micro.blog``).
  - ``MICROBLOG_IMAGE_MAX_DIM`` — longest-side pixels after resize
    (default 600; downscale only, never upscale).
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
from urllib.parse import urlparse

import requests

from . import s3

logger = logging.getLogger("workshop.journal_images")

_DEFAULT_UPLOAD_HOSTS = (
    "www.thingelstad.com", "micro.thingelstad.com",
    "cdn.uploads.micro.blog", "uploads.micro.blog",
)
_DEFAULT_MAX_DIM = 600
_FETCH_TIMEOUT = 30.0
_FETCH_MAX_BYTES = 30 * 1024 * 1024  # 30 MB raw — sanity cap on the download
_UA = "WeeklyThing-WorkshopBot/1.0"

_IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
_SRC_RE = re.compile(r'src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_ALT_RE = re.compile(r'alt\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_MD_IMG_RE = re.compile(r'!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)')
_IMG_EXT_RE = re.compile(r"\.(jpe?g|png|gif|webp)\b", re.IGNORECASE)
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(jpe?g|png|gif|webp)$", re.IGNORECASE)
_RESIZABLE = {".jpg", ".jpeg", ".png"}


def _upload_hosts() -> set[str]:
    raw = os.environ.get("MICROBLOG_IMAGE_HOSTS")
    hosts = [h.strip().lower() for h in raw.split(",")] if raw else list(_DEFAULT_UPLOAD_HOSTS)
    return {h for h in hosts if h}


def _max_dim() -> int:
    try:
        v = int(os.environ.get("MICROBLOG_IMAGE_MAX_DIM") or _DEFAULT_MAX_DIM)
        return v if v > 0 else _DEFAULT_MAX_DIM
    except (TypeError, ValueError):
        return _DEFAULT_MAX_DIM


def _should_rehost(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    host = (p.netloc or "").lower()
    if not host or host == s3._bucket().lower():
        return False  # already local (or relative)
    if host not in _upload_hosts():
        return False
    if not _IMG_EXT_RE.search(p.path or ""):
        return False
    # For Jamie's own domains, only the /uploads/ tree is a photo upload;
    # micro.blog CDN hosts have their own path layout.
    if host.endswith("thingelstad.com") and "/uploads/" not in (p.path or ""):
        return False
    return True


def _ext(url: str) -> str:
    m = _IMG_EXT_RE.search(urlparse(url).path or "")
    if not m:
        return ".jpg"
    e = "." + m.group(1).lower()
    return ".jpg" if e == ".jpeg" else e  # normalize


def _local_name(url: str) -> str:
    """A stable filename for the local copy — reuse the source basename
    (micro.blog uploads are already content-hashed, e.g. ``428e3db12e.jpg``)
    when it's a safe name, else a hash of the URL. The extension is the
    *post-resize* one (``.jpeg`` → ``.jpg``) so the HEAD-skip on the next
    ``update-draft`` run matches what we actually wrote."""
    ext = _ext(url)  # normalizes .jpeg → .jpg
    base = os.path.basename(urlparse(url).path or "")
    if _SAFE_NAME_RE.match(base):
        stem = base.rsplit(".", 1)[0]
        return f"{stem}{ext}"
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:10] + ext


def _resize(body: bytes, ext: str, max_dim: int) -> tuple[bytes, str]:
    """Downscale to ``max_dim`` longest side (never upscale). JPEG → q80;
    PNG → optimized. Returns (bytes, ext). On any failure (incl. an
    unresizable format), returns the original bytes unchanged."""
    if ext not in _RESIZABLE:
        return body, ext
    try:
        from PIL import Image
    except ImportError:
        logger.warning("journal_images: Pillow not available — uploading image as-is")
        return body, ext
    try:
        im = Image.open(io.BytesIO(body))
        im.load()
        w, h = im.size
        if max(w, h) > max_dim:
            im.thumbnail((max_dim, max_dim))
        out = io.BytesIO()
        if ext in (".jpg", ".jpeg"):
            im.convert("RGB").save(out, format="JPEG", quality=80, optimize=True)
            return out.getvalue(), ".jpg"
        # PNG — keep mode (so alpha survives); optimize.
        im.save(out, format="PNG", optimize=True)
        return out.getvalue(), ".png"
    except Exception as exc:  # noqa: BLE001
        logger.warning("journal_images: resize failed (%s) — uploading as-is", exc)
        return body, ext


def _fetch(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=_FETCH_TIMEOUT, headers={"User-Agent": _UA}, stream=True)
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if ctype and not ctype.startswith("image/"):
            logger.warning("journal_images: %s is not an image (%s) — skipping", url, ctype)
            return None
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > _FETCH_MAX_BYTES:
                logger.warning("journal_images: %s exceeds %d bytes — skipping", url, _FETCH_MAX_BYTES)
                return None
            chunks.append(chunk)
        return b"".join(chunks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("journal_images: fetch %s failed: %s", url, exc)
        return None


def _rehost_one(url: str, issue_number: int) -> str | None:
    """Download → resize → upload one blog image; return its new public URL.
    Skips the work (HEAD check) if it's already in the workspace. Returns
    None on failure (caller leaves the original URL)."""
    name = _local_name(url)
    try:
        if s3.journal_image_exists(issue_number, name):
            return s3.journal_image_url(issue_number, name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("journal_images: HEAD %s failed (%s) — will try to (re)upload", name, exc)
    body = _fetch(url)
    if body is None:
        return None
    resized, ext = _resize(body, _ext(url), _max_dim())
    # The extension may change (e.g. .jpeg → .jpg); re-derive the name.
    final_name = name
    if not final_name.lower().endswith(ext):
        stem = final_name.rsplit(".", 1)[0]
        final_name = f"{stem}{ext}"
    try:
        res = s3.write_journal_image(issue_number, final_name, resized)
    except Exception as exc:  # noqa: BLE001
        logger.warning("journal_images: upload %s failed: %s", final_name, exc)
        return None
    logger.info("journal_images: rehosted %s -> %s (%d bytes)", url, res["url"], res["size"])
    return res["url"]


def _rewrite_url(url: str, issue_number: int) -> str:
    """Return the rehosted URL for a blog image, or the original URL if it
    isn't a blog image or the rehost failed."""
    if not _should_rehost(url):
        return url
    new = _rehost_one(url, issue_number)
    return new or url


def rehost_in_markdown(content_md: str, issue_number: int) -> str:
    """Rehost blog-hosted images in one journal post's markdown and rewrite
    the references; normalize ``<img>`` tags to ``![alt](url)``. Idempotent
    and robust — a per-image failure leaves that image's reference as-is."""
    if not content_md:
        return content_md
    n = int(issue_number)

    # 1. Markdown images: ![alt](url) — rewrite the url if it's a blog image.
    def _md_sub(m: re.Match) -> str:
        alt, url = m.group(1), m.group(2).strip()
        return f"![{alt}]({_rewrite_url(url, n)})"

    out = _MD_IMG_RE.sub(_md_sub, content_md)

    # 2. <img ...> HTML tags → ![alt](url), rehosting blog images.
    def _img_sub(m: re.Match) -> str:
        tag = m.group(0)
        src_m = _SRC_RE.search(tag)
        if not src_m:
            return tag  # malformed; leave it
        url = src_m.group(1).strip()
        alt_m = _ALT_RE.search(tag)
        alt = (alt_m.group(1) if alt_m else "").strip()
        return f"![{alt}]({_rewrite_url(url, n)})"

    return _IMG_TAG_RE.sub(_img_sub, out)
