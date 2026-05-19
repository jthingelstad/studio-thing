# Workshop Bot — Discord Agent Runtime

> Author-only Discord bot for *The Weekly Thing*. Four agents that help Jamie assemble each week's issue: Eddy (editor), Linky (curator), Marky (promotion), Patty (supporter steward). The reader-facing public Q&A bot (Thingy) lives in a separate process at [`../thingy_bridge/`](../thingy_bridge/).

---

## What lives here

`apps/workshop_bot/` is one Python process running four `discord.py` clients in the same asyncio loop. Each persona is a separate Discord application (own bot token, own avatar) so messages appear under the right name.

| Persona | Role | Default model | Home channel |
|---|---|---|---|
| **Eddy** (he/him) | Editor — `update-draft` reviews (Tue–Fri), `create-final` reorder, `compose-haiku`/`-meta`. No heartbeat; mention-driven asks still work. | Opus 4.7 | `#editorial` |
| **Linky** (he/him) | Link curation — `pinboard-scan` every 3h from 07:05–22:05 CT, year-round. Pinboard ↔ `#research` ↔ Jamie; no agent-to-agent handoffs. | Sonnet 4.6 | `#research` |
| **Marky** (she/her) | Promotion — `promotion-prep` (RSS-triggered post-ship) + `daily-metrics` (daily); owns the campaign ledger. Drafts in Jamie's voice; never auto-posts. | Sonnet 4.6 | `#promotion` |
| **Patty** (she/her) | Supporter steward — `compose-cta` writes the per-issue membership CTA in **Thingy's** voice (Patty is invisible to readers; voice anchor in `prompts/shared/thingy-voice-reference.md`). Milestone-driven via the `goals` table. | Sonnet 4.6 | `#supporters` |

