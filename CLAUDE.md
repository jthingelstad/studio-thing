# CLAUDE.md — Studio

Orientation for Claude Code working in this repo. Read `README.md` for the human
overview and `STUDIO_MIGRATION_PLAN.md` for the full migration plan.

## What this repo is

Studio is the **brain** behind Jamie's publishing: the Librarian API behind Thingy, the
Discord-based authoring agents (**Eddy, Linky, Patty, Marky**) that help with publishing,
and the **corpus** of all writing and drafts across every outlet — the blog, Another
Thing, and the Weekly Thing. Everything downstream — blog, newsletter, podcast, Thingy —
is a separate **surface** that consumes what Studio produces.

The decision rule for where code belongs:

> If it's a publishing surface, it's its own repo/host, downstream. If it's *upstream* of
> publishing — capture, research, the editorial source of truth, production, or the staff —
> it lives here in Studio.

## Layout

- `apps/workshop_bot/` — the authoring staff (Eddy/Linky/Marky/Patty). Studio core.
- `apps/librarian/` — Librarian API (Lambda + infra + admin). Deployed from Studio.
- `librarian-core/` — shared `librarian_core` package (corpus/graph/retrieval/links).
- `pipeline/` — production: build, stats, status, audio, corpus, graph, deploy.
- `data/issues/` — editorial source of truth (canonical issue content).
- `data/audio/` — audio production source (manifest, scripts, bumpers).
- `data/blog/` — blog drafts + post archive.
- `content/buttondown/` — Buttondown newsletter config (source of truth for the runtime).
- `docs/`, `notes/`, `reference/` — architecture, staff, editorial reference.
- `tests/` — Python tests (librarian / corpus / content / audio).

## Critical context — this is a parallel-run, not a finished cutover

This repo was extracted from `weekly.thingelstad.com` with `git filter-repo` (history
preserved). The live monorepo **still publishes**. Several hard constraints follow:

- **`weekly` is still authoritative for anything that ships.** Studio is not yet the
  canonical production source. Do not assume code here is the one that runs in production.
- **The publishing path has no recovery flow.** A botched change before send day = a
  skipped week. Cutover is sequenced for *right after* a successful send, never before.
- **Secrets: add-then-remove, never remove-then-add.** A window with no valid key is a
  missed send.
- **The Librarian API `/retrieve` is a versioned contract.** Thingy is a live client across
  a repo boundary — casual changes to the API break it. Version before changing.
- **Preserve history.** If more code moves in from `weekly`, use `git filter-repo` — never
  copy-paste.

## When in doubt

Check `STUDIO_MIGRATION_PLAN.md` for which phase a change belongs to and what gate it must
clear first. The most important test in the whole migration is the Phase 1 artifact diff:
inputs Studio pushes must match the old path **byte-for-byte** before cutover. If a task
would alter the live publishing path or touch secrets, stop and confirm with Jamie first.
