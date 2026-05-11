# workshop_bot — project memory

> Author-only Discord bot for *The Weekly Thing*. Helps Jamie assemble each week's issue and ships supporting bits (link curation, membership CTA, promotion drafts). One Python process, several `discord.py` clients (one per persona, own token/avatar), plus an APScheduler instance — all in the same asyncio loop.

Full design rationale: [`docs/workshop-content-loop-design-brief.md`](../../docs/workshop-content-loop-design-brief.md). The user-facing overview is [`README.md`](README.md). This file is the "what to keep in mind when working here" memory.

## Architecture: jobs are the spine

Every workshop_bot action — pulling content into the draft, reordering for the final, composing CTAs, drafting promotion copy — is a **job**: deterministic Python in `apps/workshop_bot/jobs/`, fired by the `/workshop job <name>` slash surface (host: Eddy) and/or by cron. Some jobs make small encapsulated LLM calls (Eddy's draft review, the compose-* jobs, Marky's reports); most are pure Python. The job is the unit of scheduling and on-demand execution.

`jobs/_base.py` is the runtime: `JobContext` (carries `deps` — corpus/registry/team — and a `trigger` label; has `channel()` / `post()` helpers), `JobResult` (`{ok, message, data}` — `message` is acked to the invoker), single-asset locking (`job_lock([assets], name)` context manager backed by the `job_locks` SQLite table — two jobs that write the same file can't overlap; a lock held by a dead pid is stolen since a restart gets a new pid), and the draft-block helpers (`replace_block` / `get_block` for the `<!-- block:NAME -->` … `<!-- /block:NAME -->` markers in `draft.md`).

### The jobs

| Job | Trigger | What it does |
|---|---|---|
| `start-issue <n> <pub-date> <days>` | manual | Records the issue window in `workshop.db`, seeds `draft.md` from `templates/draft_starter.md`, auto-fires `update-draft`. The only job that takes the issue number explicitly. |
| `update-draft` | daily 17:00 CT + after `start-issue` + manual | Pure projection: fills the draft's section blocks from upstream (Pinboard for Notable/Briefly, micro.blog for Journal) and from standalone asset files (`intro.md` / `currently.md` / `haiku.md`). Idempotent; replaces block content wholesale. Writes a `draft_digests` row; on Tue–Fri runs Eddy's post-update review (`prompts/eddy/update-review.md`) → `#editorial`; silent Sat/Sun/Mon. Refuses (loudly) if `final.md` exists — the issue is locked. |
| `issue-status` | manual | Read-only section + asset completeness report. |
| `create-final` | manual | Eddy proposes a reordered/curated final (fenced markdown block); Jamie ✅/❌/🔄; writes `final.md`; posts "next: run compose-haiku/meta/cta, then build-publish". No auto-chain — each downstream job is run on demand and refuses-with-a-list until its prerequisites exist. |
| `compose-haiku` | manual | Eddy returns JSON haiku options → `#editorial`; Jamie picks → `haiku.md`. Required for ship. |
| `compose-meta` | manual | Eddy returns JSON (subject, description) options → `#editorial`; Jamie picks → `metadata.json` (subject/description generated; image/slug/number/publish_date deterministic). Reads `data/buttondown/emails/*.json` for recent subjects to avoid repetition. Required for ship. |
| `compose-cta` | manual | Patty decides 0/1/2 CTAs, 1–2 framings each, in **Thingy's** voice; → `#supporters`; Jamie picks per slot → `cta-1.md` / `cta-2.md` (each with `placement:` YAML frontmatter). Optional. |
| `build-publish` | manual | Assembles `publish.md` section by section from `final.md`'s blocks + `intro.md` / `haiku.md` / `currently.md` + CTAs at their placements — each section emitted as `## Header\n\n{content}` only if non-empty (an absent optional section just drops out), no block markers in the output. Refuses with a missing-list (→ `#editorial`) if any required asset is absent: `final.md`, `haiku.md`, `metadata.json`, `intro.md`, `cover.jpg`. |
| `pinboard-scan` | Mon–Fri 06:30 & 18:30 CT during the issue window; manual | Linky's four-lane Pinboard pass (popular review / toread tending / Briefly capture / read-length + queue-depth) → `#research`. Active only when an issue window is set and today ∈ `[start_date, end_date]`. |
| `promotion-prep` | auto on RSS detection; manual | Marky drafts syndication content (LinkedIn + r/WeeklyThing megathread + per-link threads, 2–3 framings each) for the latest *published* issue's `publish.md` → `#promotion`. Never auto-posts. |
| `daily-metrics` | daily 19:00 CT; manual | Polls active campaigns (Tinylytics `?ref=` traffic + Buttondown ref signups → a `campaign_metrics` row each run), checks subscriber growth + engagement; PASSes silently when nothing material moved, else Marky composes a terse report → `#promotion`. |
| `add-campaign <name> <ref> [signups] [traffic]` | manual | Inserts a row into the `campaigns` table. |
| `campaign-report` | manual | Active campaigns + current performance vs expected. |

Scheduler: `scheduler/jobs.py` declares the cron `JobSpec`s; `scheduler/handlers.py` has `content_job` (the bridge cron→jobs, wired as `functools.partial(content_job, job="<name>")`) and `rss_check` (poll the feed, dedupe via `agent_notes`, auto-fire `promotion-prep`). There are **no per-persona heartbeats** — everything an agent does on a cadence is a job.

Slash dispatch (`personas/commands.py`): the fast jobs `defer` → run → ack with the result (the followup send is wrapped in try/except — a Discord interaction token only lasts ~15 min). The **interactive** jobs (`create-final`, `compose-haiku`/`-meta`/`-cta` — they post options to a channel and wait for Jamie's reaction, which can outlast the token) instead ack *immediately* ("started — react in #editorial / #supporters") and then run; the job posts its own outcome to the channel, so no second followup is needed.

### The unified asset pattern

Every piece of issue content is a standalone file in the S3 workspace `s3://files.thingelstad.com/weekly-thing/{N}/`:

- `intro.md`, `currently.md` — Jamie writes (Drafts → Shortcut); `update-draft` reads them into the draft.
- `haiku.md` — `compose-haiku` writes; `metadata.json` — `compose-meta` writes; `cta-1.md` / `cta-2.md` — `compose-cta` writes.
- `draft.md` — `update-draft` writes (a regenerable pure projection of all the above + upstream).
- `final.md` — `create-final` writes (post-Eddy ordering; still block-structured).
- `publish.md` — `build-publish` writes (sections assembled `## Header\n\n{content}`, empties dropped, no block markers; the artifact `pipeline/content/content.py publish --issue N` pushes to Buttondown as a draft).
- `cover.jpg`, `cover-large.jpg`, `journal/*.jpg`, `body-{N}.mp3`, `weekly-thing-{N}.mp3` — written by the iOS Shortcuts and `pipeline/audio/`; agents can't touch them (the `tools/s3.py` extension allowlist is text-only). `eddy-edits.md` — Eddy, rarely, for a preserved revision proposal.

`tools/draft.py` (`section_status`) parses the draft for section item counts + asset presence + what's still missing for ship; `draft__section_status` is the agent tool over it. `tools/context.py` builds the per-persona dynamic-context blocks (`build_eddy_context` / `build_linky_context` / `build_patty_context` / `build_marky_context`) — runtime-computed facts injected into job prompts so the model doesn't recompute date math, word counts, queue depths, goal progress.

`tools/interaction.py` is the reaction primitive (`await_choice` / `await_approval`) — post options, wait for Jamie's reaction (filtered on `DISCORD_OWNER_USER_ID`), return the pick. Jobs hold their asset lock for the duration of the interaction.

## The personas now

- **Eddy** (`#editorial`) — Discord client; job-triggered (`update-draft` review, `create-final`, `compose-haiku`/`-meta`). No heartbeat. Mention-driven asks still work. Hosts the `/workshop` slash tree.
- **Linky** (`#research`) — Discord client; job-triggered (`pinboard-scan`, Mon–Fri 06:30/18:30 during the issue window). Pinboard ↔ `#research` ↔ Jamie is the whole loop — no agent-to-agent handoffs.
- **Patty** (`#supporters`) — persona prompt only; no heartbeat, no inbox. Her one job is `compose-cta`. Composes in **Thingy's** voice (the public librarian persona); Patty is invisible to readers. Milestone-driven via the `goals` table.
- **Marky** (`#promotion`) — persona prompt only beyond rendering messages. Jobs: `promotion-prep` (RSS-triggered) and `daily-metrics` (cron). Drafts syndication copy in **Jamie's** voice — highest-stakes voice work; mitigated by multiple framings and never auto-posting. Owns the campaign ledger.
- **Thingy** (`#ask-thingy`) — unchanged: the public-archive bridge to the Librarian Lambda. Not a teammate; isolated surface.

## Storage — two layers, hard boundary

- **Public S3** `s3://files.thingelstad.com/weekly-thing/{N}/` — only what ships (text/JSON via the `tools/s3.py` allowlist, plus binaries written by other pipelines). Backs the `workspace__*` tools (`workspace__list_all` / `list_files` / `read` / `write`).
- **SQLite** `apps/workshop_bot/data/workshop.db` — everything else. Tables: `agent_outputs`, `agent_runs`, `agent_notes`, `issue_windows`, `link_candidates`, `pinboard_popular_seen`, `pinboard_research_done`, `subscriber_events_seen`, `thingy_tokens`, `thingy_requests`; **new in the content-loop redesign:** `job_locks`, `draft_digests`, `goals`, `campaigns`, `campaign_metrics`. Reserved/unused: `analytics`, `supporter_events`, `channel_routes`.

There is **no private workshop bucket** anymore. Decommissioned in the redesign: `s3://weekly-thing-workshop/`, the `WORKSHOP_BUCKET` env var, `tools/persona_s3.py` + the `s3_personas__*` tools, `tools/inbox.py` + the `agent_inbox` table + the `inbox__*` tools, the `/workshop heartbeat` and `/workshop next-issue` slash commands. `s3_issues__*` was renamed to `workspace__*`.

## Conventions worth remembering

- **Pinboard tag convention is strict: only `_brief`.** Untagged-in-window = Notable; `_brief` = Briefly. The old `_featured` tag/section is retired. `pinboard__capture_blurb` writes a blurb verbatim + tags `_brief` + clears `toread` atomically.
- **micro.blog: pull everything in window, no tag filtering** (`tools/microblog.py`). Uses the Micropub source query (`GET {MICROBLOG_MICROPUB_URL}?q=source`, `Authorization: Bearer MICROBLOG_API_KEY`) — returns posts as mf2-JSON with `properties.content` carrying the **native markdown Jamie wrote** (a string; micro.blog embeds photo uploads as `<img src=…>` tags inside it). `MICROBLOG_API_KEY` is **required** — no fallback; if micro.blog is down, `journal.fill` leaves a placeholder line (Eddy's review flags it). Filtering/curation happens at `create-final` (Eddy can cut Journal entries).
- **Journal images are rehosted** (`tools/journal_images.py`, called from `journal.fill`). Each `<img>` / `![]()` on an upload host (`MICROBLOG_IMAGE_HOSTS`, default `www.thingelstad.com` `/uploads/`, `micro.thingelstad.com`, `cdn.uploads.micro.blog`, `uploads.micro.blog`) is downloaded, resized to `MICROBLOG_IMAGE_MAX_DIM` (default 600px long side, downscale-only; JPEG q80 / PNG optimized), and copied into `weekly-thing/{N}/journal/<name>` (reusing the micro.blog hash basename), then the reference is rewritten to the local URL and `<img>` tags are normalized to `![alt](url)`. A HEAD-skip makes daily re-runs cheap; a per-image failure leaves that one's original URL alone. Binary writes go through `s3.write_journal_image` (image-only allowlist, `journal/` sub-prefix; *not* an agent tool). `update-draft` runs `_gather_fills` (the blocking source pulls + image rehosting) via `asyncio.to_thread`.
- **Marky operates on the last *published* issue**, not the in-flight one — the RSS feed (`tools/rss.py`) is her trigger; she reads `publish.md`.
- **`update-draft` is a pure projection** — never an additive merge. Real authoring lives upstream. Re-running it gives the same output modulo upstream changes.
- **Job prompts get a `## Today` dynamic-context block.** Read it; don't recompute date math / counts / queue depth / goal progress.
- Prompt name → file: `team` → `prompts/shared/team.md`; `<persona>` → `prompts/<persona>/prompt.md`; `<persona>-<file>` → `prompts/<persona>/<file>.md` (e.g. `eddy-update-review`, `linky-pinboard-scan`, `marky-promotion-prep`, `patty-compose-cta`). Edits need a bot restart (prompts are cached at first read).
- New schema → `db/schema.sql` (idempotent — re-runs every boot; the `goals` seed uses `WHERE NOT EXISTS`); new *columns* on existing tables → `db._COLUMN_MIGRATIONS`.
- Tests: `python -m unittest discover -s apps/workshop_bot/tests -t .` — discord/anthropic/httpx stubbed (`tests/_stubs.py`); S3/Pinboard/micro.blog/Anthropic stubbed per-test. ~300 tests. Don't hit the network in tests.

## Known follow-ups (as of this writing)

- `create-final` does a single approval round (Eddy proposes the whole reordered body); the brief's per-section loop is a refinement.
- The broader buttondown/tinylytics/stripe tool-surface prune/rename the brief mentions is deferred — only `buttondown__campaign_signups` / `tinylytics__campaign_traffic` were added.
- `popular_unseen` dedups against `pinboard_popular_seen` only; the avoid-domains list isn't wired.
- `pipeline/content/content.py publish` (create a Buttondown draft from `publish.md` + `metadata.json`) is implemented but untested against the live API.
- iOS Shortcuts pipeline stays as a recovery tool until 3–4 successful ships via the new flow (Step 9 of the brief — not yet done).
- micro.blog's `q=source` returns ~100 recent posts (no documented date filter / pagination on that query) — fine for a week's window; if a double issue ever needs more, revisit. `MICROBLOG_IMAGE_HOSTS` defaults assume `www.thingelstad.com` / `cdn.uploads.micro.blog`; adjust if Jamie's upload host differs.
