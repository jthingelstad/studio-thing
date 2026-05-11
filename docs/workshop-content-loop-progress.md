# Workshop Content Loop — Implementation Progress

## Completed
- [2026-05-11] Step 1 — Decommission inbox + persona-scratchpad machinery; rename `s3_issues__*` → `workspace__*`; `/workshop next-issue` → `/workshop job start-issue` (now a `job` subcommand group); drop `agent_inbox` table; remove `WORKSHOP_BUCKET`. 203 tests pass.

## Blockers
(none — S3 versioning on `files.thingelstad.com` confirmed `Enabled`; the Step-4 pre-flight is satisfied)

## Notes
- **`apps/workshop_bot/CLAUDE.md` does not exist.** The brief (Step 8.5) says "The existing apps/workshop_bot/CLAUDE.md describes the prior design…" but there is no such file in the repo. Step 8.5 will *create* it new (and update the project-root CLAUDE.md). The repo-root CLAUDE.md's workshop_bot section is the only existing project memory for this app.
