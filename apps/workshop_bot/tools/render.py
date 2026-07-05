"""Render markdown to standalone, self-contained HTML pages.

The DB is the draft — the S3 ``draft.html`` preview (and its
editorial-review drawer) is retired. What lives here now:

- ``markdown_to_html_page`` — the styled page the web app's live
  production preview serves (markdown → CSS'd article, optional banner /
  meta block / block-marker stripping). No JS, no remote assets.
- ``review_target_legend`` — the anchored-comment target IDs Eddy's
  on-demand review uses (``editorial_comments`` rows surfaced on the web
  production page), derived from current DB state.
- The option-cards pages (subject / haiku / CTA pickers) and the
  side-by-side reorder-proposal page — both still uploaded to the issue
  workspace via ``s3.write_issue_html`` (no-cache + CDN invalidation).
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Optional

from . import issue_items, s3
from .content import draft as draft_mod

logger = logging.getLogger("workshop.render")

_BLOCK_MARKER_RE = re.compile(r"<!--\s*/?block:[a-z0-9_-]+\s*-->\n?", re.IGNORECASE)
_SECTION_LABELS = {
    "intro": "Intro",
    "currently": "Currently",
    "cover": "Cover",
    "notable": "Notable section",
    "journal": "Journal section",
    "brief": "Briefly section",
    "outro": "Outro",
    "haiku": "Haiku / closing",
}

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
  color: var(--wt-accent-deep); padding: 10px 14px; border-radius: 3px; margin: 0 0 24px;
}
.banner-links { display: block; margin-top: 6px; font-size: 11.5px; }
.banner-links a { color: var(--wt-accent-deep); text-decoration: none; border-bottom: 1px dotted currentColor; }
.banner-links a:hover { color: var(--wt-accent); border-bottom-style: solid; }
.banner-links .sep { opacity: 0.5; padding: 0 6px; }
dl.meta {
  margin: 0 0 32px; padding: 0;
  border-top: 1px solid var(--wt-line-soft);
  border-bottom: 1px solid var(--wt-line-soft);
  padding: 14px 0 16px;
}
dl.meta dt {
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--wt-muted);
  margin: 0 0 4px; padding: 0;
}
dl.meta dt + dd { margin-top: 0; }
dl.meta dd {
  margin: 0 0 14px; padding: 0;
  font-family: var(--wt-serif); font-size: 18px; line-height: 1.4;
  color: var(--wt-ink);
}
dl.meta dd:last-child { margin-bottom: 0; }
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
{banner}{meta}<article>
{body}
</article>
</body>
</html>
"""


def review_target_legend(*, issue_number: int,
                         section_status: Optional[dict] = None) -> str:
    """Return the target IDs Eddy can use for anchored review comments
    (``editorial_comments`` rows surfaced on the web production page).

    The list combines:

    - Section-level ids (``intro``, ``currently``, ``cover``, ``notable``,
      ``journal``, ``brief``, ``outro``, ``haiku``) — derived from DB
      state (``draft.section_status`` + the content store for ``outro``);
      a section only shows up when it has content.
    - Per-item ids (``n1``/``b2``/``j3``, etc.) — derived from
      ``issue_items`` rows in current position order, with the
      section's letter as the prefix.

    ``section_status`` lets a caller that already computed
    ``draft_mod.section_status(issue_number)`` pass it in (it does an S3
    listing + a body render); omitted, it's computed here.
    """
    from . import content_store

    n = int(issue_number)
    st = section_status if section_status is not None else draft_mod.section_status(n)
    st_sections = st.get("sections") or {}
    outro_body = content_store.read_issue(n, "outro.md")
    present = {
        "intro": bool(st.get("intro_present")),
        "currently": bool(st.get("currently_present")),
        "cover": bool(st.get("cover_present")),
        "notable": bool((st_sections.get("notable") or {}).get("present")),
        "journal": bool((st_sections.get("journal") or {}).get("present")),
        "brief": bool((st_sections.get("brief") or {}).get("present")),
        "outro": bool(outro_body and outro_body.strip()),
        "haiku": bool(st.get("haiku_present")),
    }
    lines: list[str] = []
    for name in draft_mod.SECTION_BLOCKS:
        if present.get(name):
            lines.append(f"- `{name}` — {_SECTION_LABELS.get(name, name)}")
    notable_rows = issue_items.list_items(
        int(issue_number), section="notable", include_promoted=False,
    )
    for i, row in enumerate(notable_rows, start=1):
        title = (row.get("title") or row.get("url") or "(untitled)").strip()
        lines.append(f"- `n{i}` — Notable: {title}")
    brief_rows = issue_items.list_items(
        int(issue_number), section="brief", include_promoted=False,
    )
    for i, row in enumerate(brief_rows, start=1):
        title = (row.get("title") or row.get("url") or "(untitled)").strip()
        lines.append(f"- `b{i}` — Briefly: {title}")
    journal_rows = issue_items.list_items(
        int(issue_number), section="journal", include_promoted=False,
    )
    for i, row in enumerate(journal_rows, start=1):
        title = (row.get("title") or "").strip()
        meta = row.get("metadata") or {}
        label = (meta.get("label") if isinstance(meta, dict) else "") or ""
        display = title or label or (row.get("url") or "")
        lines.append(f"- `j{i}` — Journal: {display}")
    return "\n".join(lines) if lines else "- No precise review targets are available."


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


