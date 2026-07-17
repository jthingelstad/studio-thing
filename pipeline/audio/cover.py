"""Resolve the cover image to embed in a published MP3.

Per-issue covers live at the URL in the frontmatter `image` field
(typically `https://files.thingelstad.com/weekly-thing/<N>/cover.jpg`).
Issues without a per-issue cover fall back to the show-level
`apps/site/img/podcast-cover.png` that the podcast feed already advertises.

Per-issue covers are 1200×675 landscape banners; podcast art conventions
expect square. We center-crop to a square at the shorter side.

Downloaded + squared covers are cached in `tmp/audio/covers/` so we only
fetch and process each one once per local working tree.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
COVER_CACHE_DIR = REPO / "tmp" / "audio" / "covers"
FALLBACK_COVER = REPO / "apps" / "site" / "img" / "podcast-cover.png"


def _cached_cover_path(issue: str, image_url: str) -> Path:
    suffix = Path(urlparse(image_url).path).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png"}:
        suffix = ".jpg"
    return COVER_CACHE_DIR / f"{issue}-original{suffix}"


def _squared_cover_path(issue: str, image_url: str) -> Path:
    suffix = Path(urlparse(image_url).path).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png"}:
        suffix = ".jpg"
    return COVER_CACHE_DIR / f"{issue}{suffix}"


def _probe_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return None
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        return None
    s = streams[0]
    return int(s["width"]), int(s["height"])


def _crop_to_square(src: Path, dst: Path) -> bool:
    """Center-crop src to a square at the shorter side, write to dst."""
    dims = _probe_dimensions(src)
    if dims is None:
        return False
    width, height = dims
    if width == height:
        # Already square — just copy.
        dst.write_bytes(src.read_bytes())
        return True
    side = min(width, height)
    x_off = (width - side) // 2
    y_off = (height - side) // 2
    crop_filter = f"crop={side}:{side}:{x_off}:{y_off}"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-vf", crop_filter, str(dst)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return False
    return True


def _download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status != 200:
                return False
            data = response.read()
    except urllib.error.URLError, urllib.error.HTTPError, TimeoutError:
        return False
    if not data:
        return False
    dest.write_bytes(data)
    return True


def ensure_cover(issue: str, image_url: str | None) -> Path:
    """Return a local path to a square cover image for this issue.

    Downloads the per-issue cover from `image_url`, center-crops to square,
    and caches both the original and squared versions. Falls back to the
    show-level cover (already 3000×3000 square) if the URL is empty or the
    download fails."""
    if image_url:
        squared = _squared_cover_path(issue, image_url)
        if squared.exists() and squared.stat().st_size > 0:
            return squared
        original = _cached_cover_path(issue, image_url)
        if not (original.exists() and original.stat().st_size > 0):
            if not _download(image_url, original):
                print(f"Issue #{issue}: cover download failed, using fallback")
                return FALLBACK_COVER
        if _crop_to_square(original, squared):
            return squared
        print(f"Issue #{issue}: cover crop failed, using fallback")
    return FALLBACK_COVER
