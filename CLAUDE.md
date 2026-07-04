# CLAUDE.md — Studio

Orientation for Claude Code working in this repo. Read `AGENTS.md` first for
working commands and environment gotchas, `README.md` for the human overview,
and `ALIGNMENT.md` for the current cross-repo map.

## What this repo is

Studio is the **brain** behind Jamie's publishing: the Librarian API behind Thingy, the
five-agent staff (**Scout, Eddy, Linky, Marky, Patty**) that helps with *all* publishing,
and the **corpus** of all writing and drafts across every outlet — the blog, Another
Thing, and the Weekly Thing. Everything downstream — blog, newsletter, podcast, Thingy —
is a separate **surface** that consumes what Studio produces.

Since the 2026-06 rearchitecture, **productions** (newsletter / article / podcast /
project) are the unit of work, a private tailnet-only **web app** is the work surface
(Discord is the agents' room), authored content lives in the workshop **DB** (S3 is
publishing-only), and a **seeds** idea garden feeds new productions. **The one rule:
Jamie writes every word.** See `apps/workshop_bot/CLAUDE.md` ("The studio now") for the
full model.

The decision rule for where code belongs:

> If it's a publishing surface, it's its own repo/host, downstream. If it's *upstream* of
> publishing — capture, research, the editorial source of truth, production, or the staff —
> it lives here in Studio.

## Layout

- `apps/workshop_bot/` — the staff (Scout/Eddy/Linky/Marky/Patty), the productions
  state engine, the seeds idea garden, and the tailnet web app (`webapp/`). Studio core.
- `apps/librarian/` — Librarian API (Lambda + infra + admin). Deployed from Studio.
- `librarian-core/` — shared `librarian_core` package (corpus/graph/retrieval/links).
- `pipeline/` — production: build, stats, status, audio, corpus, graph, deploy.
- `data/issues/` — editorial source of truth (canonical issue content).
- `data/audio/` — audio production source (manifest, scripts, bumpers).
- `data/blog/` — blog drafts + post archive.
- `content/buttondown/` — Buttondown newsletter config (source of truth for the runtime).
- `docs/`, `notes/`, `reference/` — architecture, staff, editorial reference.
- `tests/` — Python tests (librarian / corpus / content / audio).

## Critical context — Studio is live

This repo was extracted from `weekly.thingelstad.com` with `git filter-repo` (history
preserved) and is now the live producer. Several hard constraints follow:

- **Studio is authoritative for anything that ships.** Canonical issue content,
  authoring agents, production pipelines, corpus generation, and the Librarian API live
  here. Weekly only renders generated inputs handed off from Studio.
- **The publishing path has no recovery flow.** A botched ship-path change can still
  skip a week. Treat workflow, bot, Buttondown, audio, and handoff changes as production
  changes.
- **Secrets live here by concern.** Studio holds production credentials for publishing,
  corpus/Lambda deploys, and the cross-repo handoff. Weekly should only retain secrets
  for its own landing-page stats fetch.
- **The Librarian API `/retrieve` is a versioned contract.** Thingy is a live client across
  a repo boundary — casual changes to the API break it. Version before changing.
- **Preserve history.** If more code moves in from `weekly`, use `git filter-repo` — never
  copy-paste.

## When in doubt

Check `ALIGNMENT.md` for repo boundaries and the phase docs for migration history. If a
task would alter the live publishing path, cross-repo handoff, API contract, or secrets,
stop and confirm with Jamie first.

**Keep the north star current:** any change to the staff, the production model, a
surface, or a repo boundary must update `ALIGNMENT.md` (and this file's "What this repo
is" section if the cast or model changed) in the same PR.