def _render_banner(subtitle: Optional[str],
                   convenience_links: Optional[list[tuple[str, str]]]) -> str:
    """Build the small mono-uppercase status banner that sits above the
    article. ``subtitle`` is the existing one-line "DRAFT · WT… · …"
    summary; ``convenience_links`` is an optional list of ``(label, url)``
    pairs surfaced as a second line of cross-links (e.g. "↗ buttondown.md
    · ↗ archive.md · ↗ transcript-full.txt").
    """
    if not subtitle and not convenience_links:
        return ""
    parts = [_html.escape(subtitle)] if subtitle else []
    if convenience_links:
        link_html = '<span class="sep">·</span>'.join(
            f' <a href="{_html.escape(url, quote=True)}">↗ {_html.escape(label)}</a> '
            for label, url in convenience_links
        )
        parts.append(f'<span class="banner-links">{link_html}</span>')
    return f'<p class="banner">{"".join(parts)}</p>\n'


def _render_meta(meta: Optional[dict]) -> str:
    """Build the Subject / Description definition list that renders above
    the article body. ``meta`` is a dict — only the keys that are present
    and non-empty get rendered (so a fresh issue without a subject yet
    just doesn't show that row). Empty / None → no block at all."""
    if not meta:
        return ""
    rows: list[tuple[str, str]] = []
    for key, label in (("subject", "Subject"), ("description", "Description")):
        value = (meta.get(key) or "").strip() if isinstance(meta, dict) else ""
        if value:
            rows.append((label, value))
    if not rows:
        return ""
    items = "\n".join(
        f"  <dt>{_html.escape(label)}</dt>\n  <dd>{_html.escape(value)}</dd>"
        for label, value in rows
    )
    return f'<dl class="meta">\n{items}\n</dl>\n'


def markdown_to_html_page(md: str, *, title: str, subtitle: Optional[str] = None,
                          convenience_links: Optional[list[tuple[str, str]]] = None,
                          meta: Optional[dict] = None,
                          strip_block_markers: bool = False) -> str:
    """Wrap ``md`` (rendered to HTML) in a standalone, self-contained page.
    If ``strip_block_markers``, the ``<!-- block:X -->`` comments are
    removed first. ``subtitle``, if given, renders as a small banner above
    the content (used to mark drafts as work-in-progress).
    ``convenience_links`` (an optional list of ``(label, url)`` pairs)
    renders as a second line of cross-links in the same banner.
    ``meta`` (an optional ``{"subject": …, "description": …}`` dict)
    renders as a definition list between the banner and the article
    body.
    """
    src = md or ""
    if strip_block_markers:
        src = _BLOCK_MARKER_RE.sub("", src)
        src = re.sub(r"\n{3,}", "\n\n", src).strip() + "\n"
    body = _markdown_to_html(src)
    banner = _render_banner(subtitle, convenience_links)
    meta_block = _render_meta(meta)
    return _PAGE.format(
        title=_html.escape(title), css=_CSS, banner=banner, meta=meta_block,
        body=body,
    )


