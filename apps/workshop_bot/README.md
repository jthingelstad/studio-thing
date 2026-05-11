# Workshop Bot — Discord Agent Runtime

> Author-only Discord bot for *The Weekly Thing*. Five personas: four agents that help Jamie assemble each week's issue, plus a public-facing bridge to Thingy (the production Librarian Lambda).

---

## What lives here

`apps/workshop_bot/` is one Python process running five `discord.py` clients in the same asyncio loop. Each persona is a separate Discord application (own bot token, own avatar) so messages appear under the right name.

| Persona | Role | Default model | Home channel |
|---|---|---|---|
| **Eddy** (he/him) | Editor — sharpens drafts, watches voice | Opus 4.7 | `#editorial` |
| **Linky** (he/him) | Link curation — Pinboard queue, popular feed, archive recall | Sonnet 4.6 | `#research` |
| **Marky** (she/her) | Promotion — subject lines, descriptions, engagement reports | Sonnet 4.6 | `#promotion` |
| **Patty** (she/her) | Supporter steward — writes the per-issue `member.json` (signed by Thingy in print) | Sonnet 4.6 | `#supporters` |
| **Thingy** (bridge) | Public archive Q&A — forwards to the Librarian Lambda | n/a (LLM lives in the Lambda) | `#ask-thingy` |

