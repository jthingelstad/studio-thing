"""Render an issue's markdown to a standalone HTML preview page.

``update-draft`` / ``create-final`` / ``build-publish`` write a ``.md``;
they also write a ``.html`` twin so Jamie can pull the issue up in a
browser and see it "in progress" (or, for ``publish.html``, as it'll
ship). The page is self-contained — a small bit of CSS + JS, no remote
assets — and the ``.html`` is uploaded with ``Cache-Control: no-cache``
plus a CloudFront invalidation so the browser always sees the latest.

If a ``review_md`` is supplied (the ``update-draft`` HTML pass), it's
rendered into a slide-in drawer that's **hidden by default** and revealed
by a fixed "Show review" button — so the same shareable link reads as the
clean draft until someone toggles the editorial suggestions on.

``render_and_upload_html(issue, name, md, …)`` does the whole thing:
render → wrap → ``s3.write_issue_html`` (which sets the no-cache header
and invalidates the CDN path) → return the public URL (or None on any
failure, logged — the caller treats the preview as best-effort).
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Optional

from . import s3

logger = logging.getLogger("workshop.render")

_BLOCK_MARKER_RE = re.compile(r"<!--\s*/?block:[a-z0-9_-]+\s*-->\n?", re.IGNORECASE)

# Mirrors content/buttondown/newsletter/buttondown-email.css (the production
# email stylesheet) so the preview reads like a delivered issue: sans body,
# serif headings, mono meta, the brand blue, the section rhythm. Browsers
# may load the Google fonts; if not, the system fallbacks read similarly
# (same as the email).
_CSS = """\
:root {
  color-scheme: light dark;
  --wt-bg: #fcfcfa; --wt-ink: #14181f; --wt-ink-soft: #3d4654; --wt-muted: #7d8694;
  --wt-line: #e6ebf2; --wt-line-soft: #f0f3f8;
  --wt-accent: #1f6fd6; --wt-accent-deep: #134d99; --wt-accent-soft: #e1edff;
  --wt-sans: "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --wt-serif: "Source Serif 4", "Charter", "Iowan Old Style", "Sitka Text", Cambria, Georgia, serif;
  --wt-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  font-family: var(--wt-sans); font-size: 17px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  max-width: 680px; margin: 0 auto; padding: 32px 28px 64px;
  color: var(--wt-ink); background: var(--wt-bg);
  transition: margin 0.22s ease;
}
article > :first-child { margin-top: 0; }
h1, h2, h3, h4 {
  font-family: var(--wt-serif); font-weight: 500; letter-spacing: -0.015em;
  color: var(--wt-ink); line-height: 1.25; text-wrap: pretty;
}
h1 { font-size: 32px; line-height: 1.1; letter-spacing: -0.02em; margin: 0 0 8px;
     padding-bottom: 16px; border-bottom: 1px solid var(--wt-line); }
