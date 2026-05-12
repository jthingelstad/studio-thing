# Issue identifier convention — `WT<NUM>` + `WT<NUM> — <Theme>` subjects

Record of the forward-only rollout of two Weekly Thing conventions. The historical
archive is immutable — no past issue's subject, page, podcast episode title, feed
entry, llms.txt entry, or metadata was modified. The change is in the templates,
generators, and prompts that produce **new** output (plus the shared page-chrome
templates, where re-rendering harmlessly restamps the visible `#N` chip on old
pages too — see below).

## The two conventions

1. **Email subject line** (future issues): `WT<NUM> — <Theme Phrase>` — em-dash,
   title-case 3–6-word theme capturing the issue's center of gravity; comma-token
   fallback (`WT<NUM> — Token, Token, Token`) for varied digests; `WT<NUM> — <Special
   Topic>` for travel/anniversary/etc. (e.g. `WT322 — Banff & Lake Louise`).
   Old format was `Weekly Thing 345 / Codex, Headless, Wikiwise`.
2. **Short identifier** (future issues): `WT<NUM>` is the one canonical short form,
   replacing the old mix of `#347` / `Issue 347` / `Weekly Thing 347` / `WT347`.
   Long-form `Weekly Thing <NUM>` survives only as the wordmark (issue-page eyebrow).
   Thingy (the archive Q&A agent) references issues as `WT<NUM>` in all output,
   regardless of issue age — *new* prose written now says `WT100` even though that
   issue predates the convention.

## What was already in place

The workshop_bot content loop already produced the new subject format before this
rollout: `apps/workshop_bot/prompts/eddy/compose-subject.md` emits 5 `WT<NUM> —
<theme>` options → `jobs/compose_meta.py` writes the pick into `metadata.json` →
`pipeline/content/content.py publish` sends it verbatim to Buttondown. workshop_bot
internals (Discord messages, `tools/render.py` titles/banners) and their tests
already used `WT<N>`. Only the `content.py` degenerate fallback subject was changed
(`Weekly Thing {n}` → `WT{n}`).

## Why most of the site needed no change

Past archive `.md` frontmatter (the `subject` strings) is the immutable source of
truth and was not touched. Every surface that renders `{{ issue.data.subject }}`
directly — `<title>` / `og:title` / `twitter:title` (`_includes/layouts/base.njk`),
Atom entry titles (`feed.njk`, `rss.njk`), `issue-links-feed.njk`'s `<title>`,
`archive/archive.njk` entry titles, `issue-text.njk`'s `#` heading, the share-button
`data-title` (`issue.njk`), `archive-json.njk` — therefore shows the old format for
old issues and `WT347 — Headless Everything` for new ones automatically. No edits.
(So `og:title` on a new issue page is `WT347 — Headless Everything`.)

The real work was: (a) templates that *construct* an identifier string instead of
reading `subject`, (b) the issue-page eyebrow/H1 derivation, (c) the two HYBRID
generators (podcast feed, llms.txt) that re-render *all* issues and so need a
per-issue branch, and (d) Thingy's citation rendering.

## Changes made

### Site templates — `#N` / `Issue N` chrome → `WT<N>`
- `apps/site/_includes/layouts/issue.njk`:
  - Eyebrow: `Weekly Thing #<span…>{{ number }}</span>` → `Weekly Thing <span…>{{ number }}</span>` (drop the `#`; keep `data-pagefind-meta="issue"`).
  - H1: derive the display title as the substring after the **last** ` — ` (new) or ` / ` (legacy) separator in `subject`, else the whole `subject`. New → `Headless Everything`; old `Weekly Thing 346 / Wuphf, Landsat, Eclipse` → `Wuphf, Landsat, Eclipse` (unchanged); pre-separator early issues → full subject.
  - Per-issue links Atom `<link>` title attr: `Links from Issue #{{ number }}` → `Links from WT{{ number }}`.
  - Prev/next pager chips and `title=` tooltips: `#{{ … }}` / `Issue {{ … }}: …` → `WT{{ … }}` / `WT{{ … }}: …`.
- `apps/site/index.njk` — `home-stamp-issue` `#{{ latest.data.number }}` → `WT{{ … }}`.
- `apps/site/_includes/partials/issue-card.njk` — `#{{ issue.data.number }}` → `WT{{ … }}`.
- `apps/site/_includes/layouts/topic.njk` — `#{{ it.number }}` → `WT{{ it.number }}`.
- `apps/site/archive/archive.njk` — `archive-entry-cover-num` `{{ issue.data.number }}` → `WT{{ issue.data.number }}` (the big cover numeral; the numeric `data-fallback` attr the JS gradient reads is unchanged).
- `apps/site/issue-links-feed.njk` — `<subtitle>Links featured in issue #N of the Weekly Thing</subtitle>` → `… in WTN …`.