# ---------- option-cards page (subject picker, etc.) ----------
#
# The existing Discord reaction loop posts numbered options in a chat
# message — fine for haiku (short lines) but cramped for subject lines
# (long enough that Discord wraps mid-line) and impossible for the
# reorder pass (3 lists × 12 items). The option-cards page is
# the HTML side of the same pick UI: each option lands in its own
# card, with a stable card number that matches the 1️⃣–5️⃣ reactions
# in Discord, and a "copy" button so Jamie can lift the text into
# another window if he wants to compare or hand-edit.
#
# Same self-contained-HTML approach as the draft preview — one file,
# CSS inline, no external dependencies. The page deliberately does
# NOT have its own pick affordance: picks still flow through Discord
# reactions so the existing await_choice + refresh-loop plumbing
# stays in charge.

_OPTION_CARDS_CSS = """\
:root {
  color-scheme: light dark;
  --wt-bg: #fcfcfa; --wt-ink: #14181f; --wt-ink-soft: #3d4654; --wt-muted: #7d8694;
  --wt-line: #e6ebf2; --wt-line-soft: #f0f3f8;
  --wt-accent: #1f6fd6; --wt-accent-deep: #134d99; --wt-accent-soft: #e1edff;
  --wt-sans: "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --wt-serif: "Source Serif 4", "Charter", "Iowan Old Style", Cambria, Georgia, serif;
  --wt-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  font-family: var(--wt-sans); font-size: 17px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  max-width: 760px; margin: 0 auto; padding: 32px 28px 64px;
  color: var(--wt-ink); background: var(--wt-bg);
}
h1 {
  font-family: var(--wt-serif); font-weight: 500; font-size: 28px;
  letter-spacing: -0.015em; line-height: 1.2;
  margin: 0 0 4px; padding: 0;
}
.subtitle {
  font-family: var(--wt-mono); font-size: 12px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--wt-muted); margin: 0 0 28px;
}
.hint {
  font-family: var(--wt-mono); font-size: 12px; letter-spacing: 0.04em;
  background: var(--wt-accent-soft); border-left: 3px solid var(--wt-accent);
  color: var(--wt-accent-deep); padding: 10px 14px; border-radius: 3px;
  margin: 0 0 24px;
}
.card {
  border: 1px solid var(--wt-line); border-radius: 6px;
  padding: 18px 22px; margin: 0 0 16px;
  background: var(--wt-bg); position: relative;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.card:hover { border-color: var(--wt-accent); box-shadow: 0 1px 6px rgba(31, 111, 214, 0.08); }
.card-head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; margin: 0 0 10px;
}
.card-num {
  font-family: var(--wt-mono); font-size: 13px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--wt-accent-deep);
  background: var(--wt-accent-soft); padding: 2px 10px; border-radius: 999px;
}
.card-copy {
  cursor: pointer; border: 1px solid var(--wt-line);
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 4px 10px; border-radius: 999px;
  background: transparent; color: var(--wt-accent-deep);
}
.card-copy:hover { background: var(--wt-accent-soft); border-color: var(--wt-accent); }
.card.card-copied { border-color: #2da44e; box-shadow: 0 1px 6px rgba(45, 164, 78, 0.16); }
.card.card-copied .card-copy { color: #1a7f37; border-color: #2da44e; }
.card-body { font-family: var(--wt-serif); font-size: 19px; line-height: 1.4; white-space: pre-wrap; }
.card-body.card-body-mono { font-family: var(--wt-mono); font-size: 14px; line-height: 1.5; }
@media (max-width: 600px) {
  body { padding: 22px 16px 48px; font-size: 16px; }
  h1 { font-size: 24px; }
  .card { padding: 14px 16px; }
  .card-body { font-size: 17px; }
}
@media (prefers-color-scheme: dark) {
  :root {
    --wt-bg: #15171a; --wt-ink: #dfe2e6; --wt-ink-soft: #aab0b8; --wt-muted: #828a94;
    --wt-line: #2c2f34; --wt-line-soft: #23262a;
    --wt-accent: #6ea8fe; --wt-accent-deep: #9cc2ff; --wt-accent-soft: #1d2733;
  }
}
"""