The four agent personas share **almost** the full tool surface — every tool is available to every persona, with two privacy-scoped exceptions: `stripe__*` is restricted to Patty (donor data should never enter the other personas' surfaces) and `pinboard__*` to Linky (mutating bookmark tools). Lane discipline otherwise lives in the persona prompts, not in a per-persona allowlist. Tools follow `<system>__<action>` naming (`archive__search`, `memory__remember`, `buttondown__list_subscribers`, `workspace__read`). External-system tool surfaces live under `apps/workshop_bot/systems/<name>/`; local helpers live under `apps/workshop_bot/tools/`. Both are composed into the same `ToolRegistry` at boot. A system can declare `restricted_to = {"<persona>", ...}` to scope visibility — `ToolRegistry.names_for(persona)` filters and `dispatch()` enforces (defense in depth, even if a model invents a name for a restricted tool).

Thingy is intentionally isolated — same process, but doesn't run the local agent loop and doesn't peer-react.

---

## Project context

Other components in the larger system:
- **Thingy Lambda** at `apps/librarian/lambda/` — production agent for reader Q&A. The bridge forwards to it; the bot does not replicate it.
- **Eleventy site** — `weekly.thingelstad.com` static site.
- **Buttondown** — newsletter platform; content synced to `data/buttondown/`.
- **Shortcuts pipeline** — Jamie's iOS Shortcuts assemble each issue Sunday morning, reading from `s3://files.thingelstad.com/weekly-thing/{N}/`.

---

## Routing

Each agent persona (Eddy/Linky/Marky/Patty) responds when:
- the persona is @-mentioned in any channel,
- a human posts in its home channel without @-mentioning a different persona,
- the `@Team` role is mentioned (one bot wins the lock and orchestrates a sequential round; later personas see earlier replies in their history),
- another bot posts in `#workshop` (peer reactions; default response is the literal token `PASS`).

Thingy listens only in `#ask-thingy` and answers direct in-channel questions. It never appears in the workshop or chatter.

---

## Memory

Each agent has long-term memory via `memory__remember` / `memory__recall` / `memory__forget` tools backed by an `agent_notes` SQLite table. Notes are shared across personas and attributed by author. Use cases: tonal preferences Jamie expressed, themes building across weeks, todos for future runs, observations worth carrying forward.

(The earlier `agent_inbox` typed-handoff surface was decommissioned in the content-loop redesign — the new architecture is closed-loop with no agent-to-agent messaging; Jamie is the integrator.)

Thingy users (web and Discord) also have per-user memory in the Lambda's DynamoDB table. The Lambda Bedrock-summarizes each session when the token rotates and surfaces prior-session summaries in the `/auth` response so the bridge can offer "welcome back" UX. See [`docs/librarian.md`](../../docs/librarian.md) for the Thingy-side specifics.

---

## Scheduled jobs

`scheduler/jobs.py` declares cron-triggered jobs as plain Python functions in `scheduler/handlers.py`. Today there's exactly one shape: **heartbeats** — one per persona, default `PASS` unless something material changed. The earlier "rituals" (Friday curation, Monday subscriber report, Thursday member.json) were removed pending a deliberate redesign of how the team helps Jamie assemble each issue. Until then, heartbeats plus on-demand `/workshop` slash commands carry the load.

| Job | When (Central) | Shape |
|---|---|---|
| `eddy-heartbeat` | daily 08:30 | LLM heartbeat → `#editorial` (or `PASS`) |
| `linky-heartbeat` | every 6h, 06–22 | LLM heartbeat → `#research` (or `PASS`) |
| `marky-heartbeat` | every 3h, 07–22 | LLM heartbeat → `#promotion` (or `PASS`) |
| `patty-heartbeat` | daily 09:00 | LLM heartbeat → `#supporters` (or `PASS`) |

Heartbeats are dispatched by a shared `handlers.heartbeat(persona, ctx)` wired into each `JobSpec` via `functools.partial`. Each loads `prompts/<persona>/heartbeat.md`, runs the agent loop with `WORKSHOP_HEARTBEAT_MODEL` (default `haiku`), and posts only if the answer isn't `PASS`.

CLI: `python -m apps.workshop_bot.scheduler.runner --list` to inspect. Disable the whole scheduler with `WORKSHOP_SCHEDULER_ENABLED=0`; silence heartbeats with `WORKSHOP_HEARTBEATS_ENABLED=0`. Rehearse one heartbeat offline with `python -m apps.workshop_bot.eval --heartbeat <persona>`.

---

## The in-flight issue

The published archive (corpus) holds issues already shipped — `#1` through `#N`. The issue Jamie is *currently writing* is `#N+1` and lives in the S3 workspace at `s3://files.thingelstad.com/weekly-thing/{N+1}/` — **not in the archive corpus.** This S3 prefix is shared with the published archive (every shipped issue's folder lives at `weekly-thing/{N}/` too — that's where Shortcuts puts cover images, journal photos, etc.); the in-flight issue is just the highest-numbered folder. Jamie sets the active issue window via the `/workshop job start-issue <number> <pub-date> <day-count>` slash command (host: Eddy). Every persona reads it via `issue__current_window`, which returns `{issue_number, pub_date, end_date, start_date, day_count}`; past windows are queryable via `issue__list_windows`. Date semantics: `pub_date` is the publishing Saturday; `end_date = pub_date - 1 day` is the content cutoff; `start_date = end_date - day_count days` is the previous issue's cutoff (so a normal `day_count=7` window covers the seven days strictly after `start_date` through `end_date`).

S3 workspace conventions:

```
weekly-thing/{N}/
├── draft.md            ← Jamie's draft (from Shortcuts)
├── cover.jpg           ← issue cover image (Shortcuts-managed)
├── cover-large.jpg     ← full-size cover
├── journal/            ← per-entry photos for the issue's journal section
├── body-{N}.mp3        ← audio of the body, written by `pipeline/audio/`
├── weekly-thing-{N}.mp3← full audio episode, written by `pipeline/audio/`
├── member.json         ← Patty writes Thursday 18:00 CT (CTA + progress update)
├── marky-meta.json     ← (planned — Marky doesn't auto-write yet)
└── eddy-edits.md       ← (when Eddy posts a substantial revision)
```

The S3 helper at `tools/s3.py` enforces a strict allow-list: only md/markdown/txt/json/yaml/yml/csv/html files; bare-component filenames (no slashes, no `..`); 256 KB cap per file. The text-only extension allowlist is what keeps agent writes from clobbering published archive assets (cover.jpg, journal photos) that share the prefix. Any path outside `weekly-thing/{N}/` is rejected before the request reaches AWS.

---

## Storage architecture

Two layers with hard boundaries.

**SQLite** at `apps/workshop_bot/data/workshop.db` (gitignored) — operational state. Anything not destined for the published newsletter lives here: agent outputs, run logs, memory notes, link candidates, subscriber events, Pinboard dedup state, Thingy bridge token cache.

**S3** at `s3://files.thingelstad.com/weekly-thing/{N}/` — only files the iOS Shortcuts assemble pipeline reads on Sunday. Internal observations, research notes, draft versions never go to S3.

---

## The Thingy bridge

`#ask-thingy` is a public-facing surface (author-only for now; opens to supporters later). Each message is forwarded to the production Librarian Lambda's `/chat` endpoint via `personas/thingy.py`.

Auth uses a Lambda action `/auth?action=discord_bridge` gated by a shared secret (`DISCORD_BRIDGE_SECRET` on the Lambda; `LIBRARIAN_BRIDGE_SECRET` on the bot — same value). The Lambda mints session tokens whose `sub` is `discord:<sha256(user_id)[:32]>`, so per-Discord-user rate limits work transparently against the Lambda's existing `payload.sub` rate-limit bucket.

The bridge:
- Caches tokens in SQLite (`thingy_tokens`); refreshes ~10 min before expiry.
- Streams the Lambda's SSE response (`event: meta` / `answer_delta` / `citations` / `done`) and reassembles the answer.
- Rewrites `#NNN` citations into clickable Discord links: `[#287](https://weekly.thingelstad.com/archive/287/)`.
- Adds 👍/👎 reactions; clicks fire the Lambda's `/feedback` endpoint as the original asker.
- Greets returning users on fresh-token mints with their last session's Bedrock-synthesized summary (from the Lambda's user-memory).

