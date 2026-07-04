# Project Alignment — north star

The one-page map of the whole effort. Detailed plans hang off this; when a thread starts going deep,
come back here to check it's actually on the critical path.

> **Maintenance rule:** any PR that changes the staff, the production model, a surface, or a repo
> boundary updates this file in the same PR. A stale north star is worse than none.

## The shape

One **brain** (Studio) + federated **surfaces**, sharing intelligence through the Librarian API.

| Repo / host | Role | Class |
|---|---|---|
| **studio-thing** (Studio) | Brain: staff (Scout/Eddy/Linky/Marky/Patty), productions, web work surface, idea engine, source of truth, corpus, Librarian API, timeline | hub |
| **thingelstad.com** | Blog on Micro.blog | publish surface (no repo) |
| **another.thingelstad.com** | Podcast | publish surface |
| **weekly.thingelstad.com** | Newsletter site + audio | publish surface (→ secret-free) |
| **thingy.thingelstad.com** | Thingy web (docent) + Discord bridge | query surface |

**The rule:** surface → own repo/host, downstream. Upstream (source, production, staff, brain) → Studio.

## The studio model (2026-06 rearchitecture)

The studio now puts AI at the center of *all* of Jamie's publishing, not just the newsletter.
**The one rule: Jamie writes every word** — agents develop ideas, research, connect, curate,
structure, edit, critique; they never write his prose (the newsletter envelope is the
established exception).

- **Productions are the unit of work.** Newsletters, articles, podcasts, and projects are rows in
  a `productions` registry, each a small state engine: phase + content + task board.
- **The web app is the work surface; Discord is the agents' room.** A private (tailnet-only)
  aiohttp app serves Scout's slate, the productions registry, the seeds idea garden, and in-web
  chat with the agents. The pinned Discord phase cards are retired; slash commands remain only as
  escape hatches until their web equivalents land.
- **Authored content lives in the DB** (`production_content`); S3 is publishing-only.
- **The idea engine:** `seeds` + `seed_clusters` hold Jamie's idea snippets; Eddy tends the garden
  and graduates ripe clusters into article/podcast productions.
- **Staff:** Scout (producer — slate, phases, handoffs), Eddy (editorial), Linky (research/links),
  Marky (syndication/campaigns), Patty (membership).

Full detail: `apps/workshop_bot/CLAUDE.md` ("The studio now") and `docs/publishing-process.md`.

## Where we actually are

- **Done (alignment):** Studio holds the brain and is the live producer. Weekly is the render
  surface, Thingy is the query surface, and Another Thing remains its own podcast surface. Another
  Thing transcripts import into Studio's `data/podcast/` store and build into a separate Librarian
  podcast corpus.
- **Done (2026-06-28/29):** the productions + web-work-surface rearchitecture landed (PRs #26/#27
  plus the M3/R3 retirement pass). Tested and in production use.
- **Done (2026-07-04):** the S3-collaboration layer ripped out — **the DB is the draft.** The
  `update-draft` daily projection, `draft.md`/`draft.html`, `draft_digests`, the `workshop.json`
  pointer, and the **iOS-Shortcuts pipeline are retired**. Replacements: `sync-issue` (inbound
  Pinboard/micro.blog mirror), render-then-ship publish legs, on-demand `eddy-review`, live web
  preview, web cover upload. Also: the atom editor (build 1) — `/productions/WT{n}/editor` with
  promote/deselect/reorder over `issue_items`.
- **In transition:** WT350 will be the first ship through the fully-clean path. Escape-hatch slash
  commands (`/eddy issue …`, `/scout issue publish …`, `/patty cta`, `/marky campaign`,
  `/patty goal`) remain until web equivalents land.
- **Operational model:** Studio ships canonical content and pushes generated 11ty inputs to Weekly.
  Weekly refreshes only its own landing-page stats, then renders and deploys.

## Current production chain

1. Authoring happens in the studio (web work surface + agents; authored content in the workshop
   DB). Publishing commits canonical issue data to `studio-thing`.
2. Studio CI builds archive inputs, corpus, graph, status, and deploys Librarian changes as needed.
3. Studio CI uploads source-specific corpora, including the podcast corpus when transcript data changes.
4. Studio CI commits generated site inputs to `weekly.thingelstad.com`.
5. Weekly CI refreshes site-owned stats, builds Eleventy + Pagefind, and deploys Pages.

Historical detail: `STUDIO_MIGRATION_PLAN.md`, `PHASE_1.md`, and `PHASE_2.md`.

## Parked (designed, not now)

| Workstream | Doc | Notes |
|---|---|---|
| Thingy roadmap (identity, intelligence, temporal, sparring) | `thingy.thingelstad.com/docs/ROADMAP.md` (separate repo) | Big vision, unblocked by alignment |
| Temporal layer (`data/timeline/{year}.md`) | Thingy roadmap §temporal | Decoupled; startable anytime; unblocks the members broadcast |
| Blog draft → Micropub pipeline | (to spec) | Drafts capture exists (`data/blog/` + Drafts blog-export importer); the Micropub publisher is still to spec |
| Podcast handoff automation | (to spec) | Today Studio imports from the sibling Another repo manually before commit |

## Next action

Land the rearchitecture fully: ship the next 2–3 issues through the new publish flow, then retire
the Shortcuts recovery path and the escape-hatch slash commands. After ~a month of real use, judge
the new machinery (seeds garden, in-web chat, proactive check-ins) by whether it actually got used —
cut what didn't. Throughout: keep the Studio → Weekly handoff and the Librarian API boring.