_OPTION_CARDS_SCRIPT = """\
<script>(function(){
Array.prototype.forEach.call(document.querySelectorAll('.card-copy'),function(btn){
  btn.addEventListener('click',function(e){
    e.stopPropagation();
    var card=btn.closest('.card');if(!card)return;
    var body=card.querySelector('.card-body');if(!body)return;
    var text=(body.textContent||'').trim();
    function done(){
      card.classList.add('card-copied');
      var prev=btn.textContent;btn.textContent='copied';
      setTimeout(function(){card.classList.remove('card-copied');btn.textContent=prev||'copy';},1300);
    }
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(done,function(){
        var range=document.createRange();range.selectNodeContents(body);
        var sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);
      });
    }else{
      var range=document.createRange();range.selectNodeContents(body);
      var sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);
    }
  });
});
})();</script>
"""


def option_cards_html(
    title: str,
    options: list[str],
    *,
    subtitle: Optional[str] = None,
    hint: Optional[str] = None,
    body_kind: str = "serif",  # 'serif' | 'mono'
) -> str:
    """Render an HTML page of clickable option cards (subject picker,
    haiku picker, etc.). Each card carries the option's 1-based number
    (matching the Discord 1️⃣–5️⃣ reactions) plus a copy-to-clipboard
    button.

    ``body_kind='mono'`` switches the card body to a monospace font —
    useful for haiku and CTA copy where line breaks matter visually.
    """
    body_class = "card-body" + (" card-body-mono" if body_kind == "mono" else "")
    cards: list[str] = []
    for i, opt in enumerate(options, start=1):
        text = _html.escape((opt or "").strip())
        cards.append(
            f'<article class="card" data-card-num="{i}">'
            f'<div class="card-head">'
            f'<span class="card-num">option {i}</span>'
            f'<button type="button" class="card-copy" aria-label="Copy option {i}">copy</button>'
            f'</div>'
            f'<div class="{body_class}">{text}</div>'
            f'</article>'
        )
    sub_html = (
        f'<p class="subtitle">{_html.escape(subtitle)}</p>' if subtitle else ""
    )
    hint_html = (
        f'<p class="hint">{_html.escape(hint)}</p>' if hint else ""
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
        f"<title>{_html.escape(title)}</title>\n"
        f"<style>{_OPTION_CARDS_CSS}</style>\n"
        "</head>\n<body>\n"
        f"<h1>{_html.escape(title)}</h1>\n"
        f"{sub_html}\n"
        f"{hint_html}\n"
        + "\n".join(cards)
        + "\n"
        + _OPTION_CARDS_SCRIPT
        + "</body>\n</html>\n"
    )


def render_and_upload_option_cards(
    issue_number: int,
    name: str,
    title: str,
    options: list[str],
    *,
    subtitle: Optional[str] = None,
    hint: Optional[str] = None,
    body_kind: str = "serif",
) -> Optional[str]:
    """Render the option-cards page and upload it to the issue's
    workspace (no-cache + CDN invalidation). Returns the public URL,
    or ``None`` on any failure — callers treat the HTML preview as a
    nice-to-have on top of the Discord pick flow.
    """
    try:
        page = option_cards_html(
            title=title, options=options,
            subtitle=subtitle, hint=hint, body_kind=body_kind,
        )
        res = s3.write_issue_html(int(issue_number), f"{name}.html", page)
        return res.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "render: couldn't write %s.html for #%s: %s",
            name, issue_number, exc,
        )
        return None


# ---------- reorder proposal page ----------
#
# Side-by-side current vs proposed view of Eddy's reorder
# editorial pass. Picks still flow through Discord ✅/❌/🔄 — this
# page only shows what's being approved, with SVG connector lines
# drawn between left-column and right-column items so the moves
# read at a glance. Items that didn't move get no line. Promoted
# items render in their declared featured position on the right
# with a strikethrough on their left-column entry. Membership-block
# markers appear inline on the right as small pills at the position
# Eddy declared.