---

## Repo layout

```
apps/workshop_bot/
├── README.md
├── bot.py                    # entrypoint — composes ToolRegistry, starts clients + scheduler
├── eval.py                   # offline persona testing (no Discord); --heartbeat to rehearse one heartbeat
├── personas/
│   ├── base.py               # PersonaBot — routing, peer reactions, agent loop
│   ├── team.py               # @Team round orchestration
│   ├── eddy.py / linky.py / marky.py / patty.py
│   └── thingy.py             # Lambda bridge (no agent loop)
├── prompts/
│   ├── shared/team.md        # shared team-level prompt (cached system block)
│   └── <persona>/
│       ├── prompt.md         # the persona's identity / lane / voice
│       └── heartbeat.md      # the scheduled wake-up prompt (default PASS)
├── systems/                  # external-system tool surfaces (one subpackage per system)
│   ├── _base.py              # SystemServer Protocol + ToolDef dataclass
│   ├── buttondown/{client,server}.py
│   ├── pinboard/{client,server}.py
│   ├── stripe/{client,server}.py
│   └── tinylytics/{client,server}.py
├── tools/
│   ├── agent_loop.py         # tool-using turn (asyncio.to_thread wrapper)
│   ├── agent_tools.py        # ToolRegistry, FUNCS/SPECS, register_local_helpers
│   ├── anthropic_client.py   # client + prompt loader (resolves <persona>-heartbeat)
│   ├── archive.py            # read archive issues from disk
│   ├── corpus.py             # BM25 corpus from librarian-core
│   ├── conversation.py       # Discord history → Anthropic messages
│   ├── discord_io.py         # chunked send, attachment read
│   ├── db.py                 # SQLite helpers + idempotent column migrations
│   ├── issue.py              # issue-window compute + tool handlers
│   ├── support_state.py      # current nonprofit state for Patty
│   ├── s3.py                 # per-issue S3 workspace — backs workspace__*
│   ├── web.py                # web__fetch_url
│   ├── startup.py            # boot self-check + announce
│   ├── thingy_client.py      # Lambda bridge HTTP/SSE client
│   └── thingy_render.py      # citation injection + history compaction
├── scheduler/
│   ├── jobs.py               # JobSpec declarations (4 heartbeats)
│   ├── handlers.py           # heartbeat dispatcher
│   └── runner.py             # APScheduler + dispatch
├── db/
│   └── schema.sql            # SQLite schema (Python ALTER migrations in db.py)
├── data/                     # gitignored
│   └── workshop.db
└── tests/
    └── test_*.py             # ~200 unit tests; discord/anthropic/httpx stubbed
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
| `thingy_tokens` | Cached Lambda tokens + profile per Discord user | active |
| `thingy_requests` | Bridge request log (for `/feedback` lookup) | active |
| `analytics` | Reserved for Marky's metric history | unused |
| `supporter_events` | Reserved (older shape; superseded by `subscriber_events_seen`) | unused |
| `channel_routes` | Reserved (channels are env-var-resolved today) | unused |

(`agent_inbox` was dropped in the content-loop redesign — `db/schema.sql` carries a `DROP TABLE IF EXISTS` so long-lived DBs converge with fresh installs.)

---

## Configuration

All configuration is via env vars in `.env` (see `.env.example` at the repo root).

**Per-persona Discord apps** — each is its own bot token, so the bot can show all five avatars simultaneously:
- `DISCORD_TOKEN_EDDY`, `DISCORD_TOKEN_LINKY`, `DISCORD_TOKEN_MARKY`, `DISCORD_TOKEN_PATTY`, `DISCORD_TOKEN_THINGY`

A persona with a missing token is skipped at startup; the rest still run.

**Server + channels:**
- `DISCORD_SERVER_ID`, `DISCORD_WORKSHOP_CATEGORY_ID`, `DISCORD_TEAM_ROLE_ID`
- `DISCORD_CHANNEL_EDITORIAL`, `_RESEARCH`, `_PROMOTION`, `_SUPPORTERS`, `_WORKSHOP`, `_CHATTER`, `_ASK_THINGY`

**Per-service API access:**
- `ANTHROPIC_API_KEY`
- `BUTTONDOWN_API_KEY`, `TINYLYTICS_API_KEY`, `TINYLYTICS_SITE_UID`, `PINBOARD_API_TOKEN`, `STRIPE_API_KEY`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `WEEKLY_THING_ASSETS_BUCKET`

**Thingy bridge:**
- `LIBRARIAN_API_URL`, `LIBRARIAN_STREAM_URL` — defaults match `apps/site/_data/site.js`
- `LIBRARIAN_BRIDGE_SECRET` — must match the Lambda's `DISCORD_BRIDGE_SECRET`
- `WEEKLY_THING_SITE_URL` (default `https://weekly.thingelstad.com`)

