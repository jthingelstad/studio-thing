#!/usr/bin/env python3
"""
Audit rendered archive HTML for structural issues.

Reads every _site/archive/<N>/index.html, inspects the .issue-content region,
and records findings to:
  tmp/archive-audit.json   (machine-readable index)
  tmp/archive-audit.md     (human-readable report)

Categories checked:
  template-tag-leak   Buttondown/Mailchimp template tags surviving into HTML
  bare-url            Plain-text URL in rendered text (not wrapped in <a>)
  header-hierarchy    H1 in body / level-skip / orphan H3 / heading without id
  broken-image        Image URL returns non-2xx or is unreachable
  missing-image-src   <img> element with no src (or empty src)
  empty-link          <a> tag with no visible text
  malformed-markdown  Leftover markdown syntax that failed to render
  encoding            Mojibake, double-encoded entities, stray &
  legacy-host         Image/link pointing at a known-dead host (MailChimp CDN etc.)
  empty-body          Virtually empty issue body
  unclosed-construct  Obvious unbalanced markdown artifact (unpaired **, etc.)
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup, NavigableString

sys.stdout.reconfigure(line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = REPO_ROOT / "_site" / "archive"
OUT_DIR = REPO_ROOT / "tmp"
OUT_DIR.mkdir(exist_ok=True)

# Hosts known to have served dead images historically.
LEGACY_IMAGE_HOSTS = (
    "gallery.mailchimp.com",
    "mcusercontent.com",
    "cdn-images.mailchimp.com",
    "list-manage.com",
    "us4.campaign-archive.com",
    "campaign-archive.com",
    "tinyletter.com",
)

# Text node URL matcher — excludes trailing punctuation.
BARE_URL_RE = re.compile(r"(?<![\"'>=])\bhttps?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]}]")

# Template tag patterns that should have been stripped.
TEMPLATE_TAG_PATTERNS = [
    (re.compile(r"\{\{[^{}]*\}\}"), "jinja-variable"),
    (re.compile(r"\{%[^{}]*%\}"), "jinja-block"),
    (re.compile(r"\*\|[A-Z0-9_:]+\|\*"), "mailchimp-merge"),
    (re.compile(r"<!--\s*buttondown-editor-mode[^>]*-->", re.I), "editor-mode-comment"),
]

# Common mojibake / encoding artefacts.
# Use unicode escapes so source stays ASCII-safe.
_MOJIBAKE = (
    "\u00e2\u20ac\u2122|"       # â€™  (right single quote)
    "\u00e2\u20ac\u0153|"       # â€œ  (left double quote)
    "\u00e2\u20ac\u009d|"       # â€  (right double quote)
    "\u00e2\u20ac\u201d|"       # â€”  (em dash)
    "\u00e2\u20ac\u2013|"       # â€–  (en dash)
    "\u00e2\u20ac\u02dc|"       # â€˜  (left single quote)
    "\u00e2\u20ac\u00a6|"       # â€¦  (ellipsis)
    "\u00e2\u20ac\u00a2|"       # â€¢  (bullet)
    "\u00c3\u00a9|"             # Ã©
    "\u00c3\u00a8|"             # Ã¨
    "\u00c3\u00b1|"             # Ã±
    "\u00c3\u00bc|"             # Ã¼
    "\u00c2\u00a0"              # Â<nbsp>
)
ENCODING_PATTERNS = [
    (re.compile(_MOJIBAKE), "mojibake"),
    (re.compile(r"&amp;(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);"), "double-encoded-entity"),
]

# Unclosed/unbalanced constructs to spot in text.
UNCLOSED_PATTERNS = [
    (re.compile(r"\]\([^)]*$", re.M), "unterminated-md-link"),
    (re.compile(r"!\[[^\]]*$", re.M), "unterminated-md-image"),
]


@dataclass
class Finding:
    category: str
    detail: str
    snippet: str = ""
    location: str = ""  # css-ish path, heading chain, etc.

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IssueReport:
    number: int
    path: str
    subject: str = ""
    findings: list[Finding] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)

    def add(self, cat: str, detail: str, snippet: str = "", location: str = "") -> None:
        self.findings.append(Finding(cat, detail, snippet, location))

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "path": self.path,
            "subject": self.subject,
            "findings": [f.to_dict() for f in self.findings],
        }


def list_issues() -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for child in SITE_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            num = int(child.name)
        except ValueError:
            continue
        idx = child / "index.html"
        if idx.exists():
            out.append((num, idx))
    out.sort(key=lambda x: x[0])
    return out


def text_of(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def trim(s: str, n: int = 140) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def check_template_tags(content_html: str, rep: IssueReport) -> None:
    for pat, kind in TEMPLATE_TAG_PATTERNS:
        for m in pat.finditer(content_html):
            rep.add(
                "template-tag-leak",
                f"{kind}: {m.group(0)!r}",
                snippet=trim(content_html[max(0, m.start() - 40): m.end() + 40]),
            )


def check_encoding(content_html: str, rep: IssueReport) -> None:
    for pat, kind in ENCODING_PATTERNS:
        seen = set()
        for m in pat.finditer(content_html):
            key = m.group(0)
            if key in seen:
                continue
            seen.add(key)
            rep.add(
                "encoding",
                f"{kind}: {key!r}",
                snippet=trim(content_html[max(0, m.start() - 40): m.end() + 40]),
            )


def check_unclosed(content_text: str, rep: IssueReport) -> None:
    for pat, kind in UNCLOSED_PATTERNS:
        for m in pat.finditer(content_text):
            rep.add(
                "unclosed-construct",
                kind,
                snippet=trim(m.group(0)),
            )


def walk_text_nodes(node) -> Iterable[NavigableString]:
    for desc in node.descendants:
        if isinstance(desc, NavigableString):
            # Skip text inside <a>, <code>, <pre>, <script>, <style>
            p = desc.parent
            skip = False
            while p is not None and getattr(p, "name", None):
                if p.name in ("a", "code", "pre", "script", "style"):
                    skip = True
                    break
                p = p.parent
            if not skip:
                yield desc


def check_bare_urls(content_soup, rep: IssueReport) -> None:
    seen: set[str] = set()
    for node in walk_text_nodes(content_soup):
        text = str(node)
        for m in BARE_URL_RE.finditer(text):
            url = m.group(0)
            if url in seen:
                continue
            seen.add(url)
            rep.add(
                "bare-url",
                url,
                snippet=trim(text[max(0, m.start() - 30): m.end() + 30]),
            )


def check_headers(content_soup, rep: IssueReport) -> None:
    headings = content_soup.find_all(re.compile(r"^h[1-6]$"))
    if not headings:
        return

    levels = [int(h.name[1]) for h in headings]
    has_any_h2 = 2 in levels
    has_any_h3 = 3 in levels

    prev_level = 1  # H1 is the page title; body should start at H2
    saw_h2 = False
    for h in headings:
        level = int(h.name[1])
        text = text_of(h)
        if level == 1:
            rep.add(
                "header-hierarchy",
                "H1 in body (only page title should be H1)",
                snippet=trim(text),
            )
        if not h.get("id") and level in (2, 3):
            rep.add(
                "header-hierarchy",
                f"{h.name.upper()} without id (won't link from TOC)",
                snippet=trim(text),
            )
        # Level skip detection: e.g. going directly from H2 to H4 mid-body.
        # Skip the "H1→H3" case when we're going to flag it as orphan-H3
        # below (avoids double-counting the same underlying problem).
        skip_level_skip = (
            level == 3
            and prev_level == 1
            and not saw_h2
            and has_any_h3
        )
        if prev_level and level - prev_level > 1 and level > 2 and not skip_level_skip:
            rep.add(
                "header-hierarchy",
                f"level-skip H{prev_level}→{h.name.upper()}",
                snippet=trim(text),
            )
        if level == 3 and not saw_h2 and not has_any_h2:
            # Entire issue has no H2 at all — Tinyletter-era "all H3 links"
            # pattern. Flag once at the first H3 and continue.
            if not any(f.detail.startswith("issue has no H2") for f in rep.findings):
                rep.add(
                    "header-hierarchy",
                    "issue has no H2 sections (all H3 links) — TOC ignores orphan H3s",
                    snippet=trim(text),
                )
        elif level == 3 and not saw_h2 and has_any_h2:
            # Issue has H2 sections but this H3 appears BEFORE the first H2
            # — true orphan. Flag each occurrence.
            rep.add(
                "header-hierarchy",
                "H3 before first H2 (orphan subheading)",
                snippet=trim(text),
            )
        if level == 2:
            saw_h2 = True
        prev_level = level


def check_images(content_soup, rep: IssueReport) -> None:
    for img in content_soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            rep.add("missing-image-src", "<img> with no src", snippet=trim(str(img)))
            continue
        rep.image_urls.append(src)
        for host in LEGACY_IMAGE_HOSTS:
            if host in src:
                rep.add(
                    "legacy-host",
                    f"image references {host}",
                    snippet=trim(src),
                )
                break


def check_empty_links(content_soup, rep: IssueReport) -> None:
    for a in content_soup.find_all("a"):
        href = (a.get("href") or "").strip()
        text = text_of(a)
        inner_img = a.find("img")
        if not text and not inner_img:
            rep.add("empty-link", f"empty <a href={href!r}>", snippet=trim(str(a)))
        if href in ("", "#"):
            # '#' used by stripped tags (unsubscribe_url etc.) — only flag if text suggests content
            if text and text.lower() not in ("unsubscribe", "manage subscription", "manage"):
                rep.add(
                    "empty-link",
                    f"anchor href={href!r} (placeholder)",
                    snippet=trim(text),
                )


PROSE_BRACKET_RE = re.compile(
    r"^\[(?:"
    r"\s*\d+\s*|"             # footnote-like [1]
    r"\s*[a-z]\s*|"           # single letter [a]
    r"\s*\.{3}\s*|"           # [...]
    r"\s*\u2026\s*|"          # [ellipsis char]
    r"sic|updated|correction|note|source|citation needed|edit|added|emphasis (?:added|mine)"
    r"|source: .+"
    r")\]$",
    re.I,
)


def check_malformed_markdown(content_text: str, rep: IssueReport) -> None:
    # Unpaired bold/italic run — very rough heuristic
    strong_runs = content_text.count("**")
    if strong_runs and strong_runs % 2 == 1:
        rep.add("malformed-markdown", f"odd count of '**' ({strong_runs})")
    # Look for "[text]" immediately followed by space/EOL (no `(url)` after).
    leftover = re.findall(r"\[[^\]\n]{1,80}\](?!\()", content_text)
    # Drop prose-style brackets: footnotes, single letters, elisions, editorial asides.
    real: list[str] = []
    for m in leftover:
        if m.lower().startswith(("[^", "[image:", "[video:", "[audio:")):
            continue
        if PROSE_BRACKET_RE.match(m):
            continue
        real.append(m)
    if real:
        rep.add(
            "malformed-markdown",
            f"bracketed text with no link ({len(real)} occurrence{'s' if len(real) > 1 else ''})",
            snippet=trim(real[0]),
        )


def check_empty_body(content_soup, rep: IssueReport) -> None:
    text = text_of(content_soup)
    if len(text) < 120:
        rep.add("empty-body", f"issue body is only {len(text)} chars", snippet=trim(text))


def audit_issue(num: int, path: Path) -> IssueReport:
    rep = IssueReport(number=num, path=str(path.relative_to(REPO_ROOT)))
    try:
        html = path.read_text(encoding="utf-8")
    except Exception as e:
        rep.add("read-error", f"could not read: {e}")
        return rep

    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.select_one(".issue-header h1")
    if h1:
        rep.subject = text_of(h1)

    content = soup.select_one(".issue-content")
    if not content:
        rep.add("empty-body", "no .issue-content element found")
        return rep

    content_html = str(content)
    content_text = content.get_text("\n")

    check_template_tags(content_html, rep)
    check_encoding(content_html, rep)
    check_unclosed(content_text, rep)
    check_bare_urls(content, rep)
    check_headers(content, rep)
    check_images(content, rep)
    check_empty_links(content, rep)
    check_malformed_markdown(content_text, rep)
    check_empty_body(content, rep)

    return rep


def head_check(client: httpx.Client, url: str) -> tuple[str, int | None, str]:
    """Return (url, status_code, error). status_code=None on network error."""
    try:
        r = client.head(url, follow_redirects=True, timeout=8.0)
        if r.status_code == 405 or r.status_code == 403:
            # Some CDNs reject HEAD; retry with GET (range=1)
            r = client.get(url, follow_redirects=True, timeout=8.0,
                           headers={"Range": "bytes=0-0"})
        return url, r.status_code, ""
    except Exception as e:
        return url, None, type(e).__name__ + ": " + str(e)[:120]


def check_broken_images(reports: list[IssueReport]) -> dict[str, tuple[int | None, str]]:
    urls: set[str] = set()
    for rep in reports:
        for u in rep.image_urls:
            if u.startswith("http://") or u.startswith("https://"):
                urls.add(u)
    print(f"[audit] HEAD-checking {len(urls)} unique image URLs...", flush=True)
    results: dict[str, tuple[int | None, str]] = {}
    with httpx.Client(
        headers={"User-Agent": "weekly-thingelstad-audit/1.0"},
        http2=False,
    ) as client:
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {pool.submit(head_check, client, u): u for u in urls}
            for i, fut in enumerate(as_completed(futures), 1):
                url, status, err = fut.result()
                results[url] = (status, err)
                if i % 50 == 0:
                    print(f"[audit]   {i}/{len(urls)} checked", flush=True)
    return results


def attach_broken_images(reports: list[IssueReport], results: dict[str, tuple[int | None, str]]) -> None:
    for rep in reports:
        seen: set[str] = set()
        for u in rep.image_urls:
            if u in seen or not u.startswith(("http://", "https://")):
                continue
            seen.add(u)
            status, err = results.get(u, (None, "not-checked"))
            if status is None:
                rep.add("broken-image", f"network error: {err}", snippet=trim(u))
            elif status >= 400:
                rep.add("broken-image", f"HTTP {status}", snippet=trim(u))


CATEGORY_NOTES = {
    "template-tag-leak": "Buttondown/Mailchimp template tags that survived HTML transform.",
    "bare-url": "URLs rendered as plain text (not wrapped in <a>). Usually MailChimp-era issues.",
    "header-hierarchy": "Headings that break the TOC (only H2/H3 with ids become TOC entries).",
    "broken-image": "Image HEAD/GET returned non-2xx or timed out. Verify host is still serving.",
    "missing-image-src": "<img> tag with no src — likely a rendering/source bug.",
    "empty-link": "<a> tag with no visible text/children — usually template artifacts.",
    "malformed-markdown": "Odd bold markers or bracketed text that looks like a link lost its URL. Low-confidence.",
    "encoding": "Mojibake or double-encoded HTML entities in rendered HTML.",
    "legacy-host": "Image references a known-dead CDN (MailChimp/Tinyletter). Probably already broken.",
    "empty-body": "Rendered body is virtually empty — possible template failure.",
    "unclosed-construct": "Unbalanced markdown (unterminated link/image). Real breakage.",
    "read-error": "Could not read the HTML file.",
}


def broken_image_summary(reports: list[IssueReport]) -> list[str]:
    """Build a 'broken images grouped by host' section."""
    import urllib.parse as _up
    from collections import defaultdict

    by_host: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in reports:
        for f in r.findings:
            if f.category != "broken-image":
                continue
            url = f.snippet
            try:
                host = _up.urlparse(url).netloc or "(unknown)"
            except Exception:
                host = "(unknown)"
            by_host[host].append((r.number, url, f.detail))

    if not by_host:
        return []

    lines: list[str] = []
    lines.append("## Broken images by host")
    lines.append("")
    lines.append("Unique URLs per host, with the issues that reference them. Verify each host before deciding how to remediate (re-upload, 301, or remove).")
    lines.append("")
    for host in sorted(by_host, key=lambda k: -len(by_host[k])):
        entries = by_host[host]
        # Dedupe by URL
        unique_urls: dict[str, set[int]] = {}
        url_status: dict[str, str] = {}
        for num, url, detail in entries:
            unique_urls.setdefault(url, set()).add(num)
            url_status[url] = detail
        lines.append(f"### `{host}` — {len(entries)} refs, {len(unique_urls)} unique URLs, {len({n for es in entries for n, *_ in [es]})} issues")
        lines.append("")
        lines.append("| Issues | Status | URL |")
        lines.append("|---|---|---|")
        for url, nums in sorted(unique_urls.items(), key=lambda kv: (sorted(kv[1])[0], kv[0])):
            nums_s = ", ".join(f"#{n}" for n in sorted(nums))
            url_disp = url if len(url) < 90 else url[:87] + "…"
            lines.append(f"| {nums_s} | {url_status[url]} | `{url_disp}` |")
        lines.append("")
    return lines


def write_reports(reports: list[IssueReport]) -> None:
    relevant = [r for r in reports if r.findings]

    json_path = OUT_DIR / "archive-audit.json"
    import datetime as _dt
    json_path.write_text(
        json.dumps(
            {
                "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "total_issues": len(reports),
                "issues_with_findings": len(relevant),
                "reports": [r.to_dict() for r in reports],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[audit] wrote {json_path}", flush=True)

    # Category tally + affected issues per category
    tally: dict[str, int] = {}
    by_cat: dict[str, list[IssueReport]] = {}
    for r in reports:
        seen_cats: set[str] = set()
        for f in r.findings:
            tally[f.category] = tally.get(f.category, 0) + 1
            if f.category not in seen_cats:
                by_cat.setdefault(f.category, []).append(r)
                seen_cats.add(f.category)

    lines: list[str] = []
    lines.append("# Archive Audit Report")
    lines.append("")
    lines.append("Generated from `_site/archive/*/index.html` — the user-facing rendered HTML.")
    lines.append("")
    lines.append(f"- Total issues scanned: **{len(reports)}**")
    lines.append(f"- Issues with at least one finding: **{len(relevant)}**")
    lines.append("")
    lines.append("## Summary by category")
    lines.append("")
    lines.append("| Category | Findings | Issues affected | Notes |")
    lines.append("|---|---:|---:|---|")
    for cat in sorted(tally, key=lambda k: (-tally[k], k)):
        note = CATEGORY_NOTES.get(cat, "")
        lines.append(f"| `{cat}` | {tally[cat]} | {len(by_cat.get(cat, []))} | {note} |")
    lines.append("")

    lines.extend(broken_image_summary(reports))

    # Category cross-reference: list affected issue numbers per category
    lines.append("## Affected issues by category")
    lines.append("")
    for cat in sorted(by_cat, key=lambda k: (-len(by_cat[k]), k)):
        nums = sorted({r.number for r in by_cat[cat]})
        lines.append(f"### `{cat}` — {len(nums)} issues")
        lines.append("")
        lines.append(", ".join(f"[#{n}](#issue-{n})" for n in nums))
        lines.append("")

    # Per-issue detail
    lines.append("## Per-issue findings")
    lines.append("")
    for r in relevant:
        cats = sorted({f.category for f in r.findings})
        lines.append(f"### Issue {r.number} — {r.subject}")
        lines.append("")
        lines.append(f"<a id=\"issue-{r.number}\"></a>")
        lines.append("")
        lines.append(f"- URL: `/archive/{r.number}/`")
        lines.append(f"- File: `{r.path}`")
        lines.append(f"- Categories: {', '.join('`' + c + '`' for c in cats)}")
        lines.append("")
        # Group findings by category for readability within the issue
        by_cat_in_issue: dict[str, list[Finding]] = {}
        for f in r.findings:
            by_cat_in_issue.setdefault(f.category, []).append(f)
        for cat in cats:
            lines.append(f"**`{cat}`**")
            lines.append("")
            for f in by_cat_in_issue[cat]:
                snip = f.snippet.replace("`", "´") if f.snippet else ""
                if snip:
                    lines.append(f"- {f.detail} — `{snip}`")
                else:
                    lines.append(f"- {f.detail}")
            lines.append("")

    md_path = OUT_DIR / "archive-audit.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[audit] wrote {md_path}", flush=True)


def main() -> None:
    issues = list_issues()
    print(f"[audit] scanning {len(issues)} issues...", flush=True)
    reports: list[IssueReport] = []
    for i, (num, path) in enumerate(issues, 1):
        reports.append(audit_issue(num, path))
        if i % 50 == 0:
            print(f"[audit]   parsed {i}/{len(issues)}", flush=True)

    results = check_broken_images(reports)
    attach_broken_images(reports, results)

    write_reports(reports)

    # Short console summary
    tally: dict[str, int] = {}
    for r in reports:
        for f in r.findings:
            tally[f.category] = tally.get(f.category, 0) + 1
    print("[audit] summary:", flush=True)
    for cat in sorted(tally, key=lambda k: (-tally[k], k)):
        print(f"  {cat:24s} {tally[cat]}", flush=True)


if __name__ == "__main__":
    main()