_PROPOSAL_CSS = """\
:root {
  color-scheme: light dark;
  --wt-bg: #fcfcfa; --wt-ink: #14181f; --wt-ink-soft: #3d4654; --wt-muted: #7d8694;
  --wt-line: #e6ebf2; --wt-line-soft: #f0f3f8;
  --wt-accent: #1f6fd6; --wt-accent-deep: #134d99; --wt-accent-soft: #e1edff;
  --wt-warn: #b78a14; --wt-warn-soft: #fff4d6;
  --wt-move: #16a34a; --wt-move-soft: #d6f4e0;
  --wt-sans: "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --wt-serif: "Source Serif 4", "Charter", "Iowan Old Style", Cambria, Georgia, serif;
  --wt-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  font-family: var(--wt-sans); font-size: 16px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  margin: 0; padding: 28px 24px 64px;
  color: var(--wt-ink); background: var(--wt-bg);
}
h1 {
  font-family: var(--wt-serif); font-weight: 500; font-size: 26px;
  letter-spacing: -0.015em; margin: 0 0 6px;
}
.subtitle {
  font-family: var(--wt-mono); font-size: 11.5px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--wt-muted); margin: 0 0 18px;
}
.legend {
  display: flex; flex-wrap: wrap; gap: 14px;
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.04em;
  color: var(--wt-muted); margin: 0 0 20px;
}
.legend > span { display: inline-flex; align-items: center; gap: 6px; }
.legend .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.cols {
  display: grid; grid-template-columns: 1fr 1fr; gap: 36px;
  position: relative; z-index: 1;
}
.col h2 {
  font-family: var(--wt-mono); font-size: 12px; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--wt-muted);
  border-bottom: 1px solid var(--wt-line); padding-bottom: 8px; margin: 0 0 14px;
}
.col section { margin: 0 0 22px; }
.col section > h3 {
  font-family: var(--wt-serif); font-weight: 500; font-size: 16px;
  margin: 0 0 8px; color: var(--wt-ink);
}
.col ul { list-style: none; padding: 0; margin: 0; }
.item {
  position: relative;
  padding: 8px 12px; margin: 0 0 6px; border-radius: 5px;
  border: 1px solid var(--wt-line);
  display: flex; gap: 10px; align-items: baseline;
  background: var(--wt-bg);
  font-size: 14.5px; line-height: 1.35;
}
.item .syn {
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.04em;
  color: var(--wt-accent-deep); background: var(--wt-accent-soft);
  padding: 1px 6px; border-radius: 999px; flex: 0 0 auto;
}
.item .title {
  flex: 1 1 auto; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.item.moved { border-color: var(--wt-move); background: var(--wt-move-soft); }
.item.moved .syn { background: var(--wt-move); color: #fff; }
.item.promoted {
  text-decoration: line-through; color: var(--wt-muted);
  background: var(--wt-warn-soft); border-color: var(--wt-warn);
}
.item.promoted .syn { background: var(--wt-warn); color: #fff; }
.featured-section {
  margin-top: -2px; padding: 10px 14px; border: 1px dashed var(--wt-warn);
  background: var(--wt-warn-soft); border-radius: 5px;
}
.featured-section .featured-heading {
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--wt-warn); margin: 0 0 6px;
}
.marker {
  font-family: var(--wt-mono); font-size: 11px; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--wt-accent-deep);
  background: var(--wt-accent-soft); border: 1px dashed var(--wt-accent);
  padding: 4px 10px; border-radius: 999px; margin: 0 0 6px;
  display: inline-block;
}
#proposal-connectors {
  position: absolute; inset: 0; width: 100%; height: 100%;
  pointer-events: none; z-index: 0; overflow: visible;
}
#proposal-connectors path {
  fill: none; stroke: var(--wt-move); stroke-width: 1.5;
  stroke-linecap: round; opacity: 0.45;
}
#proposal-connectors path.up { stroke: var(--wt-accent); opacity: 0.45; }
.no-change-note {
  font-family: var(--wt-mono); font-size: 12px; letter-spacing: 0.04em;
  color: var(--wt-muted); padding: 6px 0; font-style: italic;
}
@media (max-width: 720px) {
  .cols { grid-template-columns: 1fr; }
  #proposal-connectors { display: none; }
}
@media (prefers-color-scheme: dark) {
  :root {
    --wt-bg: #15171a; --wt-ink: #dfe2e6; --wt-ink-soft: #aab0b8; --wt-muted: #828a94;
    --wt-line: #2c2f34; --wt-line-soft: #23262a;
    --wt-accent: #6ea8fe; --wt-accent-deep: #9cc2ff; --wt-accent-soft: #1d2733;
    --wt-warn: #f1c065; --wt-warn-soft: #3b2e10;
    --wt-move: #4ade80; --wt-move-soft: #112d1c;
  }
}
"""