These are template strings, so on the next build the chip on *every* issue page /
archive card / per-issue links feed flips from `#79` to `WT79`. That's intended —
the `subject`-derived titles, podcast episode titles, llms.txt entries, and feed
entry titles all stay historically correct because they read stored `subject`.

### HYBRID generators — per-issue branch on the `WT` prefix
- `apps/site/podcast.njk` — episode title: if `issue.data.subject.startsWith("WT")` → use `subject` verbatim (`WT347 — Headless Everything`); else the legacy `"#" + number + " — " + subjectTail`. The 10 existing `#NN — …` episode titles are byte-identical; `<itunes:episode>` / `<guid>` / `<link>` stay numeric.
- `apps/site/llms.njk` — issue-list entries (the "Recent Issues" and "Optional" loops): if `subject.startsWith("WT")` → link text `{{ subject }}` (avoids the `#347 — WT347 — …` doubling); else the legacy `#{{ number }} — {{ subject }}`. URLs / dates / descriptions unchanged.

### Thingy (Librarian agent) — always cite `WT<NUM>`
- `apps/librarian/lambda/prompts/answer-style.md` — instructs the model to cite as `WT295` / `(WT295, WT297)`, never a bare `#295` or "issue 295".
- `apps/librarian/lambda/chat/runtime.mjs` — `prioritizeCitationsForAnswer` matches `WT(\d+)` as well as `#(\d+)` when ordering the citations list.
- `apps/workshop_bot/tools/thingy_render.py` (Discord bridge) — `CITATION_RE` matches `WTNNN` or legacy `#NNN`; rewrites matched references (those with a citation) to `[WTNNN]({site_url}/archive/NNN/)`. References with no matching citation are left exactly as written (so a stray `#5` that isn't an issue isn't mangled).
- `apps/site/librarian.njk` (web chat) — the inline-reference linker matches `WTNNN`/`#NNN` and renders `<a …>WTNNN</a>`; the hover-tooltip header is `WT295: <subject> | <date> | <section>`.
- `apps/workshop_bot/tests/test_thingy_bridge.py` — updated expectations to `[WTNNN](…)`; added cases for the `WT`-prefixed input and an unmatched `WT999` staying plain.

### Pipeline
- `pipeline/content/content.py` — fallback subject when `metadata.json` has none: `Weekly Thing {number}` → `WT{number}` (degenerate path; compose-meta always writes a real subject).

## Deliberately left unchanged
- All past archive `.md` frontmatter (`apps/site/archive/*.md`), `data/buttondown/bodies|emails/*`, `apps/site/_data/emails.json` — immutable source of truth.
- `feed.njk` / `rss.njk` / `issue-links-feed.njk` `<title>`, `archive-json.njk`, `issue-text.njk` `#` heading, `base.njk` `<title>`/`og:title`/`twitter:title`, `archive.njk` entry titles — already `subject`-driven; correct automatically.
- `librarian-core/librarian_core/corpus.py` `Weekly Thing #{n}: {subject}` embedding header and the matching `runtime.mjs` rerank-context header — internal model context, not user-visible; changing them forces a paid re-embed/rerank for no benefit.
- `pipeline/audio/script/common.py` spoken "The Weekly Thing, issue {number}." and `pipeline/audio/synthesize.py` ID3 `Weekly Thing {number}` tag — not in the identifier-surface set.
- `apps/site/issue-text.njk` `- Issue: {{ number }}` — a labeled numeric field, not an identifier format.
- `/archive/N/` URLs everywhere — numeric path, no `WT`.

## Open item
- **r/WeeklyThing post flair:** `apps/workshop_bot/jobs/update_draft.py` `_reddit_tag_line` still emits `Weekly Thing {n} tag in r/WeeklyThing` with `flair_name=Weekly%20Thing%20{n}`, because that must match the actual subreddit flair names. If the flairs are ever renamed to `WT{n}`, update that line and the URL param to match.

## Verification done
- Site builds clean (`npx @11ty/eleventy --config apps/site/eleventy.config.js`). A throwaway `WT9999 — Headless Everything` issue was built and checked: page eyebrow `Weekly Thing 9999`, H1 `Headless Everything`, `<title>`/`og:title` `WT9999 — Headless Everything`, pager `WT9999`; `podcast.xml` item title `WT9999 — Headless Everything` with the 10 existing episodes byte-unchanged; `llms.txt` entry `[WT9999 — Headless Everything](…)`; `links.xml` `<title>Links from WT9999 — Headless Everything</title>` + `<subtitle>… in WT9999 …</subtitle>`; `feed.xml` entry title `WT9999 — Headless Everything`. Then removed.
- Tests pass: `python -m unittest discover -s tests -t .` (17), `python -m unittest discover -s apps/workshop_bot/tests -t .` (362), and the librarian Lambda `node --test` suite (28).
- Thingy prompt/runtime changes ship on the next `pipeline/deploy` of the librarian stack — the corpus does not need re-uploading (`--skip-corpus-upload`).
