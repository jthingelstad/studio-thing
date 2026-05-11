# Workshop Content Loop — Implementation Progress

## Completed
- [2026-05-11] Step 1 — Decommission inbox + persona-scratchpad machinery; rename `s3_issues__*` → `workspace__*`; `/workshop next-issue` → `/workshop job start-issue` (now a `job` subcommand group); drop `agent_inbox` table; remove `WORKSHOP_BUCKET`. 203 tests pass.
- [2026-05-11] Step 2 — Heartbeat prompts (eddy/linky/patty/marky) now open with an `issue__current_window` guard: PASS+stop when no active window, or when today is outside `[start_date, pub_date]` (Marky also keeps running while a campaign is live). 203 tests pass.
- [2026-05-11] Step 3 — Job runtime: `jobs/_base.py` (JobContext, single-asset locking via `job_locks` table + dead-pid steal, draft-block replace/get helpers), `templates/draft_starter.md`, `jobs/start_issue.py` / `update_draft.py` (stub fills) / `issue_status.py`; `/workshop job start-issue|update-draft|issue-status` wired. New `test_content_jobs.py`. 221 tests pass.
- [2026-05-11] Step 4 — Real fills (`notable`/`brief` from Pinboard `issue_window_candidates`, `journal` from micro.blog JSON Feed, all gracefully degrading), `tools/draft.py` (`section_status`), `tools/context.py` (`build_eddy_context` + delta), `draft_digests` table + helpers, `draft__section_status` agent tool, `update-draft` refuses when `final.md` exists + writes a digest + runs Eddy's post-update review (Tue–Fri only, model scales haiku→sonnet), `prompts/eddy/update-review.md`, daily 17:00 CT `update-draft-daily` cron via new `handlers.content_job` bridge (scheduler `JobContext`/`Runner` now carry `deps`). 239 tests pass. Live Pinboard/micro.blog/Anthropic paths are unit-tested with stubs; the Tue–Fri end-to-end card and the actual `MICROBLOG_FEED_URL` need a human eye.

## Blockers
(none — S3 versioning on `files.thingelstad.com` confirmed `Enabled`; the Step-4 pre-flight is satisfied)

## Notes
- **`apps/workshop_bot/CLAUDE.md` does not exist.** The brief (Step 8.5) says "The existing apps/workshop_bot/CLAUDE.md describes the prior design…" but there is no such file in the repo. Step 8.5 will *create* it new (and update the project-root CLAUDE.md). The repo-root CLAUDE.md's workshop_bot section is the only existing project memory for this app.