_PROPOSAL_SCRIPT = """\
<script>(function(){
var svg=document.getElementById('proposal-connectors');
if(!svg)return;
function box(el){return el?el.getBoundingClientRect():null;}
function relTo(rect,base){return {x:rect.left-base.left,y:rect.top-base.top,w:rect.width,h:rect.height};}
function draw(){
  if(!svg)return;
  var cols=document.querySelector('.cols');if(!cols)return;
  var base=cols.getBoundingClientRect();
  svg.setAttribute('width',base.width);
  svg.setAttribute('height',Math.max(base.height,cols.scrollHeight));
  svg.innerHTML='';
  Array.prototype.forEach.call(document.querySelectorAll('[data-side="current"]'),function(left){
    var id=left.getAttribute('data-id');if(!id)return;
    var right=document.querySelector('[data-side="proposed"][data-id="'+id+'"]')
      ||document.querySelector('[data-side="featured"][data-id="'+id+'"]');
    if(!right)return;
    var lr=box(left),rr=box(right);if(!lr||!rr)return;
    var l=relTo(lr,base),r=relTo(rr,base);
    var x1=l.x+l.w,y1=l.y+l.h/2;
    var x2=r.x,y2=r.y+r.h/2;
    var direction=Math.abs(y2-y1)<6?'flat':(y2>y1?'down':'up');
    if(direction==='flat')return;
    var mid=x1+(x2-x1)/2;
    var path=document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d','M '+x1+' '+y1+' C '+mid+' '+y1+', '+mid+' '+y2+', '+x2+' '+y2);
    if(direction==='up')path.classList.add('up');
    svg.appendChild(path);
  });
}
window.addEventListener('load',draw);
window.addEventListener('resize',draw);
})();</script>
"""


def _proposal_item_html(
    *, side: str, synth_id: str, title: str, moved: bool,
) -> str:
    """One item row in the current-or-proposed column."""
    classes = ["item"]
    if moved and side != "current":
        classes.append("moved")
    return (
        f'<li class="{" ".join(classes)}" data-side="{side}" data-id="{synth_id}">'
        f'<span class="syn">{synth_id}</span>'
        f'<span class="title">{_html.escape(title)}</span>'
        f'</li>'
    )


def _proposal_section_html(
    *,
    side: str,
    section: str,
    label: str,
    items: list[dict],
    item_synth: dict,
    moved_ids: Optional[set[str]] = None,
) -> str:
    """Render one section's column (current or proposed). ``moved_ids``
    highlights items whose position changed between the two sides."""
    moved_ids = moved_ids or set()
    parts: list[str] = [f'<section><h3>{_html.escape(label)}</h3><ul>']
    for row in items:
        synth = item_synth[int(row["id"])]
        title = (row.get("title") or row.get("url") or "(untitled)").strip()
        parts.append(_proposal_item_html(
            side=side, synth_id=synth, title=title,
            moved=synth in moved_ids,
        ))
    parts.append('</ul></section>')
    return "".join(parts)


