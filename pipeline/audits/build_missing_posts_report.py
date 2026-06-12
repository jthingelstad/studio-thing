#!/usr/bin/env python3
"""
Build an enriched report of missing micro.blog posts for recovery.

For each 404 URL in tmp/missing-photos.json, adds:
- The Wayback Machine's closest snapshot URL (from the availability API)
- The micropost's body paragraph text as it appears in the Weekly Thing issue
- The H3 heading (day/time) as it appears in the issue
- The original micro.blog canonical URL (jthingelstad.micro.blog/…)

This file is meant to be sent to micro.blog support so they can cross-
reference it against whatever they still have in their backups.

Output: tmp/missing-microblog-posts.md (overwrites)
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "apps" / "site" / "archive"
OUT = REPO / "tmp"


def wayback_lookup(client: httpx.Client, url: str) -> str | None:
    """Return the closest Wayback snapshot URL, or None."""
    try:
        r = client.get(
            "https://archive.org/wayback/available",
            params={"url": url},
            timeout=15.0,
        )
        data = r.json()
        snap = data.get("archived_snapshots", {}).get("closest") or {}
        if snap.get("status") == "200":
            return snap.get("url")
    except Exception:
        return None
    return None


def micro_blog_canonical(url: str) -> str:
    """Convert www.thingelstad.com/YYYY/MM/DD/slug.html → jthingelstad.micro.blog variant."""
    return re.sub(
        r"https?://(?:www\.|micro\.)?thingelstad\.com/",
        "https://jthingelstad.micro.blog/",
        url,
    )


def find_micropost_in_issue(issue_num: int, url: str) -> tuple[str, str]:
    """Return (h3_heading, body_paragraph) for the micropost that references
    this URL in the issue's source markdown."""
    path = ARCHIVE / f"{issue_num}.md"
    if not path.exists():
        return ("", "")
    body = path.read_text(encoding="utf-8")
    esc = re.escape(url)
    # Match the H3 heading with this URL, then capture until next H2/H3.
    m = re.search(
        rf"^(### \[[^\]]+\]\({esc}\))\s*\n\n(.*?)(?=\n#{{2,3}} |\Z)",
        body,
        re.S | re.M,
    )
    if not m:
        return ("", "")
    heading = m.group(1).strip()
    # Body = everything until next heading, trimmed.
    b = m.group(2).strip()
    # Keep just the first paragraph for readability.
    first_para = b.split("\n\n")[0].strip()
    return (heading, first_para)


def main() -> None:
    src = OUT / "missing-photos.json"
    data = json.loads(src.read_text())
    broken = data["unreachable_posts"]

    # Dedupe by URL; remember first issue reference
    unique: dict[str, int] = {}
    for r in broken:
        unique.setdefault(r["url"], r["issue"])

    print(f"[enrich] {len(unique)} unique 404 URLs", flush=True)

    # Wayback lookups (concurrent)
    wb_map: dict[str, str | None] = {}
    with httpx.Client(headers={"User-Agent": "weekly-thingelstad-recovery/1.0"}) as c:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {pool.submit(wayback_lookup, c, u): u for u in unique}
            for i, f in enumerate(as_completed(futs), 1):
                url = futs[f]
                wb_map[url] = f.result()
                if i % 25 == 0:
                    print(f"  [{i}/{len(unique)}] wayback looked up", flush=True)

    # Build enriched records
    records: list[dict] = []
    for url, issue in unique.items():
        heading, body_para = find_micropost_in_issue(issue, url)
        # Parse date
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/([^/]+?)\.html", url)
        if m:
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            slug = m.group(4)
        else:
            date, slug = "", ""
        records.append({
            "url": url,
            "micro_blog_url": micro_blog_canonical(url),
            "wayback": wb_map.get(url),
            "issue": issue,
            "date": date,
            "slug": slug,
            "heading": heading,
            "body": body_para,
        })

    records.sort(key=lambda r: (r["date"], r["url"]))

    # Also JSON output for programmatic use
    json_out = OUT / "missing-microblog-posts.json"
    json_out.write_text(
        json.dumps({
            "note": "199 missing micro.blog posts referenced from The Weekly Thing archive. "
                    "All 404 on thingelstad.com and jthingelstad.micro.blog. "
                    "Most have Wayback Machine snapshots.",
            "count": len(records),
            "with_wayback": sum(1 for r in records if r["wayback"]),
            "records": records,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[enrich] wrote {json_out}", flush=True)

    # Markdown
    lines: list[str] = []
    lines.append("# Missing micro.blog posts — recovery packet for micro.blog")
    lines.append("")
    lines.append("These URLs on `https://www.thingelstad.com/` (a micro.blog-hosted site) all return **HTTP 404** today. Each was a real micropost referenced as an H3 link in Jamie Thingelstad's *The Weekly Thing* newsletter archive. The Wayback Machine still has snapshots for most of them, confirming the posts existed and are now lost.")
    lines.append("")
    lines.append("**Status across every URL variant tried:**")
    lines.append("- `https://www.thingelstad.com/YYYY/MM/DD/<slug>.html` → 404")
    lines.append("- Canonical: `https://jthingelstad.micro.blog/YYYY/MM/DD/<slug>.html` → 404")
    lines.append("- Trailing-slash, no-suffix, `.md` variants → 404")
    lines.append("")
    lines.append(f"**Total missing: {len(records)} posts** (concentrated 2018–2019). Wayback snapshots found for **{sum(1 for r in records if r['wayback'])}** of them.")
    lines.append("")
    lines.append("Distribution suggests batch-level loss rather than individual deletions — specific days have clusters (e.g. 11 posts from April 13 & 17, 2019 are all missing; 18 posts from a single week in May 2018 are all missing).")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-post detail")
    lines.append("")
    lines.append("For each missing post: the dead URL, the Wayback snapshot URL (where available), and the context from the Weekly Thing issue — heading and body paragraph as they appear in the newsletter. When these posts are restored, the archive's H3 link text and body paragraph can be used to verify the recovered post matches.")
    lines.append("")
    lines.append("Grouped by month.")
    lines.append("")

    # Group by YYYY-MM
    from collections import defaultdict
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        key = r["date"][:7] if r["date"] else "unknown"
        by_month[key].append(r)

    for month in sorted(by_month):
        items = by_month[month]
        lines.append(f"### {month} ({len(items)} posts)")
        lines.append("")
        for r in items:
            lines.append(f"**`{r['url']}`**")
            lines.append("")
            lines.append(f"- micro.blog canonical: `{r['micro_blog_url']}`")
            if r["wayback"]:
                lines.append(f"- Wayback snapshot: {r['wayback']}")
            else:
                lines.append("- Wayback snapshot: *(none found)*")
            lines.append(f"- Referenced in: Weekly Thing #{r['issue']}")
            if r["heading"]:
                lines.append(f"- Newsletter heading: `{r['heading']}`")
            if r["body"]:
                # Collapse newlines for markdown table readability; quote it
                b = re.sub(r"\s+", " ", r["body"]).strip()
                lines.append("- Body paragraph from newsletter:")
                lines.append(f"  > {b}")
            lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Plain URL list (deduped, sorted)")
    lines.append("")
    lines.append("```")
    for r in records:
        lines.append(r["url"])
    lines.append("```")
    lines.append("")

    md_out = OUT / "missing-microblog-posts.md"
    md_out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[enrich] wrote {md_out} ({len(lines)} lines)", flush=True)


if __name__ == "__main__":
    main()
