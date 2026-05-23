# Phase 1 — Build

*Create the issue.* — Overview: [`../publishing-process.md`](../publishing-process.md)

**Owner:** Eddy (editor), with Linky feeding curated links. **Channel:** `#editorial`.
**Question:** *"Is the issue written, and is it good?"* Build fills in gradually all week.

The issue is **one uniform, channel-agnostic content artifact** with a fixed anatomy in **reading
order** — every channel composes from the same shape (`tools/renderers.py:_compose_published_body`).
The sections, their order, and per-section formatting rules live in [`../sections.md`](../sections.md);
Journal specifics in [`../journal-handling.md`](../journal-handling.md); the Echoes section in
[`../echoes.md`](../echoes.md).

## What happens

- Content arrives from upstream all week: Notable/Briefly from Pinboard, Journal from micro.blog,
  Intro/Outro/Cover from Jamie via Drafts → Shortcut, Currently from the DB, Haiku + Echoes
  composed. (See [`../sections.md`](../sections.md) for the full source map.)
- Each refresh re-projects the draft and runs **one Opus editorial review**
  (`prompts/eddy/draft-review.md`) — anchored, suggestions-only — shown in the `draft.html`
  "Show review" drawer and counted on the Build card. It re-runs only when the draft changed.
- The **Build card** (`#editorial`) is the live surface: the anatomy in reading order, the review
  count, reorder status, and the author buttons (Refresh · Reorder · Haiku · Echoes · Edit · Mark
  built).

## Gates

- **Entry:** `/eddy issue start <n> <pub-date> <days>` opens the window (`phase = build`).
- **Exit:** **`mark built`** (`/eddy issue built` or the Build-card button) — declares the content
  written and moves the issue to [Publish](publish.md). Gated on the required content being present
  (the three sections + intro + cover + haiku).

## The one rule

**Build never asks about Publish things.** Subject, description, and the membership CTA are
*Publish* inputs — they're set once the issue is built, not mid-week. Surfacing them during Build
was the original operator friction this whole model fixes.