def reorder_proposal_html(
    *,
    issue_number: int,
    rows_by_section: dict[str, list[dict]],
    proposal: dict,
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
) -> str:
    """Build the side-by-side proposal page.

    ``rows_by_section`` is the current (pre-apply) order; ``proposal``
    is Eddy's JSON (``notable_order``, ``brief_order``). The page shows
    two columns — current on the left, proposed on the right — with SVG
    connector lines between matching items (per-item id-anchored).
    Items in the same position get no line.

    Legacy fields (``promotions``, ``membership_blocks``) are ignored
    here even if the LLM still emits them — promotions moved upstream
    to the micro.blog ``Featured`` tag, and membership-block placement
    is hardcoded at email-render time.
    """
    title = f"WT{int(issue_number)} — reorder proposal"
    section_labels = {"notable": "Notable", "brief": "Briefly", "journal": "Journal"}

    # moved-ids set per section — synth ids whose position changed between
    # current and proposed. Journal is never reordered.
    def _moved_for(section: str) -> set[str]:
        current = [row_to_synth[int(r["id"])] for r in rows_by_section.get(section, [])]
        order = proposal.get(f"{section}_order") or []
        moved: set[str] = set()
        for i, sid in enumerate(order):
            try:
                cur_idx = current.index(sid)
            except ValueError:
                continue
            if cur_idx != i:
                moved.add(sid)
        return moved

    cur_html: list[str] = []
    prop_html: list[str] = []
    for section in ("notable", "journal", "brief"):
        items = rows_by_section.get(section, [])
        label = section_labels.get(section, section.capitalize())
        cur_html.append(_proposal_section_html(
            side="current", section=section, label=label,
            items=items, item_synth=row_to_synth,
        ))
        # Build the proposed column. Journal is never reordered — fall back
        # to current row order so the proposed column shows items in their
        # natural publish-date sequence.
        order = proposal.get(f"{section}_order") or []
        if section == "journal" or not order:
            order = [row_to_synth[int(r["id"])] for r in items]
        by_synth = {row_to_synth[int(r["id"])]: r for r in items}
        ordered_rows = [by_synth[sid] for sid in order if sid in by_synth]
        prop_html.append(_proposal_section_html(
            side="proposed", section=section, label=label,
            items=ordered_rows, item_synth=row_to_synth,
            moved_ids=_moved_for(section),
        ))

    legend = (
        '<div class="legend">'
        '<span><span class="swatch" style="background:var(--wt-move);"></span>moved</span>'
        '</div>'
    )

    no_change = ""
    any_moved = any(_moved_for(s) for s in ("notable", "brief", "journal"))
    if not any_moved:
        no_change = '<p class="no-change-note">No changes proposed — current order stands.</p>'

    body = (
        f'<h1>{_html.escape(title)}</h1>'
        '<p class="subtitle">react ✅ / ❌ / 🔄 in #editorial</p>'
    )
    body += legend + no_change
    body += (
        '<div class="cols">'
        '<svg id="proposal-connectors" aria-hidden="true"></svg>'
        '<div class="col col-current"><h2>Current order</h2>'
        + "".join(cur_html)
        + '</div>'
        '<div class="col col-proposed"><h2>Proposed by Eddy</h2>'
        + "".join(prop_html)
        + '</div>'
        '</div>'
    )

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
        f"<title>{_html.escape(title)}</title>\n"
        f"<style>{_PROPOSAL_CSS}</style>\n"
        "</head>\n<body>\n"
        + body
        + "\n" + _PROPOSAL_SCRIPT
        + "</body>\n</html>\n"
    )


def render_and_upload_proposal(
    *,
    issue_number: int,
    rows_by_section: dict[str, list[dict]],
    proposal: dict,
    synth_to_row: dict[str, int],
    row_to_synth: dict[int, str],
) -> Optional[str]:
    """Upload the proposal page to ``final-proposal.html`` in the issue
    workspace. Returns the public URL; ``None`` on failure (caller
    treats the page as a nice-to-have on top of the Discord pick)."""
    try:
        page = reorder_proposal_html(
            issue_number=int(issue_number),
            rows_by_section=rows_by_section, proposal=proposal,
            synth_to_row=synth_to_row, row_to_synth=row_to_synth,
        )
        res = s3.write_issue_html(int(issue_number), "final-proposal.html", page)
        return res.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "render: couldn't write final-proposal.html for #%s: %s",
            issue_number, exc,
        )
        return None


# (``render_and_upload_html`` — the S3 draft.html preview writer — was
# retired with the update-draft job. The web app renders previews live via
# ``markdown_to_html_page``; the DB is the draft.)
