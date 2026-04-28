#!/usr/bin/env python3
"""
Restore micropost photos that were silently lost — complement to
fix_micropost_photos.py. This script handles the cases where the source
body has NO image and no `mp-photo-alt[]=` marker (single-photo posts
lost the primary photo with no trace).

Driven by tmp/missing-photos.json. For each entry whose era is
MailChimp (#42-#130) or Tinyletter (#1-#41):
  1. Fetch the live page and extract its photos.
  2. Locate the H3 link in the source body.
  3. Insert `![](url)` lines at the end of that H3's slice (just before
     the next heading), preserving the existing body paragraph.

Buttondown-era entries are SKIPPED — those may be intentionally
text-only "read my full journal post" links. Pass --include-buttondown
to override.

Usage:
  python pipeline/audits/restore_missing_micropost_photos.py --dry-run
  python pipeline/audits/restore_missing_micropost_photos.py
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

PHOTO_IMG_RE = re.compile(
    r'<img[^>]+src="(https?://'
    r'(?:cdn\.uploads\.micro\.blog'
    r'|(?:(?:www|micro)\.)?thingelstad\.com/uploads'
    r'|files\.thingelstad\.com'
    r')[^"]+)"',
    re.I,
)


def normalize_photo_url(url: str) -> str:
    return re.sub(
        r"^https?://(?:micro\.|www\.)?thingelstad\.com/uploads/",
        "https://www.thingelstad.com/uploads/",
        url,
    )


def fetch_photos(client: httpx.Client, url: str) -> tuple[int, list[str]]:
    try:
        r = client.get(url, follow_redirects=True, timeout=20.0)
    except Exception as e:
        return (-1, [])
    if r.status_code != 200:
        return (r.status_code, [])
    photos = [normalize_photo_url(u) for u in PHOTO_IMG_RE.findall(r.text)]
    # Dedupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in photos:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return (200, unique)


def era_of(num: int) -> str:
    if num <= 41:
        return "Tinyletter"
    if num <= 130:
        return "MailChimp"
    return "Buttondown"


def inject_photos_after_h3(
    body: str,
    target_url: str,
    photos: list[str],
) -> tuple[str, bool]:
    """Find `### [text](target_url)` and insert ![](photo) lines at the end
    of that H3's slice (just before the next heading). Return (new_body, injected)."""
    # Locate the H3 with this exact URL. Escape parens & special chars.
    esc_url = re.escape(target_url)
    h3_re = re.compile(rf"^(### \[[^\]]+\]\({esc_url}\))$", re.M)
    m = h3_re.search(body)
    if not m:
        return body, False
    # End of this slice = next H2/H3, or end of body
    next_heading_re = re.compile(r"^#{2,3} ", re.M)
    m2 = next_heading_re.search(body, m.end())
    slice_end = m2.start() if m2 else len(body)
    # Walk back from slice_end over trailing whitespace
    insert_at = slice_end
    while insert_at > m.end() and body[insert_at - 1] in ("\n", " ", "\t"):
        insert_at -= 1
    # Build the injection: blank line separator, then one line per photo,
    # then a blank line before the next heading (if one follows).
    img_block = "\n\n" + "\n".join(f"![]({p})" for p in photos)
    if slice_end < len(body):
        img_block += "\n\n"
    else:
        img_block += "\n"
    new_body = body[:insert_at] + img_block + body[slice_end:]
    return new_body, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-buttondown", action="store_true",
                    help="Also restore Buttondown-era cases (off by default)")
    args = ap.parse_args()

    missing_path = OUT / "missing-photos.json"
    if not missing_path.exists():
        print("ERROR: tmp/missing-photos.json not found — run "
              "pipeline/audits/audit_missing_micropost_photos.py first", flush=True)
        sys.exit(1)

    data = json.loads(missing_path.read_text())
    entries = data.get("missing_photos", [])

    # Filter by era
    if args.include_buttondown:
        selected = entries
    else:
        selected = [e for e in entries if era_of(e["issue"]) != "Buttondown"]

    print(f"[restore] {len(selected)}/{len(entries)} entries selected "
          f"(era filter: {'ALL' if args.include_buttondown else 'MailChimp + Tinyletter'})",
          flush=True)

    # Fetch each URL
    unique_urls = sorted({e["url"] for e in selected})
    print(f"[restore] fetching {len(unique_urls)} unique URLs...", flush=True)
    results: dict[str, tuple[int, list[str]]] = {}
    with httpx.Client(
        headers={"User-Agent": "weekly-thingelstad-restore/1.0"},
        timeout=25.0,
    ) as client:
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(fetch_photos, client, u): u for u in unique_urls}
            for i, f in enumerate(as_completed(futs), 1):
                url = futs[f]
                results[url] = f.result()
                if i % 50 == 0:
                    print(f"  [{i}/{len(unique_urls)}]", flush=True)

    # Apply per file
    per_file: dict[int, list[dict]] = {}
    for e in selected:
        per_file.setdefault(e["issue"], []).append(e)

    totals = {
        "files_changed": 0,
        "injected": 0,
        "photos_added": 0,
        "h3_not_found": 0,
        "fetch_failed": 0,
    }

    for issue_num in sorted(per_file):
        path = ARCHIVE / f"{issue_num}.md"
        body = path.read_text(encoding="utf-8")
        original = body
        entries_for_file = per_file[issue_num]
        changes_here = 0
        photos_here = 0
        for e in entries_for_file:
            url = e["url"]
            status, photos = results.get(url, (-1, []))
            if status != 200 or not photos:
                totals["fetch_failed"] += 1
                continue
            new_body, injected = inject_photos_after_h3(body, url, photos)
            if injected:
                body = new_body
                changes_here += 1
                photos_here += len(photos)
            else:
                totals["h3_not_found"] += 1
        if body != original:
            totals["files_changed"] += 1
            totals["injected"] += changes_here
            totals["photos_added"] += photos_here
            tag = "[DRY]" if args.dry_run else "[APPLY]"
            print(f"  {tag} #{issue_num}: {changes_here} microposts, {photos_here} photos",
                  flush=True)
            if not args.dry_run:
                path.write_text(body, encoding="utf-8")

    print(f"\n[restore] summary:", flush=True)
    for k, v in totals.items():
        print(f"  {k}: {v}", flush=True)


if __name__ == "__main__":
    main()
