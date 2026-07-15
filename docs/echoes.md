# Echoes — the archive note

A **section** near the end of every issue — see [`sections.md`](sections.md). It
is a short note connecting this week's issue to the archive and renders as
`## Echoes`.

## What it is

2–5 sentences (~60–110 words), in an archive-librarian voice: third-person
about Jamie, warm, and grounded in citations.
Every cited issue is a markdown link: `[WT###](https://weekly.thingelstad.com/archive/N/)`.

## Two modes

1. **Thematic resonance** (preferred) — a genuine echo between this issue and 1–3 past issues,
   surfaced via semantic retrieval over the archive.
2. **Anniversary echo** (fallback) — a specific detail from the issue nearest 1 / 5 / 8 years back.

## Rules

- Echoes is expected for every issue; if retrieval is unavailable, fail loud and rerun.
- Anti-repetition: it sees the last several Echoes and avoids reusing themes.
- Quality bar: it requires real semantic retrieval (fails loud rather than degrading silently).

## How it's run

Auto-fired when the issue is marked built, or on demand via `/eddy issue echoes`.
