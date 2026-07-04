# Phase 1 — Build

*Create the issue.* — Overview: [`../publishing-process.md`](../publishing-process.md)

**Owner:** Scout (producer), with Eddy on editorial quality and Linky feeding curated links.
**Channel:** `#production`.
**Question:** *"Is the issue written, and is it good?"* Build fills in gradually all week.

The issue is **one uniform, channel-agnostic content artifact** with a fixed anatomy in **reading
order** — every channel composes from the same shape (`tools/renderers.py:_compose_published_body`).
The sections, their order, and per-section formatting rules live in [`../sections.md`](../sections.md);
Journal specifics in [`../journal-handling.md`](../journal-handling.md); the Echoes section in
[`../echoes.md`](../echoes.md).

## What happens

- Content arrives from upstream all week: Notable/Briefly from Pinboard, Journal from micro.blog
  (mirrored into DB rows by the daily `sync-issue`), Intro/Outro/Currently written by Jamie in the
  web editor, the cover uploaded on the production page, Echoes composed.
  (See [`../sections.md`](../sections.md) for the full source map.) **Haiku is not Build content** —
  Eddy writes it on the [Publish](publish.md) side, alongside subject/description/CTA, since it's
  shipping work, not authoring.
- **Reading the draft = rendering the DB.** The live preview (`/productions/WT{n}/preview`)
  renders the issue from current row state on every load — there is no `draft.md`/`draft.html`
  artifact and no daily projection tick.
- Editorial review is **on-demand**: the production page's Review button runs Eddy's single Opus
  pass (`eddy-review`) — anchored, suggestions-only — storing comments surfaced on the page.
- The **production page** (`/productions/WT{n}`) is the live surface: the anatomy in reading
  order, open comments, gates, and the controls (Sync · Review · editor · Mark built).

## Gates

- **Entry:** `/scout issue start <n> <pub-date> <days>` opens the window (`phase = build`).
- **Exit:** **`mark built`** (the production page or `/scout issue built`) — declares the content
  written and moves the issue to [Publish](publish.md). Gated on the required *authored* content
  being present (the three sections + intro + cover). Haiku is no longer a Build gate — it's
  produced on the Publish side.

## The one rule

**Build never asks about Publish things.** Subject, description, the membership CTA, the haiku,
and the thesis are *Publish* inputs — Eddy produces them once the issue is built, not mid-week.
Surfacing them during Build was the original operator friction this whole model fixes.