Each persona hosts its own slash tree on its own Discord bot: `/eddy …` on Eddy's bot, `/linky …` on Linky's, etc. The four agent personas share **almost** the full agent-tool surface — every tool is available to every persona, with two privacy-scoped exceptions: `stripe__*` is restricted to Patty (donor data should never enter the other personas' surfaces) and `pinboard__*` to Linky (mutating bookmark tools). Lane discipline otherwise lives in the persona prompts, not in a per-persona allowlist. Tools follow `<system>__<action>` naming (`archive__search`, `memory__remember`, `buttondown__list_subscribers`, `workspace__read`). External-system tool surfaces live under `apps/workshop_bot/systems/<name>/`; local helpers live under `apps/workshop_bot/tools/`. Both are composed into the same `ToolRegistry` at boot. A system can declare `restricted_to = {"<persona>", ...}` to scope visibility — `ToolRegistry.names_for(persona)` filters and `dispatch()` enforces (defense in depth, even if a model invents a name for a restricted tool).

The reader-facing Thingy bot — `#ask-thingy`, the operator-side conversation mirror, and the `/thingy {recent,show,sync}` commands — lives in [`../thingy_bridge/`](../thingy_bridge/) as a separate Python process. See that app's README for its launch story.

---

## Project context

Other components in the larger system:
- **thingy_bridge** at [`../thingy_bridge/`](../thingy_bridge/) — the Discord bridge to Thingy. Separate process; reader-facing surface.
- **Librarian Lambda** at `apps/librarian/lambda/` — production agent for reader Q&A. The bridge process forwards to it; workshop_bot doesn't talk to it.
- **Eleventy site** — `weekly.thingelstad.com` static site.
- **Buttondown** — email delivery platform. workshop_bot's `send-to-buttondown` job pushes `buttondown.md` as a draft (POST first time, PATCH on every re-run via a stored `buttondown_id`). Jamie schedules + sends from the Buttondown UI; no operator-side pull/sync.
- **Shortcuts pipeline** — Jamie's iOS Shortcuts assemble each issue Sunday morning, reading from `s3://files.thingelstad.com/weekly-thing/{N}/`.

---

## Routing

Each agent persona (Eddy/Linky/Marky/Patty) responds when:
- the persona is @-mentioned in any channel,
- a human posts in its home channel without @-mentioning a different persona,
- the `@Team` role is mentioned (one bot wins the lock and orchestrates a sequential round; later personas see earlier replies in their history),
- another bot posts in `#workshop` (peer reactions; default response is the literal token `PASS`).

The reader-facing Thingy bot listens only in `#ask-thingy` and runs in [`../thingy_bridge/`](../thingy_bridge/) (separate process). It never appears in the workshop. It may post operator-side conversation cards to `#chatter` via its hourly `thingy-watch` job — those are informational, not part of any team round.

---

## Memory

Each agent has long-term memory via `memory__remember` / `memory__recall` / `memory__forget` tools backed by an `agent_notes` SQLite table. Notes are shared across personas and attributed by author. Use cases: tonal preferences Jamie expressed, themes building across weeks, todos for future runs, observations worth carrying forward.

(The earlier `agent_inbox` typed-handoff surface was decommissioned in the content-loop redesign — the new architecture is closed-loop with no agent-to-agent messaging; Jamie is the integrator.)

Thingy users (web and Discord) also have per-user memory in the Lambda's DynamoDB table — but that surface lives in [`../thingy_bridge/`](../thingy_bridge/) now, not here. See `docs/librarian.md` and the bridge's CLAUDE.md for the Thingy-side specifics.

---

## Jobs (the spine)

Every workshop_bot action is a **job** — deterministic Python in `apps/workshop_bot/jobs/`, fired by a per-persona slash tree (`manage_guild`-gated) and/or by cron. Each persona hosts its own tree on its own bot:

- `/eddy issue {start,update,status,final,haiku,subject,publish}` · `/eddy status` · `/eddy review` · `/eddy archive` · `/eddy followup {list,add,cancel}`
- `/linky scan` · `/linky research` · `/linky pile` · `/linky stats` · `/linky followup {list,add,cancel}`
- `/marky prep` · `/marky metrics` · `/marky engagement` · `/marky referrers` · `/marky campaign {add,edit,report,copy,sunset}` · `/marky followup {list,add,cancel}`
- `/patty cta` · `/patty goal {set,done}` · `/patty progress` · `/patty nonprofit` · `/patty supporters` · `/patty followup {list,add,cancel}`

(The `/thingy {recent,show,sync}` operator commands live in [`../thingy_bridge/`](../thingy_bridge/) — a separate process.) `jobs/_base.py` is the runtime (`JobContext`, `JobResult`, single-asset `job_lock`, draft-block helpers). See [`CLAUDE.md`](CLAUDE.md) for the full job table (and the job-name → slash-command map) and [`docs/workshop-content-loop-design-brief.md`](../../docs/workshop-content-loop-design-brief.md) for the design.

Issue-assembly flow: `/eddy issue start` → `/eddy issue update` (pure projection of Pinboard/micro.blog/asset files into `draft.md`; Eddy reviews Tue–Fri) → `/eddy issue final` (Eddy reorder → `final.md`) → `/eddy issue haiku` / `/eddy issue subject` / `/patty cta` (run on demand, any order) → `/eddy issue publish` (assembles `buttondown.md`; refuses with a missing-list until the required assets exist). Parallel: `/linky scan` (Linky), `/marky prep` + `/marky metrics` + `/marky campaign add` / `/marky campaign report` / `/marky campaign sunset` (Marky). Ledger pokes: `/patty goal set` / `/patty goal done` (Patty's milestone progression) and `/marky campaign sunset` are tiny no-LLM commands. **Follow-ups** (`followup__schedule` agent tool / `/eddy followup add`, `/linky followup add`, etc.) let an agent — or Jamie — register a commitment ("I'll check in tomorrow evening", "when we get to issue 387"); the hourly `follow-up-sweep` fires the due ones (runs the persona's agent loop with the note + context, posts the check-in) — the deliberate, targeted replacement for per-persona heartbeats. `/eddy status` is a read-only ops snapshot — active issue window, active goal/campaigns, any held job locks, the last few `agent_runs`.

Scheduled (`scheduler/jobs.py`, Central time):

| Job | When | Shape |
|---|---|---|
| `update-draft-daily` | daily 17:00 | `content_job` → `jobs/update_draft.py`; PASSes if no issue in flight / locked |
| `linky-pinboard-scan` | every 3h, 07:05–22:05 | `content_job` → `jobs/pinboard_scan.py`; PASSes when source lists are empty |
| `marky-rss-check` | Sat & Sun, every 4h 09–21 | `handlers.rss_check` — detects a new published issue, fires `promotion-prep` |
| `marky-daily-metrics` | daily 19:00 | `content_job` → `jobs/daily_metrics.py`; PASSes silently when nothing moved |
| `follow-up-sweep` | hourly (:23) | `content_job` → `jobs/follow_up.py`; fires due agent follow-ups (time-based or "when the issue hits N") — runs the persona's agent loop, posts the check-in; PASSes when nothing's due |

There are no per-persona heartbeats — everything an agent does on a cadence is a job (the closest thing to an agent acting on its own is `follow-up-sweep` firing a commitment the agent itself scheduled via `followup__schedule`). The slash layer dispatches *fast* jobs as defer → run → ack, and *interactive* jobs (`create-final`, `compose-haiku`/`-meta`/`-cta` — they wait on Jamie's reaction, possibly longer than the ~15-min interaction token) as ack-immediately → run → the job posts its own outcome to the channel. (`/eddy status` sits directly under the `/eddy` group rather than in the issue subgroup — it's a bot-health view, not an issue verb.) CLI: `python -m apps.workshop_bot.scheduler.runner --list`. Disable the scheduler with `WORKSHOP_SCHEDULER_ENABLED=0`.

---

## The in-flight issue

The published archive (corpus) holds issues already shipped — `#1` through `#N`. The issue Jamie is *currently writing* is `#N+1` and lives in the S3 workspace at `s3://files.thingelstad.com/weekly-thing/{N+1}/` — **not in the archive corpus.** This S3 prefix is shared with the published archive (every shipped issue's folder lives at `weekly-thing/{N}/` too — that's where Shortcuts puts cover images, journal photos, etc.); the in-flight issue is just the highest-numbered folder. Jamie sets the active issue window via the `/eddy issue start <number> <pub-date> <day-count>` slash command. Every persona reads it via `issue__current_window`, which returns `{issue_number, pub_date, end_date, start_date, day_count}`; past windows are queryable via `issue__list_windows`. Date semantics: `pub_date` is the publishing Saturday; `end_date = pub_date - 1 day` is the content cutoff; `start_date = end_date - day_count days` is the previous issue's cutoff (so a normal `day_count=7` window covers the seven days strictly after `start_date` through `end_date`).

S3 workspace conventions — every piece of issue content is a standalone file (the "unified asset pattern"):

```
weekly-thing/{N}/
├── intro.md            ← opener prose — Jamie writes (Drafts → Shortcut)  [required]
├── cover.md            ← cover photo caption + "Month D, YYYY  \nLocation" — Jamie writes  [optional]
├── currently.md        ← the optional "Currently" section — Jamie writes  [optional]
├── haiku.md            ← compose-haiku writes (bold/hard-break rendered at draft/publish time)  [required]
├── metadata.json       ← compose-meta writes (subject + description)       [required]
├── cta-1.md / cta-2.md ← compose-cta writes (placement: frontmatter)       [optional, 0–2]
├── draft.md            ← update-draft writes — rebuilt from templates/draft_starter.md each run; shaped like a delivered issue
├── final.md            ← create-final writes (post-Eddy ordering)          [required]
├── buttondown.md          ← build-publish writes (---fenced parts: intro, cover, the non-empty ## sections, CTAs, haiku close; the ship artifact)
├── draft.html / final.html / buttondown.html ← browser-viewable HTML twins (tools.render; no-cache + CDN-invalidated). draft.html also carries a "Show review" toggle → a slide-in drawer with Eddy's editorial suggestions, hidden by default.
├── cover.jpg           ← issue cover image (iOS Shortcuts)                  [required]
├── cover-large.jpg     ← full-size cover (iOS Shortcuts)
├── journal/<hash>.jpg  ← per-entry photos — iOS Shortcuts AND update-draft's journal-image rehost
├── body-{N}.mp3 / weekly-thing-{N}.mp3 ← audio, written by `pipeline/audio/`
└── eddy-edits.md       ← (rare — when Eddy posts a substantial revision worth preserving)
```

The exact markdown shape (the `---`-fenced blocks, the Notable "discuss on Reddit" line, `### [Title](url)` headings, the `→ **[Title](url)**` Briefly form, elevated Journal posts, the `A haiku to leave you with…` close) is the same shape stored in `data/issues/{N}/archive.md` after a ship — see [`CLAUDE.md`](CLAUDE.md) ("Issue-markdown shape") for the per-loop formatting rules.

The S3 helper at `tools/s3.py` enforces a strict allow-list: only md/markdown/txt/json/yaml/yml/csv/html files; bare-component filenames (no slashes, no `..`); 256 KB cap per file. The text-only extension allowlist is what keeps agent writes from clobbering published archive assets (cover.jpg, journal photos) that share the prefix. Any path outside `weekly-thing/{N}/` is rejected before the request reaches AWS.

---

## Storage architecture

Two layers with hard boundaries.

**SQLite** at `apps/workshop_bot/data/workshop.db` (gitignored) — operational state. Anything not destined for the published newsletter lives here: agent outputs, run logs, memory notes, link candidates, subscriber events, Pinboard dedup state. (The Thingy bridge has its own SQLite at `../thingy_bridge/data/thingy_bridge.db` for its token cache + conversation mirror — workshop_bot doesn't see it.)

**S3** at `s3://files.thingelstad.com/weekly-thing/{N}/` — only files the iOS Shortcuts assemble pipeline reads on Sunday. Internal observations, research notes, draft versions never go to S3.

---

## The Thingy bridge

The reader-facing Thingy bot now lives in [`../thingy_bridge/`](../thingy_bridge/) as a separate process — see that app's README and CLAUDE.md for its architecture, deploy story, and Lambda-bridge contract. Two-process layout:

- **workshop_bot** (this app) — author-facing personas (Eddy/Linky/Marky/Patty), per-persona slash trees (`/eddy`, `/linky`, `/marky`, `/patty`), issue-assembly jobs.
- **thingy_bridge** — reader-facing answering bot in `#ask-thingy`, the hourly `thingy-watch` conversation mirror, `/thingy {recent,show,sync}` operator commands.

The two processes share the Discord server and (in normal use) the `#chatter` channel; both can post there. They do **not** share code, SQLite, or memory — workshop_bot can restart for an author-flow change without dropping `#ask-thingy`.

---

## Repo layout

```
apps/workshop_bot/
├── README.md
├── bot.py                    # entrypoint — composes ToolRegistry, starts clients + scheduler
├── eval.py                   # offline persona testing (no Discord)
├── jobs/                     # the content-loop spine (deterministic, schedulable, slash-triggerable)
│   ├── _base.py              # JobContext, JobResult, single-asset job_lock, draft-block helpers
│   ├── _llm_job.py           # shared helpers for LLM-using jobs (resolve_bot_and_channel, refresh_loop, body caps, thesis_block, _try_send)
│   ├── start_issue.py / update_draft.py / issue_status.py / status.py   # status.py backs /eddy status
│   ├── create_final.py / compose_haiku.py / compose_meta.py / compose_cta.py / build_publish.py
│   ├── ops.py                # set-goal / goal-achieved / campaign-{copy,edit,sunset} (no-LLM ledger pokes)
│   ├── pinboard_scan.py      # Linky's per-link research pass (toread + N discovery feeds)
│   ├── promotion_prep.py / daily_metrics.py / add_campaign.py / campaign_report.py   # Marky
│   ├── review_text.py / archive_lookup.py                            # /eddy ad-hoc
│   ├── linky_research.py / linky_quicklook.py                        # /linky ad-hoc
│   ├── marky_quicklook.py / patty_quicklook.py                       # /marky + /patty quick reads
│   └── follow_up.py                                                  # follow-up-sweep
├── templates/
│   └── draft_starter.md      # the six-block issue template
├── personas/
│   ├── base.py               # PersonaBot — routing, peer reactions, agent loop, slash-tree sync, startup card
│   ├── team.py               # @Team round orchestration
│   ├── commands/             # per-persona slash trees
│   │   ├── _shared.py        # ack / run-and-ack / run-interactive factories
│   │   ├── eddy.py           # /eddy issue {…} · /eddy status · /eddy review · /eddy archive · /eddy followup
│   │   ├── linky.py          # /linky scan · research · pile · stats · followup
│   │   ├── marky.py          # /marky prep · metrics · engagement · referrers · campaign {…} · followup
│   │   └── patty.py          # /patty cta · goal {…} · progress · nonprofit · supporters · followup
│   └── eddy.py / linky.py / marky.py / patty.py
│   (thingy.py — moved to ../thingy_bridge/personas/)
├── prompts/
│   ├── shared/team.md        # shared team-level prompt (cached system block)
│   └── <persona>/
│       ├── prompt.md         # the persona's identity / lane / voice
│       └── <job>.md          # job prompts: eddy/update-review.md, eddy/draft-review.md, eddy/create-final.md,
│                             #   eddy/compose-{haiku,subject,description}.md, linky/pinboard-scan.md,
│                             #   patty/compose-cta.md, marky/promotion-prep.md, marky/daily-metrics.md
├── systems/                  # external-system tool surfaces (one subpackage per system)
│   ├── _base.py              # SystemServer Protocol + ToolDef dataclass
│   ├── buttondown/{client,server}.py
│   ├── pinboard/{client,server}.py
│   ├── stripe/{client,server}.py
│   └── tinylytics/{client,server}.py
├── tools/
│   ├── llm/
│   │   ├── agent_loop.py     # tool-using turn (asyncio.to_thread wrapper)
│   │   ├── agent_tools.py    # ToolRegistry, local helper specs/functions, register_local_helpers
│   │   └── anthropic_client.py # client + prompt loader (<persona>-<file> → prompts/<persona>/<file>.md)
│   ├── content/
│   │   ├── archive.py / corpus.py / issue.py / draft.py / context.py
│   │   ├── microblog.py      # micro.blog client — Micropub q=source → native markdown
│   │   └── journal_images.py # rehost micro.blog photo uploads → weekly-thing/{N}/journal/
│   ├── discord/
│   │   ├── conversation.py / discord_io.py / interaction.py / startup.py
│   ├── db.py                 # SQLite helpers + idempotent column migrations
│   ├── render.py             # markdown → standalone HTML preview page (draft/final/publish .html twins) + the draft.html "Show review" toggle drawer
│   ├── cdn.py                # CloudFront invalidation (best-effort) for the public assets bucket
│   ├── avoid_domains.py      # popular-feed exclusion list (mirrors pipeline/content/domain_exclusions.py)
│   ├── rss.py                # latest_published_issue() from weekly.thingelstad.com/feed.xml
│   ├── support_state.py      # current nonprofit state for Patty
│   ├── s3.py                 # per-issue S3 workspace — backs workspace__*
│   ├── web.py                # web__fetch_url
├── scheduler/
│   ├── jobs.py               # cron JobSpec declarations (update-draft, pinboard-scan, rss-check, daily-metrics)
│   ├── handlers.py           # content_job bridge (cron → jobs/) + rss_check
│   └── runner.py             # APScheduler + dispatch
├── db/
│   └── schema.sql            # SQLite schema (Python ALTER migrations in db.py)
├── data/                     # gitignored
│   └── workshop.db
└── tests/
    └── test_*.py             # 650+ unit tests; discord/anthropic/httpx + S3/Pinboard/etc. stubbed
```

---

## Tech stack

- Python 3.14
- `discord.py >= 2.4` — async Discord client
- `anthropic` — Claude API
- `apscheduler >= 3.10` — cron-style jobs
- `boto3` — S3 access
- `httpx` — Lambda bridge HTTP/SSE
- `requests` — Pinboard / Buttondown / Tinylytics REST
- `beautifulsoup4` — `fetch_url` HTML cleanup, Pinboard RSS parsing
- `python-dotenv` — env loading

LLM models are configurable per-persona (`preferred_model` class attr), per-message (`--haiku` / `--sonnet` / `--opus` flag in the message body), or globally (`WORKSHOP_DEFAULT_MODEL` env var). Default cascade: per-message flag → persona preferred → env var → `haiku` fallback.

---

## Database

Tables in `db/schema.sql`. New columns added later go through idempotent `ALTER TABLE` migrations in `db._COLUMN_MIGRATIONS` so existing DBs and fresh installs converge.

| Table | Purpose | Status |
|---|---|---|
| `agent_outputs` | Per-turn agent reply records | active |
| `agent_runs` | Per-run status + duration log | active |
| `agent_notes` | Long-term memory (kind, key, content, agent author) | active |
| `issue_windows` | Operator-set in-flight issue windows (one active row) | active |
| `link_candidates` | Pinboard bookmarks Linky has seen | active |
| `pinboard_popular_seen` | URLs Linky has surfaced from the popular feed | active |
| `pinboard_research_done` | URLs Linky has researched from the to-read pile | active |
| `subscriber_events_seen` | Buttondown subscriber activity Marky has logged | active |
| `job_locks` | Single-asset serialization for the jobs pipeline (dead-pid steal) | active |
| `draft_digests` | Per-`update-draft`-run snapshot — Eddy's "since yesterday" delta | active |
| `goals` | Patty's milestone progression (one active row; `set-goal` / `goal-achieved`) | active |
| `campaigns` | Marky's `?ref=` ad-placement ledger (`add-campaign` / `campaign-sunset`) | active |
| `campaign_metrics` | Append-only per-poll campaign traffic + signups (`daily-metrics`) | active |

(`agent_inbox`, `analytics`, `supporter_events`, `channel_routes`, `thingy_tokens`, `thingy_requests`, `thingy_conversations` were dropped — `db/schema.sql` carries `DROP TABLE IF EXISTS` for each so long-lived DBs converge with fresh installs. `agent_inbox` went with the content-loop redesign's closed-loop architecture; the three Thingy tables moved with the Thingy split to `../thingy_bridge/`; the other three were reserved-but-never-wired.)

---

## Configuration

All configuration is via env vars in `.env` (see `.env.example` at the repo root).

**Per-persona Discord apps** — each is its own bot token, so the bot can show all four avatars simultaneously:
- `DISCORD_TOKEN_EDDY`, `DISCORD_TOKEN_LINKY`, `DISCORD_TOKEN_MARKY`, `DISCORD_TOKEN_PATTY`

A persona with a missing token is skipped at startup; the rest still run.

(`DISCORD_TOKEN_THINGY` + `DISCORD_CHANNEL_ASK_THINGY` are read by the separate [`../thingy_bridge/`](../thingy_bridge/) process — not by workshop_bot.)

**Server + channels:**
- `DISCORD_SERVER_ID`, `DISCORD_WORKSHOP_CATEGORY_ID`, `DISCORD_TEAM_ROLE_ID`
- `DISCORD_CHANNEL_EDITORIAL`, `_RESEARCH`, `_PROMOTION`, `_SUPPORTERS`, `_WORKSHOP`, `_CHATTER`

**Per-service API access:**
- `ANTHROPIC_API_KEY`
- `BUTTONDOWN_API_KEY`, `TINYLYTICS_API_KEY`, `TINYLYTICS_SITE_UID`, `PINBOARD_API_TOKEN`, `STRIPE_API_KEY`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `WEEKLY_THING_ASSETS_BUCKET`

**Runtime:**
- `WORKSHOP_DB_PATH` (default `apps/workshop_bot/data/workshop.db`)
- `WORKSHOP_LOG_LEVEL` (default `INFO`)
- `WORKSHOP_DEFAULT_MODEL` (default `haiku`; per-persona overrides take precedence)
- `WORKSHOP_SCHEDULER_ENABLED` (`0` to disable all scheduled jobs)
- `WORKSHOP_EDDY_REVIEW_MODEL` (optional; default: haiku Tue/Wed, sonnet Thu/Fri for Eddy's post-update review)

---

## Architectural principles

1. **One process, multiple personas.** Single asyncio loop; separate `discord.py` clients with separate tokens so each persona has its own avatar.
2. **Personas are config, not code.** Class-level attributes (`home_channel_env`, `preferred_model`, `empty_greeting`) drive behavior; every persona sees the full `Deps.registry` tool surface; the agent loop is shared in `PersonaBot.core()`.
3. **Prompts as `.md` files.** `prompts/shared/team.md` carries shared identity and rules; `prompts/<persona>/prompt.md` carries the persona's distinctive lane; `prompts/<persona>/<job>.md` carries a job's task brief. The team prompt is cached at the API; persona prompts inherit the prefix cache.
4. **Memory beyond chat.** `agent_notes` for cross-session continuity; Discord history alone is too short to remember preferences week to week.
5. **SQLite for operational state, S3 only for build artifacts.** Strict boundary; the S3 helper enforces it at the path level.
6. **Scheduled jobs are first-class.** Most jobs are pure-code data shuffling; only compose-style work hits the LLM.
7. **Cross-talk via shared visibility.** Agents see each other's messages in `#workshop`; the PASS rule keeps overhearing from becoming chatter. `#chatter` is a status firehose with no peer reactions.
8. **Reader-facing and author-facing surfaces run as separate processes.** The Thingy bridge (`../thingy_bridge/`) is its own Python process — workshop_bot restarts (Marky/Patty/Eddy code changes) don't drop `#ask-thingy`.

---

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install -r ../../requirements.txt
cp ../../.env.example ../../.env  # then fill in values
python -m apps.workshop_bot.bot
```

Tests (run from the repo root; use the local venv so dependencies match the bot):

```bash
make test-workshop
# or:
venv/bin/python -m unittest discover -s apps/workshop_bot/tests -t .
```

`make test-workshop-env` loads the repo-root `.env` before running the same
suite. Use that only for runtime-config smoke checks; the plain target keeps
unit tests away from live-service branches and credential-bearing logs.

Offline persona eval (no Discord):

```bash
python -m apps.workshop_bot.eval --persona eddy --model sonnet
```

---

## Conventions

- Citation format: `#NNN` consistent with the public Q&A surface.
- Prompts are markdown files cached in-process at first read; restart the bot to pick up edits.
- Logging: structured `logger.info("event_name %s", arg)` style. The format is plain but the messages are CloudWatch-readable if this ever moves to Lambda.
- `.env` for secrets — never commit. `.env.example` is the source of truth for required keys.
- New schema columns go in `db/schema.sql` for fresh DBs and in `db._COLUMN_MIGRATIONS` for existing DBs (idempotent ALTER).

---

## What's still missing

The README above describes what's built. Open items:

- **`create-final` per-section approval.** It does one approval round (Eddy proposes the whole reordered body, Jamie ✅/❌/🔄); the design brief's per-section loop (approve Notable order, then Briefly, then Journal) is a refinement.
- **Deeper tool-surface pass on buttondown/tinylytics/stripe.** Step 5 reshaped Pinboard; Step 8 added `buttondown__campaign_signups` / `tinylytics__campaign_traffic`, but the broader "drop verbs that don't serve a job, rename verbs that describe the API" pass is deferred.
- **`send-to-buttondown`** (wired as `/eddy issue send`; CLI sibling `pipeline/content/content.py publish --issue N`) is implemented with idempotent create/update: POST on first run, PATCH on subsequent runs (the response `id` is stored in `metadata.json` as `buttondown_id`). Untested against the live Buttondown API; first-ship smoke test should `--dry-run` then real-run.
- **Retire the iOS Shortcuts pipeline** — kept as a recovery tool until 3–4 successful ships via the new flow (Step 9 of the design brief).
- **Buttondown supporter-event webhook.** Today Marky polls. Real-time signups/churn → `#chatter` would need a small HTTP listener. The `subscriber_events_seen` table is ready for it.
- **`agent_outputs.status` lifecycle.** Field exists (`pending` / `ready` / `used` / `archived`) but nothing transitions outputs after Jamie pulls them.
- **Stripe Payment Link `ref` metadata.** `stripe__donations_by_ref` returns mostly `(no-ref)` until the donate flow sets `ref` on Checkout Session metadata.