h2 { font-size: 24px; margin: 40px 0 12px; padding-top: 24px; border-top: 1px solid var(--wt-line-soft); }
h3 { font-size: 20px; line-height: 1.3; margin: 28px 0 8px; }
h4 { font-size: 17px; margin: 24px 0 6px; }
p { margin: 0 0 18px; color: var(--wt-ink); }
em, i { font-style: italic; } strong, b { font-weight: 600; }
a { color: var(--wt-accent); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--wt-accent-deep); }
ul, ol { padding-left: 24px; margin: 0 0 18px; }
li { line-height: 1.55; margin-bottom: 6px; }
li::marker { color: var(--wt-muted); }
img { max-width: 100%; height: auto; border-radius: 2px; display: block; margin: 18px 0; }
blockquote {
  margin: 18px 0 24px; padding: 4px 0 4px 20px; border-left: 3px solid var(--wt-accent);
  font-family: var(--wt-serif); font-style: italic; color: var(--wt-ink-soft);
}
blockquote p { color: var(--wt-ink-soft); margin-bottom: 6px; }
blockquote p:last-child { margin-bottom: 0; }
code { font-family: var(--wt-mono); font-size: 14px; background: var(--wt-line-soft); color: var(--wt-accent-deep); padding: 1px 6px; border-radius: 3px; }
pre { background: var(--wt-line-soft); border-left: 3px solid var(--wt-accent); padding: 16px 20px; overflow-x: auto; margin: 18px 0; }
pre code { background: transparent; color: var(--wt-ink); font-size: 13px; padding: 0; }
hr { border: none; border-top: 1px solid var(--wt-line); margin: 32px 0; }
.banner {
  font-family: var(--wt-mono); font-size: 12px; line-height: 1.4;
  text-transform: uppercase; letter-spacing: 0.08em;
  background: var(--wt-accent-soft); border-left: 4px solid var(--wt-accent);
  color: var(--wt-accent-deep); padding: 10px 14px; border-radius: 3px; margin: 0 0 32px;
}
/* Editorial-review drawer — hidden until "Show review" is pressed. */
#rv-toggle {
  position: fixed; top: 14px; right: 14px; z-index: 30; cursor: pointer;
  font-family: var(--wt-mono); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 8px 14px; border-radius: 999px; border: 1px solid var(--wt-accent);
  background: var(--wt-accent-soft); color: var(--wt-accent-deep);
}
#rv-toggle:hover { background: var(--wt-accent); color: #fff; }
#rv-panel {
  position: fixed; top: 0; right: 0; bottom: 0; width: min(440px, 94vw);
  overflow-y: auto; padding: 58px 24px 32px; z-index: 20;
  background: var(--wt-bg); border-left: 1px solid var(--wt-line);
  box-shadow: -10px 0 28px rgba(0, 0, 0, 0.12);
  transform: translateX(100%); transition: transform 0.22s ease;
}
body.rv-open #rv-panel { transform: translateX(0); }
/* When the drawer is open and there's room, left-align the draft so the
   review panel and the content are visible side by side instead of the
   panel sitting on top of the text. On narrow windows the panel overlays. */
