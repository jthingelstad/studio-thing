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

1. **Alignment (the effort now).** Split the monorepo into Studio + surfaces and cut over. Structural.
2. **Features (enabled by alignment — parked until it's done).** Thingy identity/intelligence/temporal/
   sparring, the blog Micropub pipeline, the podcast `data/episodes` source.

## Where we actually are

- **Done:** parallel extraction — studio-thing holds the brain, thingy holds the Discord bridge. A lot of
  design captured.
- **Not done:** the cutover. Weekly still does 100% of the work; studio-thing is a dormant copy.
  **Alignment isn't real until Phase 1–2 land.**

## The alignment critical path (the whole near-term effort)

1. **Phase 1 — stand up Studio.** Studio CI runs the production half and pushes generated inputs to the
   weekly repo (the handoff tool already exists). Verify the pushed artifacts match the old path.
2. **Phase 2 — slim weekly.** Cut production steps + delete the duplicated brain + move secrets; weekly
   becomes a pure render surface. Time it for the day after a send (no recovery flow).

Detail: `weekly.thingelstad.com/STUDIO_MIGRATION_PLAN.md`.

## Parked (designed, not now)

| Workstream | Doc | Notes |
|---|---|---|
| Thingy standalone web (docent) | `thingy/STANDALONE_BUILD.md` | Additive surface completion; can run parallel to the migration |
| Thingy roadmap (identity, intelligence, temporal, sparring) | `thingy/THINGY_ROADMAP.md` | Big vision; sequenced behind alignment |
| Temporal layer (`data/timeline/{year}.md`) | THINGY_ROADMAP §temporal | Decoupled; startable anytime; unblocks the members broadcast |
| Blog draft → Micropub pipeline | (to spec) | Needs blog drafts + a publisher in Studio |
| Podcast `data/episodes` source + transcript ingestion | (to spec) | Audio-native source store |

## Next action

Point Claude Code at **Phase 1**. Everything in the parked table waits until the structure is aligned —
with the one exception that the Thingy standalone (A1) and the temporal layer are both additive and may
run in parallel if there's appetite, since neither touches the live publishing path.
