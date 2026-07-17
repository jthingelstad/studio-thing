#!/usr/bin/env python3
"""
Restore micropost photos that were lost as `mp-photo-alt[]=` tokens.

During the migration to Buttondown, the micropub form-field placeholder
`mp-photo-alt[]=` leaked into the body instead of the actual photo
markdown. The original photos still live on thingelstad.com (Jamie's
micro.blog-powered site) at the URL linked in the H3 above each run of
tokens. For each run:

  1. Find the H3 link URL immediately above the run.
  2. Fetch that page. If it returns 404, strip the tokens.
  3. If 200, extract every `<img>` under class `u-photo` / the
     `cdn.uploads.micro.blog` or `files.thingelstad.com` host — those are
     the post's photos. Replace the token line with one `![](url)`
     per photo.

Verified: token_count + 1 = page_photo_count on 44 of 45 working pages
(the +1 being the post's primary photo on the h-entry wrapper).

Usage:
  python pipeline/audits/fix_micropost_photos.py --dry-run
  python pipeline/audits/fix_micropost_photos.py            # applies edits
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "apps" / "site" / "archive"

H3_RE = re.compile(r"^### \[[^\]]+\]\((https?://[^)]+)\)")
MP_LINE_RE = re.compile(r"^mp-photo-alt\[\](?:=mp-photo-alt\[\])*=?\s*$")
# Extract img tags whose src is a post photo — covers:
#   cdn.uploads.micro.blog/…              (modern micro.blog CDN)
#   micro.thingelstad.com/uploads/…       (legacy micro.blog subdomain)
#   www.thingelstad.com/uploads/…         (current canonical — redirect target)
#   files.thingelstad.com/…               (newsletter S3 bucket)
# Explicitly excludes avatars/chrome (avatars.micro.blog, jthingelstad/avatar.jpg).
IMG_SRC_RE = re.compile(
    r'<img[^>]+src="(https?://'
    r"(?:cdn\.uploads\.micro\.blog"
    r"|(?:(?:www|micro)\.)?thingelstad\.com/uploads"
    r"|files\.thingelstad\.com"
    r')[^"]+)"',
    re.I,
)


def normalize_photo_url(url: str) -> str:
    """Normalize legacy micro.thingelstad.com / bare thingelstad.com to the
    canonical https://www.thingelstad.com/uploads/ form (matches the existing
    repo-wide rewrite from commit 40930fa)."""
    url = re.sub(
        r"^https?://(?:micro\.|www\.)?thingelstad\.com/uploads/",
        "https://www.thingelstad.com/uploads/",
        url,
    )
    return url


def fetch_photos(client: httpx.Client, url: str) -> tuple[int, list[str]]:
    """Return (status_code, list_of_photo_urls)."""
    try:
        r = client.get(url, follow_redirects=True, timeout=15.0)
    except Exception as e:
        print(f"    ERR {type(e).__name__}: {e}", flush=True)
        return (-1, [])
    if r.status_code != 200:
        return (r.status_code, [])
    photos = [normalize_photo_url(u) for u in IMG_SRC_RE.findall(r.text)]
    # Dedupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in photos:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return (200, unique)


def transform(
    body: str, photo_map: dict[str, list[str]], status_map: dict[str, int]
) -> tuple[str, dict]:
    """Return (new_body, stats)."""
    lines = body.split("\n")
    out: list[str] = []
    last_h3_url: str | None = None
    stats = {
        "replaced": 0,
        "stripped_404": 0,
        "tokens_found": 0,
        "photos_added": 0,
        "skipped_other": 0,
    }
    for line in lines:
        m = H3_RE.match(line)
        if m:
            last_h3_url = m.group(1)
            out.append(line)
            continue
        if MP_LINE_RE.match(line):
            stats["tokens_found"] += 1
            if last_h3_url is None:
                # No preceding H3 — leave alone, shouldn't happen in practice
                stats["skipped_other"] += 1
                out.append(line)
                last_h3_url = None
                continue
            status = status_map.get(last_h3_url, -1)
            photos = photo_map.get(last_h3_url, [])
            if status == 200 and photos:
                for url in photos:
                    out.append(f"![]({url})")
                stats["replaced"] += 1
                stats["photos_added"] += len(photos)
            elif status == 404:
                # Strip the line entirely
                stats["stripped_404"] += 1
            else:
                # Unknown status or fetch failed — leave as-is to be safe
                stats["skipped_other"] += 1
                out.append(line)
            # One H3 feeds one token line
            last_h3_url = None
            continue
        out.append(line)
    return ("\n".join(out), stats)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Pass 1: find all (issue, url, count)
    work: dict[Path, list[str]] = {}  # path -> list of urls that appear
    urls_needed: set[str] = set()
    for p in sorted(ARCHIVE.glob("*.md")):
        if not p.stem.isdigit():
            continue
        body = p.read_text(encoding="utf-8")
        if "mp-photo-alt[]" not in body:
            continue
        # Collect URLs in order
        lines = body.split("\n")
        last_h3 = None
        urls_in_file: list[str] = []
        for line in lines:
            m = H3_RE.match(line)
            if m:
                last_h3 = m.group(1)
            elif MP_LINE_RE.match(line) and last_h3:
                urls_in_file.append(last_h3)
                urls_needed.add(last_h3)
                last_h3 = None
        if urls_in_file:
            work[p] = urls_in_file

    print(
        f"[micropost-photos] {len(work)} files contain tokens; "
        f"{len(urls_needed)} unique URLs to fetch",
        flush=True,
    )

    # Pass 2: fetch all unique URLs
    photo_map: dict[str, list[str]] = {}
    status_map: dict[str, int] = {}
    with httpx.Client(timeout=20.0, headers={"User-Agent": "weekly-thingelstad-fix/1.0"}) as client:
        for i, url in enumerate(sorted(urls_needed), 1):
            status, photos = fetch_photos(client, url)
            photo_map[url] = photos
            status_map[url] = status
            tag = "ok" if status == 200 else ("404" if status == 404 else f"err{status}")
            print(
                f"  [{i:2}/{len(urls_needed)}] {tag} {len(photos)} photos — {url[-60:]}", flush=True
            )

    # Pass 3: transform files
    total_stats = {
        "files_changed": 0,
        "replaced": 0,
        "stripped_404": 0,
        "photos_added": 0,
        "skipped_other": 0,
    }
    for path, _urls in sorted(work.items()):
        body = path.read_text(encoding="utf-8")
        new_body, stats = transform(body, photo_map, status_map)
        if new_body == body:
            continue
        total_stats["files_changed"] += 1
        total_stats["replaced"] += stats["replaced"]
        total_stats["stripped_404"] += stats["stripped_404"]
        total_stats["photos_added"] += stats["photos_added"]
        total_stats["skipped_other"] += stats["skipped_other"]
        rel = path.relative_to(REPO)
        print(
            f"  {'[DRY]' if args.dry_run else '[APPLY]'} {rel}: "
            f"{stats['replaced']} runs replaced, "
            f"{stats['stripped_404']} stripped, "
            f"{stats['photos_added']} photos added, "
            f"{stats['skipped_other']} left alone",
            flush=True,
        )
        if not args.dry_run:
            path.write_text(new_body, encoding="utf-8")

    print("\n[micropost-photos] summary:", flush=True)
    for k, v in total_stats.items():
        print(f"  {k}: {v}", flush=True)


if __name__ == "__main__":
    main()