**Runtime:**
- `WORKSHOP_DB_PATH` (default `apps/workshop_bot/data/workshop.db`)
- `WORKSHOP_LOG_LEVEL` (default `INFO`)
- `WORKSHOP_DEFAULT_MODEL` (default `haiku`; per-persona overrides take precedence)
- `WORKSHOP_SCHEDULER_ENABLED` (`0` to disable all scheduled jobs)
- `WORKSHOP_HEARTBEATS_ENABLED` (default `1`; set to `0` to silence heartbeats)
- `WORKSHOP_HEARTBEAT_MODEL` (default `haiku`)

---

## Architectural principles

1. **One process, multiple personas.** Single asyncio loop; separate `discord.py` clients with separate tokens so each persona has its own avatar.
2. **Personas are config, not code.** Class-level attributes (`home_channel_env`, `preferred_model`, `empty_greeting`) drive behavior; every persona sees the full `Deps.registry` tool surface; the agent loop is shared in `PersonaBot.core()`.
3. **Prompts as `.md` files.** `prompts/shared/team.md` carries shared identity and rules; `prompts/<persona>/prompt.md` carries the persona's distinctive lane; `prompts/<persona>/heartbeat.md` is the scheduled wake-up prompt. The team prompt is cached at the API; persona prompts inherit the prefix cache.
4. **Memory beyond chat.** `agent_notes` for cross-session continuity; Discord history alone is too short to remember preferences week to week.
5. **SQLite for operational state, S3 only for build artifacts.** Strict boundary; the S3 helper enforces it at the path level.
6. **Scheduled jobs are first-class.** Most jobs are pure-code data shuffling; only compose-style work hits the LLM.
7. **Cross-talk via shared visibility.** Agents see each other's messages in `#workshop`; the PASS rule keeps overhearing from becoming chatter. `#chatter` is a status firehose with no peer reactions.
8. **Thingy is a bridge, not a teammate.** Same process; isolated surface. The four agent personas don't see Thingy's conversations and don't peer-react in `#ask-thingy`.

---

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install -r ../../requirements.txt
cp ../../.env.example ../../.env  # then fill in values
python -m apps.workshop_bot.bot
```

Tests (no SDK dependencies needed; discord/anthropic/httpx are stubbed):

```bash
python -m unittest discover -s apps/workshop_bot/tests -t .
```

Offline persona eval (no Discord):

```bash
python -m apps.workshop_bot.eval --persona eddy --model sonnet
```

---

## Conventions

- Citation format: `#NNN` consistent with Thingy.
- Prompts are markdown files cached in-process at first read; restart the bot to pick up edits.
- Logging: structured `logger.info("event_name %s", arg)` style. The format is plain but the messages are CloudWatch-readable if this ever moves to Lambda.
- `.env` for secrets — never commit. `.env.example` is the source of truth for required keys.
- New schema columns go in `db/schema.sql` for fresh DBs and in `db._COLUMN_MIGRATIONS` for existing DBs (idempotent ALTER).

---

## What's still missing

The README above describes what's built. A few items are still on the cutting room floor:

- **Buttondown supporter-event webhook.** Today Marky polls. Real-time signups/churn → `#chatter` would need a small HTTP listener (Flask or aiohttp). The `subscriber_events_seen` table is ready for it.
- **Auto-shipped `marky-meta.json`.** Patty's Thursday `member.json` job has the shape; Marky needs a parallel scheduled job that composes `{ "subject": "Three Words Title", "description": "..." }` and writes it to S3.
- **Eddy auto-critique on new draft.** Today Eddy reads drafts on demand. Could poll S3 for a fresh `draft.md` per the in-flight issue and post a critique automatically.
- **`agent_outputs.status` lifecycle.** Field exists with `pending` / `ready` / `used` / `archived` values, but nothing transitions outputs after Jamie pulls them.
- **Stripe Payment Link `ref` metadata.** `stripe__donations_by_ref` returns mostly `(no-ref)` until the donate flow is configured to set `ref` on Checkout Session metadata. Documented in the tool description.
- **Decommission dead tables.** `analytics`, `supporter_events`, `channel_routes` are reserved but unused.
