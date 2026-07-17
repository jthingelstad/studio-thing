"""Report every `thingelstad.com/assets/logos/` URL reference in archive
bodies. Read-only — produces a review artifact for Jamie to act on
manually. No file changes.
"""

import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(line_buffering=True)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "apps" / "site" / "archive"
REPORT_FILE = Path("/tmp/logo-refs.txt")

URL_RE = re.compile(r"https?://(?:www\.)?thingelstad\.com/assets/logos/[^\s)\"'>]+")


def check_url(url):
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return str(r.status_code)
    except requests.Timeout:
        return "timeout"
    except requests.RequestException as e:
        return f"err:{type(e).__name__}"


def main():
    hits = []
    url_cache = {}  # avoid re-HEADing identical URLs

    for fp in sorted(
        ARCHIVE_DIR.glob("*.md"), key=lambda p: int(p.stem) if p.stem.isdigit() else 9999
    ):
        if not fp.stem.isdigit():
            continue
        lines = fp.read_text().split("\n")
        for lineno, line in enumerate(lines, start=1):
            for m in URL_RE.finditer(line):
                url = m.group(0)
                if url not in url_cache:
                    url_cache[url] = check_url(url)
                status = url_cache[url]
                # ±60-char context
                s = max(0, m.start() - 60)
                e = min(len(line), m.end() + 60)
                snippet = line[s:e].replace("\n", " ")
                hits.append((fp.stem, lineno, status, url, snippet))

    # Write report
    lines_out = [
        f"/assets/logos/ audit — {len(hits)} hits across {len({h[0] for h in hits})} issues",
        "",
    ]
    current_issue = None
    for issue, lineno, status, url, snippet in hits:
        if issue != current_issue:
            lines_out.append(f"\n=== #{issue} ===")
            current_issue = issue
        lines_out.append(f"  L{lineno}  [{status}]  {url}")
        lines_out.append(f"    {snippet}")
    lines_out.append("")
    lines_out.append(
        f"Unique URLs: {len(url_cache)} — "
        f"{sum(1 for s in url_cache.values() if s == '200')} live, "
        f"{sum(1 for s in url_cache.values() if s == '404')} 404, "
        f"{sum(1 for s in url_cache.values() if s not in ('200', '404'))} other."
    )

    report = "\n".join(lines_out)
    REPORT_FILE.write_text(report)
    print(report)
    print(f"\nReport written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
