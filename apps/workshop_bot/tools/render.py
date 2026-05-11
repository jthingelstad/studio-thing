"""Render an issue's markdown to a standalone HTML preview page.

``update-draft`` / ``create-final`` / ``build-publish`` write a ``.md``;
they also write a ``.html`` twin so Jamie can pull the issue up in a
browser and see it "in progress" (or, for ``publish.html``, as it'll
ship). The page is self-contained — a small bit of CSS, no remote assets
— and the ``.html`` is uploaded with ``Cache-Control: no-cache`` plus a
CloudFront invalidation so the browser always sees the latest.

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

_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font: 1.05rem/1.65 "Iowan Old Style", "Source Serif 4", Georgia, "Times New Roman", serif;
  max-width: 44rem; margin: 2.5rem auto; padding: 0 1.25rem;
  color: #1f2328; background: #fcfcfa;
}
@media (prefers-color-scheme: dark) {
  body { color: #d6d8da; background: #161719; }
  a { color: #6ea8fe; }
  blockquote { color: #a9adb2; border-left-color: #3a3d40; }
  code, pre { background: #232528; }
  hr, .banner { border-color: #3a3d40; }
  .banner { background: #1d1f22; color: #a9adb2; }
}
h1, h2, h3, h4 { font-family: "Source Sans 3", "Helvetica Neue", Arial, sans-serif; line-height: 1.25; margin: 1.9em 0 .5em; }
h1 { font-size: 1.9rem; } h2 { font-size: 1.5rem; } h3 { font-size: 1.2rem; } h4 { font-size: 1.05rem; }
h2 { border-bottom: 1px solid currentColor; padding-bottom: .15em; opacity: .92; }
a { color: #1f6fd6; }
img { max-width: 100%; height: auto; border-radius: 6px; display: block; margin: 1em 0; }
blockquote { margin: 1em 0; padding: .1em 1em; border-left: 3px solid #d8dade; color: #555; }
code { font: .9em/1 "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; background: #f0f0ec; padding: .15em .35em; border-radius: 4px; }
pre { background: #f0f0ec; padding: .9em 1.1em; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
hr { border: none; border-top: 1px solid #d8dade; margin: 2em 0; }
.banner {
  font: .8rem/1.4 "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  text-transform: uppercase; letter-spacing: .04em;
  background: #fff7e6; border: 1px solid #e8d9b5; color: #6b5b2e;
  padding: .55em .85em; border-radius: 6px; margin-bottom: 2em;
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
{banner}<article>
{body}
</article>
</body>
</html>
"""


def _markdown_to_html(md: str) -> str:
    """Render markdown → HTML. Uses Python-Markdown if available; falls back
    to a ``<pre>`` block of the raw source so the preview is still usable
    if the dependency is somehow missing."""
    try:
        import markdown  # python-markdown
    except ImportError:
        logger.warning("render: python-markdown not installed — preview will show raw source")
        return f"<pre>{_html.escape(md)}</pre>"
    return markdown.markdown(md, extensions=["extra", "sane_lists"], output_format="html5")


def markdown_to_html_page(md: str, *, title: str, subtitle: Optional[str] = None,
                          strip_block_markers: bool = False) -> str:
    """Wrap ``md`` (rendered to HTML) in a standalone, self-contained page.
    If ``strip_block_markers``, the ``<!-- block:X -->`` comments are
    removed first. ``subtitle``, if given, renders as a small banner above
    the content (used to mark drafts as work-in-progress)."""
    src = md or ""
    if strip_block_markers:
        src = _BLOCK_MARKER_RE.sub("", src)
        src = re.sub(r"\n{3,}", "\n\n", src).strip() + "\n"
    body = _markdown_to_html(src)
    banner = f'<p class="banner">{_html.escape(subtitle)}</p>\n' if subtitle else ""
    return _PAGE.format(title=_html.escape(title), css=_CSS, banner=banner, body=body)


def render_and_upload_html(
    issue_number: int,
    name: str,
    md: str,
    *,
    title: str,
    subtitle: Optional[str] = None,
    strip_block_markers: bool = False,
) -> Optional[str]:
    """Render ``md`` to ``{name}.html`` in the issue workspace (no-cache +
    CDN invalidation) and return its public URL. Best-effort: returns None
    (logged) on any failure — the caller treats the HTML preview as
    optional."""
    try:
        page = markdown_to_html_page(
            md, title=title, subtitle=subtitle, strip_block_markers=strip_block_markers
        )
        res = s3.write_issue_html(int(issue_number), f"{name}.html", page)
        return res.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.warning("render: couldn't write %s.html for #%s: %s", name, issue_number, exc)
        return None
