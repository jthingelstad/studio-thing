# Studio

The **brain** behind Jamie Thingelstad's publishing. Studio is where capture,
research, the editorial source of truth, production, and the authoring staff live.
Everything downstream of it — the blog, the newsletter, the podcast, Thingy — is a
**surface** that consumes what Studio produces.

> **The rule that decides where anything goes:** if it's a publishing surface, it's
> its own repo/host, downstream. If it's *upstream* of publishing — capture, research,
> the editorial source of truth, production, or the staff — it lives here in Studio.

This repo was extracted from the `weekly.thingelstad.com` monorepo with
`git filter-repo`, so **history and blame are preserved** for everything it contains.
See `ALIGNMENT.md` for the current architecture map. `STUDIO_MIGRATION_PLAN.md`
and the phase runbooks remain as historical migration records.

## Architecture

One brain, several surfaces.

| Repo / host | Role | Class |
|---|---|---|
| **Studio** (this repo) | Brain: authoring staff, production pipeline, editorial source of truth, corpus, Librarian API | hub |
| thingelstad.com | Blog on Micro.blog | publish surface (no repo) |
| another.thingelstad.com | Podcast, custom site | publish surface (own repo) |
| weekly.thingelstad.com | Newsletter site (11ty) + audio links | publish surface (own repo) |
| thingy.thingelstad.com | Thingy web UI + Discord bridge | query surface (own repo) |

**Two classes of surface:**

- **Publishing surfaces** (blog, newsletter, podcast) consume **static artifacts** —
  committed files and feeds. No live dependency on Studio.
- **Query surface** (Thingy) is a **live client** of the Librarian API at runtime. That
  makes the **Librarian API a versioned contract**, not just an internal function.

## What's in here

| Path | What it is |
|---|---|
| `apps/workshop_bot/` | The authoring staff (Eddy / Linky / Marky / Patty) — Discord-based agents that help produce each issue. The Studio core. |
| `apps/librarian/` | The Librarian API: Lambda, infra, and admin. Deployed from Studio; queried live by Thingy. |
| `librarian-core/` | The shared `librarian_core` Python package — corpus, graph, retrieval, links. The library behind the API and the pipeline. |
| `pipeline/` | Production: build, stats, status, audio, corpus, graph, deploy. |
| `data/issues/` | Editorial source of truth — the canonical per-issue content. |
| `data/audio/` | Audio production source: manifest, scripts, bumpers. |
| `data/blog/` | Blog drafts and post archive; feeds the (future) Micropub publish pipeline. |
| `content/buttondown/` | Author-managed Buttondown newsletter config (automations, transactional, theme). |
| `docs/`, `notes/`, `reference/` | Architecture, staff, and editorial reference. |
| `tests/` | Python tests covering librarian / corpus / content / audio. |
| `Makefile`, `requirements.txt` | Production command surface and Python deps. |

## Status: live producer

Studio is now the canonical production source. The authoring bot commits canonical
issue content here; this repo's production workflow builds the archive, corpus, graph,
audio/status artifacts, deploys the Librarian runtime when needed, and hands generated
11ty inputs to `weekly.thingelstad.com`. Weekly is a render surface: it receives those
inputs, refreshes its own landing-page stats, builds Eleventy + Pagefind, and deploys
to GitHub Pages.
