# workshop_bot — Studio Runtime

Studio is now the private publishing website for **The Weekly Thing**
newsletter. This package contains the web app, Eddy's runtime, the newsletter
issue jobs, and the SQLite-backed source of truth for in-flight issues.

## Current Product

- **Scope:** newsletter issues only.
- **Surface:** the Studio web app is the primary operator surface.
- **Assistant:** Eddy is the only active assistant.
- **Rule:** Jamie writes every word.
- **Retired:** Scout, Linky, Marky, Patty, generic productions, projects, blog
  post production, podcast production, seeds, gardening, proactive slate/garden
  check-ins, and the S3/Shortcuts collaboration layer.

The `productions` table remains internally because newsletter issue windows are
mirrored there as `WT{n}` rows. Treat that as an implementation detail. Product
language should say **newsletter issue**, **current issue**, **editor**,
**preview**, **review**, and **publish**.

## Runtime

`apps/workshop_bot/bot.py` starts:

- Eddy's Discord client (`DISCORD_TOKEN_EDDY`)
- the private aiohttp Studio web app
- the small scheduler

Scheduled jobs are intentionally minimal:

- `sync-issue-daily` — daily source mirror from Pinboard + micro.blog into
  `issue_items`
- `follow-up-sweep` — Eddy follow-ups only

Publishing, review, and lifecycle transitions are web-driven. Slash commands are
repair/ad-hoc tools, not the normal workflow.

## Newsletter Flow

1. Create or open a newsletter issue.
2. Start working when it is ready to enter the live pipeline.
3. Sync sources into `issue_items`.
4. Edit issue atoms, Currently entries, cover metadata, and item ordering in the
   web UI.
5. Preview the issue live from the DB.
6. Run Eddy review on demand.
7. Save package fields: subject, description, haiku, Echoes, CTA/thanks.
8. Mark built, then publish email, website, and audio.
9. Put the issue to bed.

The DB is the draft. Renderers build from current DB state at preview/publish
time. S3 is publishing-only.

## Key Paths

- `webapp/routes.py` — Studio HTTP routes
- `webapp/templates/` — web UI templates
- `jobs/sync_issue.py` — source mirror
- `jobs/eddy_review.py` — on-demand editorial review
- `jobs/production_ops.py` — build/publish phase transitions
- `jobs/publish.py` — email, website, audio publish legs
- `jobs/put_to_bed.py` — file the shipped issue
- `tools/issue_items*.py` — issue item storage/rendering
- `tools/content_store.py` — DB-backed authored content blocks
- `tools/db/` — SQLite domain helpers and migrations

## Database

New schema goes in `db/schema.sql`. Existing DB changes go in
`tools/db/migrations.py` as a numbered `Migration(...)`. This repo uses
idempotent startup migrations.

The seeds/garden tables were deliberately dropped. Do not reintroduce idea
garden concepts without an explicit product decision.

## Tests

Use the repo-local virtualenv:

```sh
uv run --locked python -m unittest discover -s apps/workshop_bot/tests -t .
```

Use uv from the repo root; do not use bare `python`, `python3`, or pip-managed environments.
