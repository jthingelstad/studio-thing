#!/usr/bin/env python3
"""
Find microposts whose photos were silently lost during the MailChimp →
Buttondown migration. The `mp-photo-alt[]=` marker only survived for
posts with 2+ photos (it's the alt-text array for the additional
photos; the primary photo has a separate `photo` field that left no
marker). A single-photo post therefore has NO trace in the archive
source — just the text with no image.

For every H3 that links to a thingelstad.com micropost page (the
typical `### [Day @ Time](https://www.thingelstad.com/YYYY/MM/DD/...)`
pattern), this script:

  1. Counts images in the source body between that H3 and the next H3.
  2. Fetches the live page and counts its photos.
  3. Flags posts where source=0 but live>0.

Output:
  tmp/missing-photos.json     structured
  tmp/missing-photos.md       review list
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "site" / "archive"
OUT = REPO / "tmp"
OUT.mkdir(exist_ok=True)

# H3 micropost heading: `### [Day @ Time](URL)` with URL on thingelstad.com
H3_MICROPOST_RE = re.compile(
    r'^### \[[^\]]+\]\((https?://(?:www\.|micro\.)?thingelstad\.com/\d{4}/\d{2}/\d{2}/[^)]+)\)',
    re.M,
)

# Same photo host set used by fix_micropost_photos.py
PHOTO_IMG_RE = re.compile(
    r'<img[^>]+src="(https?://'
    r'(?:cdn\.uploads\.micro\.blog'
    r'|(?:(?:www|micro)\.)?thingelstad\.com/uploads'
    r'|files\.thingelstad\.com'
    r')[^"]+)"',
    re.I,
)

# Markdown images in source body: ![alt](url)
MD_IMG_RE = re.compile(r'!\[[^\]]*\]\((https?://[^)\s]+)\)')


def slice_between_h3s(body: str) -> list[tuple[int, int, str, str]]:
    """Return list of (h3_start, slice_end, h3_url, slice_body)."""
    out: list[tuple[int, int, str, str]] = []
    h3_matches = list(H3_MICROPOST_RE.finditer(body))
    for i, m in enumerate(h3_matches):
        h3_start = m.start()
        url = m.group(1)
        # Slice ends at the next H2/H3, or at end of body.
        # We want to scope to just this micropost, so stop at the next
        # heading of level 2 or 3.
        next_heading_re = re.compile(r'^#{2,3} ', re.M)
        m2 = next_heading_re.search(body, m.end())
        slice_end = m2.start() if m2 else len(body)
        out.append((h3_start, slice_end, url, body[m.end():slice_end]))
    return out


def count_source_images(md_slice: str) -> int:
    """Count markdown images in a slice (ignoring non-photo URLs)."""
    count = 0
    for m in MD_IMG_RE.finditer(md_slice):
        url = m.group(1)
        # Only count photos from known hosts (same rule as the fix script).
        if any(h in url for h in [
            "cdn.uploads.micro.blog",
            "thingelstad.com/uploads",
            "files.thingelstad.com",
        ]):
            count += 1
    return count


def count_live_photos(client: httpx.Client, url: str) -> tuple[int, int]:
    """Return (status_code, photo_count)."""
    try:
        r = client.get(url, follow_redirects=True, timeout=15.0)
    except Exception:
        return (-1, 0)
    if r.status_code != 200:
        return (r.status_code, 0)
    photos = set(PHOTO_IMG_RE.findall(r.text))
    return (200, len(photos))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="For testing: only check first N microposts")
    args = ap.parse_args()

    # Pass 1: scan all archive files, collect (issue, h3_url, source_img_count)
    entries: list[dict] = []
    for path in sorted(ARCHIVE.glob("*.md")):
        if not path.stem.isdigit():
            continue
        body = path.read_text(encoding="utf-8")
        if "thingelstad.com/" not in body:
            continue
        slices = slice_between_h3s(body)
        for h3_start, slice_end, url, md_slice in slices:
            src_imgs = count_source_images(md_slice)
            entries.append({
                "issue": int(path.stem),
                "url": url,
                "source_img_count": src_imgs,
            })

    print(f"[missing-photos] found {len(entries)} H3-micropost references "
          f"across {len({e['issue'] for e in entries})} issues",
          flush=True)

    # Pass 2: only fetch URLs where source has 0 photos — that's where we'd
    # miss single-photo posts. Posts with ≥1 source image already match the
    # "tokens + 1" replacement pattern and are not at risk.
    to_check = [e for e in entries if e["source_img_count"] == 0]
    print(f"[missing-photos] {len(to_check)} entries have ZERO source images — "
          f"checking each live page", flush=True)

    if args.limit:
        to_check = to_check[: args.limit]
        print(f"[missing-photos] limited to {len(to_check)}", flush=True)

    # Dedupe URLs
    unique_urls = sorted({e["url"] for e in to_check})
    print(f"[missing-photos] {len(unique_urls)} unique URLs", flush=True)

    results: dict[str, tuple[int, int]] = {}
    with httpx.Client(
        headers={"User-Agent": "weekly-thingelstad-audit/1.0"},
        timeout=20.0,
    ) as client:
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(count_live_photos, client, u): u for u in unique_urls}
            for i, f in enumerate(as_completed(futs), 1):
                url = futs[f]
                status, n = f.result()
                results[url] = (status, n)
                if i % 25 == 0:
                    print(f"  [{i}/{len(unique_urls)}] checked", flush=True)

    # Assemble findings
    missing: list[dict] = []
    ok: list[dict] = []
    broken: list[dict] = []
    for e in to_check:
        status, n = results.get(e["url"], (-1, 0))
        row = {**e, "live_status": status, "live_photos": n}
        if status == 200 and n > 0:
            missing.append(row)
        elif status == 200 and n == 0:
            ok.append(row)  # post exists, no photos — text-only micropost
        else:
            broken.append(row)  # 404 or error — can't recover anyway

    # JSON output
    out_json = OUT / "missing-photos.json"
    out_json.write_text(
        json.dumps(
            {
                "total_h3_microposts_scanned": len(entries),
                "zero_source_image_count": len(to_check),
                "missing_photos": missing,
                "text_only_posts": ok,
                "unreachable_posts": broken,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n[missing-photos] wrote {out_json}", flush=True)

    # Markdown
    lines: list[str] = []
    lines.append("# Missing Micropost Photos Audit")
    lines.append("")
    lines.append(f"- H3 microposts scanned: {len(entries)}")
    lines.append(f"- With zero source images (at-risk): {len(to_check)}")
    lines.append(f"- **Missing photos (actionable)**: **{len(missing)}**")
    lines.append(f"- Text-only posts (OK — page has no photos either): {len(ok)}")
    lines.append(f"- Unreachable posts (404 / error): {len(broken)}")
    lines.append("")

    if missing:
        # Group by issue
        by_issue: dict[int, list[dict]] = {}
        for row in missing:
            by_issue.setdefault(row["issue"], []).append(row)
        total_photos = sum(r["live_photos"] for r in missing)
        lines.append(f"## Missing photos by issue ({total_photos} photos total)")
        lines.append("")
        for issue in sorted(by_issue):
            rows = by_issue[issue]
            photos_n = sum(r["live_photos"] for r in rows)
            lines.append(f"### #{issue} — {len(rows)} microposts, {photos_n} photos missing")
            lines.append("")
            for r in rows:
                lines.append(f"- `{r['url']}` — {r['live_photos']} photo(s)")
            lines.append("")

    if broken:
        lines.append(f"## Unreachable ({len(broken)}) — cannot recover")
        lines.append("")
        by_issue_b: dict[int, list[dict]] = {}
        for row in broken:
            by_issue_b.setdefault(row["issue"], []).append(row)
        for issue in sorted(by_issue_b):
            for r in by_issue_b[issue]:
                lines.append(f"- #{issue}: [{r['live_status']}] `{r['url']}`")
        lines.append("")

    out_md = OUT / "missing-photos.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[missing-photos] wrote {out_md}", flush=True)

    # Console summary
    print()
    print(f"RESULT: {len(missing)} microposts are missing photos that still exist on the live page "
          f"({sum(r['live_photos'] for r in missing)} photos total).",
          flush=True)


if __name__ == "__main__":
    main()
