# Echoes — the archive note

A **section** (the last one in every issue — see [`sections.md`](sections.md)), **written by
[Thingy](agents/thingy.md)**: a short note connecting this week's issue to the nine-year archive.
Renders as `## Echoes`. *Internally the job/file is still `compose-closer` / `closer.md`; the
reader-facing name is **Echoes**.*

## What it is

2–5 sentences (~60–110 words), in **Thingy's voice** — third-person about Jamie, warm, librarian.
Every cited issue is a markdown link: `[WT###](https://weekly.thingelstad.com/archive/N/)`.

## Two modes (Thingy picks whichever has the stronger signal)

1. **Thematic resonance** (preferred) — a genuine echo between this issue and 1–3 past issues,
   surfaced via semantic retrieval over the archive.
2. **Anniversary echo** (fallback) — a specific detail from the issue nearest 1 / 5 / 8 years back.

## Rules

- **SKIP is allowed** — if there's no real connection this week, no Echoes section ships.
- Anti-repetition: it sees the last several Echoes and avoids reusing themes.
- Quality bar: it requires real semantic retrieval (fails loud rather than degrading silently).

## How it's run

Auto-fired when Eddy's reorder pass is accepted, **or** on demand via `/eddy issue echoes` / the
Build-card **Echoes** button (so it's never trapped behind the reorder step).
