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
| `campaign-sunset <name>` | manual | Sets a campaign's status to `sunset` — `daily-metrics` stops polling it. |
| `set-goal <kind> <value> [notes]` | manual | Opens a new active goal in the `goals` table (`kind` ∈ `members`/`dollars`). Refuses if one's already active (close it with `goal-achieved` first — the table allows one row with `achieved_at IS NULL`). |
| `goal-achieved [notes]` | manual | Marks the active goal achieved (today); `notes` is appended to whatever was recorded at `set-goal` time. |

Plus one non-`job` subcommand: **`/workshop status`** — a read-only DB-only ops snapshot (active issue window, active goal/campaigns, any held `job_locks`, the last few `agent_runs`). Distinct from `/workshop job issue-status` (the in-flight issue's *content* completeness) and `/workshop job campaign-report` (campaign perf vs expected). Source: `jobs/status.py`; `set-goal`/`goal-achieved`/`campaign-sunset` are in `jobs/ops.py` (tiny, no-LLM).

Scheduler: `scheduler/jobs.py` declares the cron `JobSpec`s; `scheduler/handlers.py` has `content_job` (the bridge cron→jobs, wired as `functools.partial(content_job, job="<name>")`) and `rss_check` (poll the feed, dedupe via `agent_notes`, auto-fire `promotion-prep`). There are **no per-persona heartbeats** — everything an agent does on a cadence is a job.

Slash dispatch (`personas/commands.py`): the fast jobs `defer` → run → ack with the result (the followup send is wrapped in try/except — a Discord interaction token only lasts ~15 min). The **interactive** jobs (`create-final`, `compose-haiku`/`-meta`/`-cta` — they post options to a channel and wait for Jamie's reaction, which can outlast the token) instead ack *immediately* ("started — react in #editorial / #supporters") and then run; the job posts its own outcome to the channel, so no second followup is needed. `/workshop status` is the one subcommand attached directly to the `workshop` group rather than under `job` (it's a bot-health view, not a content-loop job) — Discord allows a command group to hold both a subcommand and a subcommand-group.

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
- **SQLite** `apps/workshop_bot/data/workshop.db` — everything else. Tables: `agent_outputs`, `agent_runs`, `agent_notes`, `issue_windows`, `link_candidates`, `pinboard_popular_seen`, `pinboard_research_done`, `subscriber_events_seen`, `thingy_tokens`, `thingy_requests`; **new in the content-loop redesign:** `job_locks`, `draft_digests`, `goals`, `campaigns`, `campaign_metrics`.

There is **no private workshop bucket** anymore. Decommissioned in the redesign: `s3://weekly-thing-workshop/`, the `WORKSHOP_BUCKET` env var, `tools/persona_s3.py` + the `s3_personas__*` tools, `tools/inbox.py` + the `agent_inbox` table + the `inbox__*` tools, the reserved-but-never-wired `analytics` / `supporter_events` / `channel_routes` tables, the `/workshop heartbeat` and `/workshop next-issue` slash commands. `s3_issues__*` was renamed to `workspace__*`. `db/schema.sql` carries a `DROP TABLE IF EXISTS` for each dropped table so a long-lived DB converges with a fresh install.

## Conventions worth remembering

- **Pinboard tag convention is strict: only `_brief`.** Untagged-in-window = Notable; `_brief` = Briefly. The old `_featured` tag/section is retired. `pinboard__capture_blurb` writes a blurb verbatim + tags `_brief` + clears `toread` atomically.
- **`pinboard__popular_unseen` filters avoid-domains.** Before the `pinboard_popular_seen` dedup it drops items whose host is on `tools/avoid_domains.py`'s exclusion set (own domains, Buttondown, image CDNs, URL shorteners, social, Wikipedia, YouTube/Spotify/Vimeo, generic CDNs) — so Linky never even considers a "popular on Pinboard" Wikipedia article or t.co redirect as a possible Notable. That list is a hand-maintained *copy* of `pipeline/content/domain_exclusions.py` (`pipeline/` isn't importable from here); keep them loosely in sync — an exact match isn't required since this only gates Linky's scan, nothing it touches ships.
- **micro.blog: pull everything in window, no tag filtering** (`tools/microblog.py`). Uses the Micropub source query (`GET {MICROBLOG_MICROPUB_URL}?q=source`, `Authorization: Bearer MICROBLOG_API_KEY`) — returns posts as mf2-JSON with `properties.content` carrying the **native markdown Jamie wrote** (a string; micro.blog embeds photo uploads as `<img src=…>` tags inside it). `MICROBLOG_API_KEY` is **required** — no fallback; if micro.blog is down, `journal.fill` leaves a placeholder line (Eddy's review flags it). Filtering/curation happens at `create-final` (Eddy can cut Journal entries).
- **Journal images are rehosted** (`tools/journal_images.py`, called from `journal.fill`). Each `<img>` / `![]()` on an upload host (`MICROBLOG_IMAGE_HOSTS`, default `www.thingelstad.com` `/uploads/`, `micro.thingelstad.com`, `cdn.uploads.micro.blog`, `uploads.micro.blog`) is downloaded, resized to `MICROBLOG_IMAGE_MAX_DIM` (default 600px long side, downscale-only; JPEG q80 / PNG optimized), and copied into `weekly-thing/{N}/journal/<name>` (reusing the micro.blog hash basename), then the reference is rewritten to the local URL and `<img>` tags are normalized to `![alt](url)`, each on its own paragraph (so adjacent gallery `<img><img>` don't run together). A HEAD-skip makes daily re-runs cheap; a per-image failure leaves that one's original URL alone. Binary writes go through `s3.write_journal_image` (image-only allowlist, `journal/` sub-prefix; *not* an agent tool). `update-draft` runs `_gather_fills` (the blocking source pulls + image rehosting + the HTML-preview write) via `asyncio.to_thread`.
- **Browser-viewable HTML previews.** `update-draft` / `create-final` / `build-publish` write a `.html` twin alongside their `.md` (`draft.html` / `final.html` / `publish.html` in the workspace) via `tools.render` (Python-Markdown → a self-contained styled page; `draft`/`final` strip the block markers and get a "DRAFT…/FINAL…" banner, `publish` renders clean). They're uploaded with `Cache-Control: no-cache` and a CloudFront invalidation of that path (`tools.cdn.invalidate`, distribution `WEEKLY_THING_CDN_DISTRIBUTION_ID`, default the prod one; set to empty to disable) — so Jamie always sees the latest at `https://files.thingelstad.com/weekly-thing/{N}/draft.html` etc. The URL is surfaced in the job's result and (for `update-draft`, Tue–Fri) appended to Eddy's review card. Best-effort: a render/invalidation hiccup never fails the job. The pages carry a `<meta name="robots" content="noindex,nofollow">` and `files.thingelstad.com/robots.txt` is already `Disallow: /`, so the in-progress drafts aren't indexed (they *are* publicly reachable by URL — same as `draft.md` always has been on that public prefix).
- **Off-loop source pulls.** Jobs that hit external APIs from inside the bot's asyncio loop wrap the blocking calls in `asyncio.to_thread` so a slow Pinboard/Buttondown/Tinylytics/RSS/S3 round trip doesn't stall the gateway: `update-draft` (`_gather_fills` — Pinboard + micro.blog + image rehost + HTML render), `pinboard-scan` (`build_linky_context`), `daily-metrics` (campaign polls + `subscriber_growth` + `tinylytics.summary` + `build_marky_context`), `promotion-prep` (RSS lookup + `publish.md` read + `build_marky_context`). Agent-loop calls (`bot.core`) are already thread-wrapped in `agent_loop.py`.
- **Marky operates on the last *published* issue**, not the in-flight one — the RSS feed (`tools/rss.py`) is her trigger; she reads `publish.md`.
- **`update-draft` is a pure projection** — never an additive merge. Real authoring lives upstream. Re-running it gives the same output modulo upstream changes.
- **Job prompts get a `## Today` dynamic-context block.** Read it; don't recompute date math / counts / queue depth / goal progress.
- Prompt name → file: `team` → `prompts/shared/team.md`; `<persona>` → `prompts/<persona>/prompt.md`; `<persona>-<file>` → `prompts/<persona>/<file>.md` (e.g. `eddy-update-review`, `linky-pinboard-scan`, `marky-promotion-prep`, `patty-compose-cta`). Edits need a bot restart (prompts are cached at first read).
- New schema → `db/schema.sql` (idempotent — re-runs every boot; the `goals` seed uses `WHERE NOT EXISTS`); new *columns* on existing tables → `db._COLUMN_MIGRATIONS`.
- Tests: `python -m unittest discover -s apps/workshop_bot/tests -t .` — discord/anthropic/httpx stubbed (`tests/_stubs.py`); S3/Pinboard/micro.blog/Anthropic stubbed per-test. ~300 tests. Don't hit the network in tests.

## Known follow-ups (as of this writing)

- `create-final` does a single approval round (Eddy proposes the whole reordered body); the brief's per-section loop is a refinement.
- The broader buttondown/tinylytics/stripe tool-surface prune/rename the brief mentions is deferred — only `buttondown__campaign_signups` / `tinylytics__campaign_traffic` were added.
- `pipeline/content/content.py publish` (create a Buttondown draft from `publish.md` + `metadata.json`) is implemented but untested against the live API.
- iOS Shortcuts pipeline stays as a recovery tool until 3–4 successful ships via the new flow (Step 9 of the brief — not yet done).
- micro.blog's `q=source` returns ~100 recent posts (no documented date filter / pagination on that query) — fine for a week's window; if a double issue ever needs more, revisit. `MICROBLOG_IMAGE_HOSTS` defaults assume `www.thingelstad.com` / `cdn.uploads.micro.blog`; adjust if Jamie's upload host differs.
