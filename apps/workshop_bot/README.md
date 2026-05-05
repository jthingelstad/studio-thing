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

The four agent personas share a tool surface (archive, memory, S3 workspace, persona-specific extras) and the agent loop in `personas/base.py:PersonaBot`. Thingy is intentionally isolated — same process, but doesn't run the local agent loop and doesn't peer-react.

---

## Project context

Other components in the larger system:
- **Thingy Lambda** at `apps/librarian/lambda/` — production agent for reader Q&A. The bridge forwards to it; the bot does not replicate it.
- **Eleventy site** — `weekly.thingelstad.com` static site.
- **Buttondown** — newsletter platform; content synced to `data/buttondown/`.
- **Shortcuts pipeline** — Jamie's iOS Shortcuts assemble each issue Sunday morning, reading from `s3://files.thingelstad.com/weekly-thing/issues/{N}/`.

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

Each agent has long-term memory via `remember`/`recall`/`forget_note` tools backed by an `agent_notes` SQLite table. Notes are shared across personas and attributed by author. Use cases: tonal preferences Jamie expressed, themes building across weeks, todos for future runs, observations worth carrying forward.

Thingy users (web and Discord) also have per-user memory in the Lambda's DynamoDB table. The Lambda Bedrock-summarizes each session when the token rotates and surfaces prior-session summaries in the `/auth` response so the bridge can offer "welcome back" UX. See [`docs/librarian.md`](../../docs/librarian.md) for the Thingy-side specifics.

---

## Scheduled jobs

`scheduler/jobs.py` declares cron-triggered jobs as plain Python functions in `scheduler/handlers.py`. Most handlers are pure code (fetch + format + post); a few call into the agent loop where LLM judgment is genuinely needed. The split is deliberate — the LLM is a tool the handler reaches for, not the default execution path.

| Job | When (Central) | Mode | Channel |
|---|---|---|---|
| `linky-wednesday-check` | Wed 10:30 | code | `#research` |
| `linky-friday-curation` | Fri 16:00 | LLM | `#research` |
| `linky-popular-scan` | every 6h | code + LLM filter | `#research` |
| `linky-research-unread` | 10:00 + 16:00 daily | LLM | `#research` |
| `marky-daily-engagement` | daily 09:00 | code | `#chatter` |
| `marky-weekly-subscribers` | Mon 11:00 | code | `#promotion` |
| `patty-thursday-member-json` | Thu 18:00 | LLM | `#supporters` + S3 |
| `eddy-saturday-prep` | Sat 08:00 | code | `#editorial` |

CLI: `python -m apps.workshop_bot.scheduler.runner --list` to inspect, `--once <job_id>` to fire manually. Disable the whole scheduler with `WORKSHOP_SCHEDULER_ENABLED=0`.

---

## The in-flight issue

The published archive (corpus) holds issues already shipped — `#1` through `#N`. The issue Jamie is *currently writing* is `#N+1` and lives in the S3 workspace at `s3://files.thingelstad.com/weekly-thing/issues/{N+1}/` — **not in the archive corpus.** Every persona has the universal `current_issue_number` tool that resolves "the issue I'm working on" by combining S3 workspace folders with the corpus's latest published issue.

S3 workspace conventions:

```
weekly-thing/issues/{N}/
├── draft.md            ← Jamie's draft (from Shortcuts)
├── photo.jpg
├── photo-caption.txt
├── metadata.json       ← Shortcuts-managed
├── member.json         ← Patty writes Thursday 18:00 CT (CTA + progress update)
├── marky-meta.json     ← (planned — Marky doesn't auto-write yet)
└── eddy-edits.md       ← (when Eddy posts a substantial revision)
```

The S3 helper at `tools/s3.py` enforces a strict allow-list: only md/markdown/txt/json/yaml/yml/csv/html files; bare-component filenames (no slashes, no `..`); 256 KB cap per file. Any path outside `weekly-thing/issues/{N}/` is rejected before the request reaches AWS.

---

## Storage architecture

Two layers with hard boundaries.

**SQLite** at `apps/workshop_bot/data/workshop.db` (gitignored) — operational state. Anything not destined for the published newsletter lives here: agent outputs, run logs, memory notes, link candidates, subscriber events, Pinboard dedup state, Thingy bridge token cache.