@media (min-width: 880px) {
  body.rv-open {
    margin-left: 40px;
    margin-right: calc(min(440px, 94vw) + 40px);
  }
}
#rv-panel .rv-h {
  font-family: var(--wt-mono); font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--wt-accent); border: none; padding: 0; margin: 0 0 2px;
}
#rv-panel .rv-sub {
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--wt-muted); margin: 0 0 18px;
}
#rv-panel h2 { font-size: 18px; margin: 22px 0 6px; padding: 0; border: none; }
#rv-panel h3 { font-size: 15.5px; margin: 14px 0 4px; }
#rv-panel p, #rv-panel li { font-size: 14.5px; line-height: 1.55; }
#rv-panel ul, #rv-panel ol { padding-left: 20px; margin: 0 0 12px; }
#rv-panel blockquote { font-size: 14px; margin: 8px 0 12px; padding: 2px 0 2px 14px; }
@media (max-width: 600px) { #rv-panel { width: 94vw; } }
@media print { #rv-toggle, #rv-panel { display: none !important; } }

@media (max-width: 600px) {
  body { padding: 20px 18px 48px; font-size: 16px; }
  h1 { font-size: 26px; } h2 { font-size: 22px; } li { font-size: 16px; }
}
@media (prefers-color-scheme: dark) {
  :root {
    --wt-bg: #15171a; --wt-ink: #dfe2e6; --wt-ink-soft: #aab0b8; --wt-muted: #828a94;
    --wt-line: #2c2f34; --wt-line-soft: #23262a;
    --wt-accent: #6ea8fe; --wt-accent-deep: #9cc2ff; --wt-accent-soft: #1d2733;
  }
  code { color: #cdd9ff; }
}
"""

_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{review_chrome}{banner}<article>
{body}
</article>
{review_script}</body>
</html>
"""

# The review drawer's HTML (button + aside) — injected only when there's a
# review. ``{review_html}`` is the rendered review markdown.
_REVIEW_CHROME = """\
<button id="rv-toggle" type="button" aria-expanded="false">Show review</button>
<aside id="rv-panel" aria-label="Editorial review">
<p class="rv-h">Editorial review</p>
<p class="rv-sub">Suggestions only — the draft itself is unchanged.</p>
{review_html}
</aside>
"""

# Toggles ``body.rv-open`` and swaps the button label. Passed as a value
# (not literal in ``_PAGE``) so the braces don't trip ``str.format``.
_REVIEW_SCRIPT = (
    "<script>(function(){var b=document.getElementById('rv-toggle');if(!b)return;"
    "b.addEventListener('click',function(){"
    "var on=document.body.classList.toggle('rv-open');"
    "b.textContent=on?'Hide review':'Show review';"
    "b.setAttribute('aria-expanded',on?'true':'false');"
    "var p=document.getElementById('rv-panel');if(on&&p)p.scrollTop=0;});})();</script>\n"
)


def _markdown_to_html(md: str) -> str:
    """Render markdown → HTML. Uses Python-Markdown if available; falls back
    to a ``<pre>`` block of the raw source so the preview is still usable
    if the dependency is somehow missing."""
    try:
        import markdown  # python-markdown
    except ImportError:
        logger.warning("render: python-markdown not installed — preview will show raw source")
        return f"<pre>{_html.escape(md)}</pre>"
    # `smarty` gives the curly quotes / em-dashes the published issue has;
    # `extra` + `sane_lists` match the site's markdown handling closely enough.
    return markdown.markdown(md, extensions=["extra", "sane_lists", "smarty"], output_format="html5")


def markdown_to_html_page(md: str, *, title: str, subtitle: Optional[str] = None,
                          strip_block_markers: bool = False,
                          review_md: Optional[str] = None) -> str:
    """Wrap ``md`` (rendered to HTML) in a standalone, self-contained page.
    If ``strip_block_markers``, the ``<!-- block:X -->`` comments are
    removed first. ``subtitle``, if given, renders as a small banner above
    the content (used to mark drafts as work-in-progress). ``review_md``,
    if given, is rendered into a slide-in drawer that's hidden until the
    fixed "Show review" button is pressed."""
    src = md or ""
    if strip_block_markers:
        src = _BLOCK_MARKER_RE.sub("", src)
        src = re.sub(r"\n{3,}", "\n\n", src).strip() + "\n"
    body = _markdown_to_html(src)
    banner = f'<p class="banner">{_html.escape(subtitle)}</p>\n' if subtitle else ""
    if review_md and review_md.strip():
        review_chrome = _REVIEW_CHROME.format(review_html=_markdown_to_html(review_md))
        review_script = _REVIEW_SCRIPT
    else:
        review_chrome = review_script = ""
    return _PAGE.format(
        title=_html.escape(title), css=_CSS, banner=banner, body=body,
        review_chrome=review_chrome, review_script=review_script,
    )


def render_and_upload_html(
    issue_number: int,
    name: str,
    md: str,
    *,
    title: str,
    subtitle: Optional[str] = None,
    strip_block_markers: bool = False,
    review_md: Optional[str] = None,
) -> Optional[str]:
    """Render ``md`` to ``{name}.html`` in the issue workspace (no-cache +
    CDN invalidation) and return its public URL. Best-effort: returns None
    (logged) on any failure — the caller treats the HTML preview as
    optional."""
    try:
        page = markdown_to_html_page(
            md, title=title, subtitle=subtitle,
            strip_block_markers=strip_block_markers, review_md=review_md,
        )
        res = s3.write_issue_html(int(issue_number), f"{name}.html", page)
        return res.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.warning("render: couldn't write %s.html for #%s: %s", name, issue_number, exc)
        return None
