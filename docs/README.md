# How The Weekly Thing works

This is the **editorial north star** — the canonical, plain-English description of how an issue of
*The Weekly Thing* is made and shipped. It's what we design the implementation against and verify
it against. (See [`CLAUDE.md`](CLAUDE.md) for the discipline around that.)

**Start here:** [`publishing-process.md`](publishing-process.md) — the spine (Build → Publish →
Share), concurrency, and who owns what. Everything else is detail behind it.

## When to read each

| If you want to understand… | Read |
|---|---|
| The overall process + phase machinery | [`publishing-process.md`](publishing-process.md) |
| A single phase | [`phases/build.md`](phases/build.md) · [`phases/publish.md`](phases/publish.md) · [`phases/share.md`](phases/share.md) |
| What's in an issue + how it's formatted | [`sections.md`](sections.md) |
| The Journal (micro.blog → issue) | [`journal-handling.md`](journal-handling.md) |
| How a post becomes a Featured section | [`featured-posts.md`](featured-posts.md) |
| The Echoes section (Thingy's archive note) | [`echoes.md`](echoes.md) |
| How it should sound | [`voice-and-style.md`](voice-and-style.md) |
| The standing programs | [`programs/membership.md`](programs/membership.md) · [`programs/campaigns.md`](programs/campaigns.md) |
| A persona's role | [`agents/`](agents/) — scout · eddy · linky · marky · patty · thingy |
| How issues are identified + titled | [`identifiers.md`](identifiers.md) |

## What's *not* here

- **Technical reference** (the Librarian/Thingy Lambda runtime, third-party API gotchas) →
  [`../reference/`](../reference/README.md).
- **Project history** (design briefs, audit snapshots, progress logs, planning sessions) →
  [`../notes/`](../notes/README.md). *True when written, not canonical — this `docs/` wins.*
- **How it's built** (jobs, schema, runtime conventions) → the per-app `CLAUDE.md` files
  (`apps/workshop_bot/CLAUDE.md`, etc.). The canonical editorial source for a shipped issue is
  `data/issues/{N}/archive.md`; `make build` regenerates the site from those bytes.