**S3** at `s3://files.thingelstad.com/weekly-thing/issues/{N}/` — only files the iOS Shortcuts assemble pipeline reads on Sunday. Internal observations, research notes, draft versions never go to S3.

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
├── bot.py                    # entrypoint
├── eval.py                   # offline persona testing (no Discord)
├── personas/
│   ├── base.py               # PersonaBot — routing, peer reactions, agent loop
│   ├── team.py               # @Team round orchestration
│   ├── eddy.py / linky.py / marky.py / patty.py
│   └── thingy.py             # Lambda bridge (no agent loop)
├── prompts/
│   ├── team.md               # shared team-level prompt (cached system block)
│   └── eddy.md / linky.md / marky.md / patty.md
├── tools/
│   ├── agent_loop.py         # tool-using turn (asyncio.to_thread wrapper)
│   ├── agent_tools.py        # tool registry + ContextVar persona attribution
│   ├── anthropic_client.py   # client + prompt loader
│   ├── archive.py            # read archive issues from disk
│   ├── corpus.py             # BM25 corpus from librarian-core
│   ├── conversation.py       # Discord history → Anthropic messages
│   ├── discord_io.py         # chunked send, attachment read
│   ├── db.py                 # SQLite helpers + idempotent column migrations
│   ├── pinboard.py           # Pinboard REST + popular RSS feed
│   ├── support_state.py      # current nonprofit state for Patty
│   ├── buttondown.py         # subscriber API
│   ├── tinylytics.py         # engagement API
│   ├── web.py                # fetch_url
│   ├── s3.py                 # per-issue S3 workspace
│   ├── startup.py            # boot self-check + announce
│   ├── thingy_client.py      # Lambda bridge HTTP/SSE client
│   └── thingy_render.py      # citation injection + history compaction
├── scheduler/
│   ├── jobs.py               # JobSpec declarations
│   ├── handlers.py           # per-job functions
│   └── runner.py             # APScheduler + dispatch
├── db/
│   └── schema.sql            # SQLite schema (Python ALTER migrations in db.py)
├── data/                     # gitignored
│   └── workshop.db
└── tests/
    └── test_*.py             # 81 unit tests; discord/anthropic/httpx stubbed
```

---

## Tech stack

- Python 3.13
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
| `link_candidates` | Pinboard bookmarks Linky has seen | active |
| `pinboard_popular_seen` | URLs Linky has surfaced from the popular feed | active |
| `pinboard_research_done` | URLs Linky has researched from the to-read pile | active |
| `subscriber_events_seen` | Buttondown subscriber activity Marky has logged | active |
| `thingy_tokens` | Cached Lambda tokens + profile per Discord user | active |
| `thingy_requests` | Bridge request log (for `/feedback` lookup) | active |
| `analytics` | Reserved for Marky's metric history | unused |
| `supporter_events` | Reserved (older shape; superseded by `subscriber_events_seen`) | unused |
| `channel_routes` | Reserved (channels are env-var-resolved today) | unused |

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
- `BUTTONDOWN_API_KEY`, `TINYLYTICS_API_KEY`, `TINYLYTICS_SITE_UID`, `PINBOARD_API_TOKEN`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `WEEKLY_THING_ASSETS_BUCKET`

**Thingy bridge:**
- `LIBRARIAN_API_URL`, `LIBRARIAN_STREAM_URL` — defaults match `apps/site/_data/site.js`
- `LIBRARIAN_BRIDGE_SECRET` — must match the Lambda's `DISCORD_BRIDGE_SECRET`
- `WEEKLY_THING_SITE_URL` (default `https://weekly.thingelstad.com`)

**Runtime:**
- `WORKSHOP_DB_PATH` (default `apps/workshop_bot/data/workshop.db`)
- `WORKSHOP_LOG_LEVEL` (default `INFO`)
- `WORKSHOP_DEFAULT_MODEL` (default `haiku`; per-persona overrides take precedence)
- `WORKSHOP_SCHEDULER_ENABLED` (`0` to disable scheduled jobs)

---

## Architectural principles

1. **One process, multiple personas.** Single asyncio loop; separate `discord.py` clients with separate tokens so each persona has its own avatar.
2. **Personas are config, not code.** Class-level attributes (`tools`, `home_channel_env`, `preferred_model`, `empty_greeting`) drive behavior; the agent loop is shared in `PersonaBot.handle()`.
3. **Prompts as `.md` files.** `prompts/team.md` carries shared identity and rules; per-persona prompts carry only what's distinctive. The team prompt is cached at the API; per-persona prompts inherit the prefix cache.
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

- **Buttondown supporter-event webhook.** Today Marky polls weekly. Real-time signups/churn → `#chatter` would need a small HTTP listener (Flask or aiohttp). The `subscriber_events_seen` table is ready for it.
- **Auto-shipped `marky-meta.json`.** Patty's Thursday `member.json` job has the shape; Marky needs a parallel scheduled job that composes `{ "subject": "Three Words Title", "description": "..." }` and writes it to S3.
- **Eddy auto-critique on new draft.** Today Eddy reads drafts on demand. Could poll S3 for a fresh `draft.md` per the in-flight issue and post a critique automatically.
- **`agent_outputs.status` lifecycle.** Field exists with `pending` / `ready` / `used` / `archived` values, but nothing transitions outputs after Jamie pulls them.
- **Decommission dead tables.** `analytics`, `supporter_events`, `channel_routes` are reserved but unused.
