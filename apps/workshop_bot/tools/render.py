"""Render an issue's markdown to a standalone HTML preview page.

``update-draft`` writes ``draft.md`` and a ``draft.html`` twin so Jamie
can pull the in-progress issue up in a browser. ``draft.html`` is the
only review surface — ``archive.md`` / ``buttondown.md`` / ``transcript/``
are ship-shaped artifacts for their destinations and have no rendered
HTML view. The page is self-contained — a small bit of CSS + JS, no
remote assets — and the ``.html`` is uploaded with ``Cache-Control:
no-cache`` plus a CloudFront invalidation so the browser always sees the
latest.

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

from . import issue_items, s3
from .content import draft as draft_mod

logger = logging.getLogger("workshop.render")

_BLOCK_MARKER_RE = re.compile(r"<!--\s*/?block:[a-z0-9_-]+\s*-->\n?", re.IGNORECASE)
_REVIEW_TARGET_RE = re.compile(
    r"<!--\s*target:([a-z0-9_-]+)\s*-->" r"|\[target:([a-z0-9_-]+)\]",
    re.IGNORECASE,
)
# Handle markers (``<!-- handle:E349-N1 -->``) are injected by
# ``update_draft._inject_handle_markers`` next to each target marker
# after the comment is stored. The renderer converts them into a
# visible badge + a copy-to-clipboard button so Jamie can paste the
# handle back into Discord to continue the conversation.
_REVIEW_HANDLE_RE = re.compile(
    r"<!--\s*handle:(E\d+-[A-Z]\d+)\s*-->",
    re.IGNORECASE,
)
_VALID_TARGET_RE = re.compile(r"^[a-z0-9_-]+$", re.IGNORECASE)
_VALID_HANDLE_RE = re.compile(r"^E\d+-[A-Z]\d+$", re.IGNORECASE)
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
.rv-anchor {
  display: block; position: relative; height: 0; width: 0; overflow: visible;
  scroll-margin-top: 24px;
}
.rv-target-active {
  outline: 2px solid color-mix(in srgb, var(--wt-accent) 54%, transparent);
  outline-offset: 5px; border-radius: 3px;
  background: color-mix(in srgb, var(--wt-accent-soft) 52%, transparent);
  transition: background 0.16s ease, outline-color 0.16s ease;
}
#rv-panel .rv-review-item {
  cursor: pointer; border-radius: 3px; transition: background 0.16s ease;
}
#rv-panel .rv-review-active {
  background: var(--wt-accent-soft);
}
#rv-panel .rv-target-ref { display: none; }
/* Handle badge — sits at the start of a review bullet, gives Jamie a
   stable ID (E349-N1) he can copy and paste into Discord to continue
   the conversation about that specific comment. */
#rv-panel .rv-handle {
  display: inline-flex; align-items: center; gap: 4px;
  margin: 0 8px 0 0; padding: 1px 6px 1px 8px;
  font-family: var(--wt-mono); font-size: 11.5px; letter-spacing: 0.02em;
  background: var(--wt-accent-soft); color: var(--wt-accent-deep);
  border-radius: 999px; vertical-align: baseline;
}
#rv-panel .rv-handle-text { font-weight: 600; }
#rv-panel .rv-handle-copy {
  cursor: pointer; border: 0; padding: 0 6px;
  font-family: var(--wt-mono); font-size: 10.5px; letter-spacing: 0.04em;
  text-transform: uppercase;
  background: transparent; color: var(--wt-accent);
  border-left: 1px solid color-mix(in srgb, var(--wt-accent) 30%, transparent);
}
#rv-panel .rv-handle-copy:hover { color: var(--wt-accent-deep); }
#rv-panel .rv-handle.rv-handle-copied { background: color-mix(in srgb, #2da44e 18%, var(--wt-accent-soft)); }
#rv-panel .rv-handle.rv-handle-copied .rv-handle-copy { color: #1a7f37; }
#rv-connectors {
  display: none; position: fixed; inset: 0; width: 100vw; height: 100vh;
  pointer-events: none; z-index: 25; overflow: visible;
}
body.rv-open #rv-connectors { display: block; }
#rv-connectors path {
  fill: none; stroke: var(--wt-accent); stroke-width: 2;
  stroke-linecap: round; opacity: 0.68;
}
@media (max-width: 600px) { #rv-panel { width: 94vw; } }
@media (max-width: 879px) { #rv-connectors { display: none !important; } }
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
{review_chrome}{review_connectors}
{banner}{meta}<article>
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
_REVIEW_SCRIPT = """\
<script>(function(){
var b=document.getElementById('rv-toggle');if(!b)return;
var panel=document.getElementById('rv-panel');
var svg=document.getElementById('rv-connectors');
var activeReview=null,activeTarget=null,activeId=null;
function byTarget(id){return document.querySelector('[data-review-anchor="'+id+'"]');}
function targetBox(anchor){
  if(!anchor)return null;
  var el=anchor.nextElementSibling||anchor.parentElement;
  while(el&&el.classList&&el.classList.contains('rv-anchor'))el=el.nextElementSibling;
  return el||anchor;
}
function clear(){
  if(activeReview)activeReview.classList.remove('rv-review-active');
  if(activeTarget)activeTarget.classList.remove('rv-target-active');
  if(svg)svg.innerHTML='';
  activeReview=activeTarget=null;activeId=null;
}
function draw(){
  if(!activeReview||!activeTarget||!svg||!document.body.classList.contains('rv-open')||window.innerWidth<880){if(svg)svg.innerHTML='';return;}
  var rr=activeReview.getBoundingClientRect();
  var tr=activeTarget.getBoundingClientRect();
  if(rr.bottom<0||rr.top>window.innerHeight||tr.bottom<0||tr.top>window.innerHeight){svg.innerHTML='';return;}
  var x1=tr.right+8,y1=tr.top+(Math.min(tr.height,80)/2);
  var x2=rr.left-10,y2=rr.top+(Math.min(rr.height,80)/2);
  var mid=x1+Math.max(48,(x2-x1)/2);
  svg.innerHTML='<path d="M '+x1+' '+y1+' C '+mid+' '+y1+', '+mid+' '+y2+', '+x2+' '+y2+'"></path>';
}
function activate(item,scroll){
  var id=item&&item.getAttribute('data-review-target');if(!id)return;
  var anchor=byTarget(id);if(!anchor)return;
  clear();
  activeReview=item;activeTarget=targetBox(anchor);activeId=id;
  activeReview.classList.add('rv-review-active');
  activeTarget.classList.add('rv-target-active');
  if(scroll&&activeTarget.scrollIntoView)activeTarget.scrollIntoView({block:'center',behavior:'smooth'});
  draw();
}
Array.prototype.forEach.call(document.querySelectorAll('#rv-panel .rv-target-ref'),function(ref){
  var id=ref.getAttribute('data-review-target');if(!id||!byTarget(id))return;
  var item=ref.closest('li,p,blockquote,h2,h3')||ref.parentElement;if(!item)return;
  item.classList.add('rv-review-item');
  item.setAttribute('data-review-target',id);
  item.setAttribute('tabindex','0');
  item.addEventListener('mouseenter',function(){activate(item,true);});
  item.addEventListener('focusin',function(){activate(item,true);});
  item.addEventListener('click',function(){activate(item,true);});
});
b.addEventListener('click',function(){
  var on=document.body.classList.toggle('rv-open');
  b.textContent=on?'Hide review':'Show review';
  b.setAttribute('aria-expanded',on?'true':'false');
  if(on&&panel)panel.scrollTop=0;
  if(!on)clear();else if(activeId)draw();
});
/* Handle badge copy buttons. Clipboard API is async; on success we
   briefly mark the badge with rv-handle-copied so the user gets
   visible feedback. Clicking the badge anywhere also activates the
   surrounding review item (via the activate() handler above), so
   the copy button stops propagation to avoid double-firing. */
Array.prototype.forEach.call(document.querySelectorAll('#rv-panel .rv-handle-copy'),function(btn){
  btn.addEventListener('click',function(e){
    e.stopPropagation();
    var badge=btn.parentElement;if(!badge)return;
    var handle=badge.getAttribute('data-handle')||(badge.textContent||'').trim();
    if(!handle)return;
    function done(){
      badge.classList.add('rv-handle-copied');
      var prev=btn.textContent;btn.textContent='copied';
      setTimeout(function(){badge.classList.remove('rv-handle-copied');btn.textContent=prev||'copy';},1200);
    }
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(handle).then(done,function(){
        /* fallback: select the text so the user can ⌘C */
        var range=document.createRange();range.selectNodeContents(badge.querySelector('.rv-handle-text'));
        var sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);
      });
    }else{
      var range=document.createRange();range.selectNodeContents(badge.querySelector('.rv-handle-text'));
      var sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);
    }
  });
});
window.addEventListener('scroll',draw,{passive:true});
window.addEventListener('resize',draw);
if(panel)panel.addEventListener('scroll',draw,{passive:true});
})();</script>
"""


def _safe_target_id(value: str) -> str:
    target = (value or "").strip().lower()
    return target if _VALID_TARGET_RE.match(target) else ""


def _anchor_html(target: str) -> str:
    safe = _safe_target_id(target)
    if not safe:
        return ""
    return (
        f'<div class="rv-anchor" id="rv-target-{safe}" '
        f'data-review-anchor="{safe}" aria-hidden="true"></div>'
    )


def _replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!--\s*block:{re.escape(name)}\s*-->\n?)(.*?)(<!--\s*/block:{re.escape(name)}\s*-->)",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(lambda m: f"{m.group(1)}{body}{m.group(3)}", text, count=1)


_SECTION_PREFIX = {"notable": "n", "brief": "b", "journal": "j"}


def _annotate_chunk_targets(name: str, body: str, *, issue_number: int) -> str:
    """Walk the section's rows (in current position order) and prepend
    a hidden HTML anchor at the start of the line containing each
    item's URL, so the drawer's connector lines can find the target.

    Anchoring at line-start avoids breaking markdown link syntax —
    inserting before the URL itself would land *inside* ``[Title](url)``
    and confuse the renderer (the anchor would end up inside the
    href).
    """
    if name not in _SECTION_PREFIX:
        return body
    rows = issue_items.list_items(int(issue_number), section=name, include_promoted=False)
    out = body
    prefix = _SECTION_PREFIX[name]
    for i, row in enumerate(rows, start=1):
        url = (row.get("url") or "").strip()
        if not url:
            continue
        url_idx = out.find(url)
        if url_idx < 0:
            continue
        line_start = out.rfind("\n", 0, url_idx) + 1
        anchor = _anchor_html(f"{prefix}{i}")
        if not anchor:
            continue
        out = out[:line_start] + anchor + "\n" + out[line_start:]
    return out


def _annotate_review_targets(md: str, *, issue_number: int) -> str:
    """Convert draft block markers and per-item rows into HTML anchors.

    The anchors exist only in the preview HTML; the underlying draft markdown
    and publish flow stay unchanged.
    """
    out = md or ""
    for name in draft_mod.SECTION_BLOCKS:
        pattern = re.compile(
            rf"(<!--\s*block:{re.escape(name)}\s*-->\n?)(.*?)(<!--\s*/block:{re.escape(name)}\s*-->)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(out)
        if not match:
            continue
        body = _annotate_chunk_targets(name, match.group(2), issue_number=issue_number)
        out = _replace_block(out, name, body)
        out = re.sub(
            rf"<!--\s*block:{re.escape(name)}\s*-->\n?",
            _anchor_html(name) + "\n",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
    return out


def _prepare_review_md(review_md: str) -> str:
    src = review_md or ""

    def _target_repl(match: re.Match) -> str:
        safe = _safe_target_id(match.group(1) or match.group(2) or "")
        if not safe:
            return ""
        return f'<span class="rv-target-ref" data-review-target="{safe}"></span>'

    src = _REVIEW_TARGET_RE.sub(_target_repl, src)

    def _handle_repl(match: re.Match) -> str:
        raw = (match.group(1) or "").strip().upper()
        if not _VALID_HANDLE_RE.match(raw):
            return ""
        # The badge sits inline next to the bullet text. Aria-label
        # explains the copy action for screen readers; data-handle is
        # what the inline JS reads when the button is clicked. The
        # ``<noscript>`` fallback keeps the handle text readable when
        # JS is off (the badge just becomes static text).
        return (
            f'<span class="rv-handle" data-handle="{raw}">'
            f'<span class="rv-handle-text">{raw}</span>'
            f'<button type="button" class="rv-handle-copy" '
            f'aria-label="Copy {raw} to clipboard">copy</button>'
            f'</span>'
        )

    src = _REVIEW_HANDLE_RE.sub(_handle_repl, src)
    return src


def review_target_legend(md: str, *, issue_number: int) -> str:
    """Return the target IDs Eddy can use in the draft-review drawer.

    The list combines:

    - Section-level ids (``intro``, ``currently``, ``cover``, ``notable``,
      ``journal``, ``brief``, ``outro``, ``haiku``) — derived from the
      draft text's block presence (atom sections only show up when
      their block has content).
    - Per-item ids (``n1``/``b2``/``j3``, etc.) — derived from
      ``issue_items`` rows in current position order, with the
      section's letter as the prefix.
    """
    blocks = draft_mod.parse_blocks(md or "")
    lines: list[str] = []
    for name in draft_mod.SECTION_BLOCKS:
        if blocks.get(name):
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
                          strip_block_markers: bool = False,
                          review_md: Optional[str] = None,
                          issue_number: Optional[int] = None) -> str:
    """Wrap ``md`` (rendered to HTML) in a standalone, self-contained page.
    If ``strip_block_markers``, the ``<!-- block:X -->`` comments are
    removed first. ``subtitle``, if given, renders as a small banner above
    the content (used to mark drafts as work-in-progress).
    ``convenience_links`` (an optional list of ``(label, url)`` pairs)
    renders as a second line of cross-links in the same banner.
    ``meta`` (an optional ``{"subject": …, "description": …}`` dict)
    renders as a definition list between the banner and the article
    body. ``review_md``, if given, is rendered into a slide-in drawer
    that's hidden until the fixed "Show review" button is pressed.

    ``issue_number`` is required when ``review_md`` is supplied — the
    per-item drawer anchors (n1/b2/j3) are derived from ``issue_items``
    rows for that issue. When omitted (preview-only paths with no
    drawer), the row-based anchor pass is skipped.
    """
    src = md or ""
    has_review = bool(review_md and review_md.strip())
    if has_review and issue_number is not None:
        src = _annotate_review_targets(src, issue_number=int(issue_number))
    if strip_block_markers:
        src = _BLOCK_MARKER_RE.sub("", src)
        src = re.sub(r"\n{3,}", "\n\n", src).strip() + "\n"
    body = _markdown_to_html(src)
    banner = _render_banner(subtitle, convenience_links)
    meta_block = _render_meta(meta)
    if has_review:
        review_chrome = _REVIEW_CHROME.format(review_html=_markdown_to_html(_prepare_review_md(review_md)))
        review_connectors = '<svg id="rv-connectors" aria-hidden="true"></svg>\n'
        review_script = _REVIEW_SCRIPT
    else:
        review_chrome = review_connectors = review_script = ""
    return _PAGE.format(
        title=_html.escape(title), css=_CSS, banner=banner, meta=meta_block,
        body=body,
        review_chrome=review_chrome, review_connectors=review_connectors,
        review_script=review_script,
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
.thesis {
  font-family: var(--wt-serif); font-size: 18px; line-height: 1.45;
  background: var(--wt-accent-soft); border-left: 3px solid var(--wt-accent);
  padding: 14px 18px; border-radius: 3px; margin: 0 0 24px;
  color: var(--wt-ink-soft); font-style: italic;
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
    thesis: str,
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
        '<p class="subtitle">react ✅ / ❌ / 🔄 in #editorial · the page refreshes on each round</p>'
        f'<p class="thesis">{_html.escape((thesis or "").strip())}</p>'
        if thesis and thesis.strip()
        else
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
    thesis: str,
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
            issue_number=int(issue_number), thesis=thesis,
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
