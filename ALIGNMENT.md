# Project Alignment — north star

The one-page map of the whole effort. Detailed plans hang off this; when a thread starts going deep,
come back here to check it's actually on the critical path.

## The shape

One **brain** (Studio) + federated **surfaces**, sharing intelligence through the Librarian API.

| Repo / host | Role | Class |
|---|---|---|
| **studio-thing** (Studio) | Brain: staff (Eddy/Linky/Marky/Patty), production, source of truth, corpus, Librarian API, blog drafts, timeline | hub |
| **thingelstad.com** | Blog on Micro.blog | publish surface (no repo) |
| **another.thingelstad.com** | Podcast | publish surface |
| **weekly.thingelstad.com** | Newsletter site + audio | publish surface (→ secret-free) |
| **thingy.thingelstad.com** | Thingy web (docent) + members broadcast | query surface |

**The rule:** surface → own repo/host, downstream. Upstream (source, production, staff, brain) → Studio.

## Two layers of work — don't confuse them

1. **Alignment (completed pivot).** Split the monorepo into Studio + surfaces and cut over. Structural.
2. **Features (enabled by alignment).** Thingy identity/intelligence/temporal/sparring, the blog
   Micropub pipeline, the podcast `data/episodes` source.

## Where we actually are

- **Done:** Studio holds the brain and is the live producer. Weekly is the render surface, Thingy is the
  query surface, and Another Thing remains its own podcast surface.
- **Operational model:** Studio ships canonical content and pushes generated 11ty inputs to Weekly.
  Weekly refreshes only its own landing-page stats, then renders and deploys.

## Current production chain

1. Authoring bot commits canonical issue data to `studio-thing`.
2. Studio CI builds archive inputs, corpus, graph, status, and deploys Librarian changes as needed.
3. Studio CI commits generated site inputs to `weekly.thingelstad.com`.
4. Weekly CI refreshes site-owned stats, builds Eleventy + Pagefind, and deploys Pages.

Historical detail: `STUDIO_MIGRATION_PLAN.md`, `PHASE_1.md`, and `PHASE_2.md`.

## Parked (designed, not now)

| Workstream | Doc | Notes |
|---|---|---|
| Thingy standalone web (docent) | `thingy/STANDALONE_BUILD.md` | Additive surface completion |
| Thingy roadmap (identity, intelligence, temporal, sparring) | `thingy/THINGY_ROADMAP.md` | Big vision, now unblocked by alignment |
| Temporal layer (`data/timeline/{year}.md`) | THINGY_ROADMAP §temporal | Decoupled; startable anytime; unblocks the members broadcast |
| Blog draft → Micropub pipeline | (to spec) | Needs blog drafts + a publisher in Studio |
| Podcast `data/episodes` source + transcript ingestion | (to spec) | Audio-native source store |

## Next action

Keep production boring: protect the Studio → Weekly handoff, keep the Librarian API stable, and move
new work through the feature docs now that the structure is aligned.
