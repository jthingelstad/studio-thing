# Workshop Bot — Discord Agent Runtime

> Author-only Discord bot hosting four AI agents that assist with creating *The Weekly Thing* newsletter. Part of the `weekly.thingelstad.com` monorepo.

---

## Project Context

This bot is one component of a larger system. The Weekly Thing already has:

- **Thingy** — production Lambda agent answering reader questions about the archive (lives at `apps/librarian/lambda/`, deployed to AWS). NOT built here.
- **archive_chat** — local CLI for unrestricted author research against the archive (`apps/archive-chat/archive_chat.py`). NOT replaced.
- **Eleventy site** — `weekly.thingelstad.com` static site.
- **Buttondown** — newsletter platform; content is synced to `data/buttondown/`.
- **Shortcuts pipeline** — Jamie's iOS Shortcuts build the actual newsletter, using DataJar for inter-shortcut state.

This repo will add **four new agents** that run as a Discord bot, plus the supporting database and S3 integration. Thingy exists; we're not modifying it.

---

## The Four Agents

| Agent  | Role                | Trigger                         | Primary Output                      |
|--------|---------------------|---------------------------------|-------------------------------------|
| Eddy   | Editor              | On-demand (Discord mention)     | Draft critique, voice feedback      |
| Linky | Link Curator        | Weekly + on-demand              | Curated unpublished Pinboard preview|
| Marky  | Promotion           | Daily + on-demand               | Stats, subject lines, descriptions  |
| Patty  | Supporter Steward   | Weekly Friday + Buttondown evts | Supporter signals, CTA snippet      |

Each agent is a distinct system prompt + a set of tools. They share corpus access, share the SQLite DB, and can read each other's outputs.

### Agent jobs in detail

**Eddy** — reads drafts, gives editorial critique with archive-aware voice analysis. Reads draft from S3 (drafts are too long for Discord 2000-char limit). Posts summary in `#editorial`, writes detailed feedback to SQLite for follow-up queries.

**Linky** — forward-looking, NOT archive research. Reads unpublished Pinboard bookmarks, finds themes, suggests groupings, helps Jamie curate what should go in the next issue. Outputs a structured preview with link summaries, theme clusters, and confidence notes.

**Marky** — has two modes:
- *Scheduled (daily)*: fetch Tinylytics, post engagement summary in `#chatter`, write to SQLite.
- *On-demand*: given a draft + photo on S3, generate subject line (3-word convention used by The Weekly Thing) and issue description. Write back to S3 for Shortcuts pipeline to pick up.

**Patty** — supporter program steward (NOT subscription tier; this is a nonprofit-spirited support program). Two jobs:
- *Scheduled weekly*: draft the supporter CTA snippet for the next issue. Output goes to S3 (public, since it's going into the newsletter anyway). Attributed to Thingy in the published issue, not Patty — Patty is invisible to readers.
- *Event-driven*: when Buttondown reports new/churned supporters, post in `#chatter` (tagged as signup/churn signal).

---

## Discord Server Structure

Author-only for now (single user: Jamie). May open `#ask-thingy` to supporters in the future, but that's out of scope for v1.

```
WORKSHOP (category)
├─ #editorial      → Eddy work (drafts, critique, voice)
├─ #research       → Linky work (Pinboard curation)
├─ #promotion      → Marky work (subject lines, descriptions, angles)
├─ #supporters     → Patty work (CTA drafts, supporter analysis)
├─ #workshop       → multi-agent collaboration; bring drafts/ideas, any agent responds
└─ #chatter     → operational heartbeat:
                       - signups (new supporters from Patty)
                       - churn (unsubscribes from Patty)
                       - engagement (daily Tinylytics from Marky)
                       - deployments (build/publish notifications)
```

`#chatter` is read-mostly — agents post status updates here automatically. The signal types are differentiated by message format and bot identity, not by separate channels. Keeps signal density high in one place rather than spreading thin across four channels.

`#workshop` is the multi-agent collaboration room. When you want multiple agents weighing in on the same thing — bring a draft, ask Eddy first, then ask Marky to react, then ask Patty for the supporter angle — that happens here. Each agent in `#workshop` sees the full thread history including other agents' responses.

The four single-agent channels (`#editorial`, `#research`, `#promotion`, `#supporters`) are for focused work with one agent. Less context-switching.

---

## Storage Architecture

Two distinct storage layers with different access boundaries:

### SQLite (private, local) — operational state
Path: `apps/workshop_bot/data/workshop.db` (gitignored).

Used for:
- Agent outputs (drafts, analyses, research notes)
- Marky's analytics history
- Linky's link analysis
- Patty's supporter tracking
- Agent execution log
- Conversation context for multi-turn threads

### S3 (public, `files.thingelstad.com`) — build pipeline artifacts
Bucket already exists for the static site. Add a prefix:
```
s3://files.thingelstad.com/weekly-thing/issues/{issue_number}/
├── draft.md            # Jamie's draft, dual-written from Shortcuts
├── photo.jpg           # already there
├── photo-caption.txt   # already there
├── metadata.json       # subject, description, etc.
├── patty-cta.json      # Patty's CTA snippet (written by agent)
└── marky-meta.json     # Marky's subject + description (written by agent)
```

S3 is what Shortcuts can read (public HTTP). SQLite is what agents read among themselves.

**Important rule:** agents write to S3 ONLY for things meant to be published or read by the Shortcuts build automation. Internal analysis, research notes, supporter tracking — all SQLite, never S3.

---

## Repo Location

This bot lives at `apps/workshop_bot/` in the existing monorepo. Shared retrieval/corpus primitives already live in `librarian-core/` (installed editable) — import from there. The Thingy Lambda at `apps/librarian/lambda/` is Node and not directly importable from Python; copy patterns rather than code.

```
apps/workshop_bot/
├── README.md
├── pyproject.toml or requirements.txt
├── bot.py                    # entrypoint
├── personas/
│   ├── __init__.py
│   ├── eddy.py
│   ├── linky.py
│   ├── marky.py
│   └── patty.py
├── prompts/                  # editable system prompts
│   ├── eddy.md
│   ├── linky.md
│   ├── marky.md
│   └── patty.md
├── tools/                    # shared agent tools
│   ├── corpus.py             # archive retrieval (reuse from librarian-core)
│   ├── pinboard.py           # Pinboard MCP / API client
│   ├── tinylytics.py         # Tinylytics API client
│   ├── buttondown.py         # Buttondown API client
│   └── s3.py                 # S3 read/write helpers
├── db/
│   ├── schema.sql
│   └── migrations/
├── scheduler/
│   └── jobs.py               # APScheduler or similar
├── data/                     # gitignored
│   └── workshop.db
└── tests/
```

---

## Tech Stack

- **Language**: Python 3.11
- **Discord**: `discord.py` (preferred, async, mature) or `nextcord`
- **LLM**: Anthropic API directly (`anthropic` package). Claude Sonnet 4.6 for most agents; Opus 4.7 for Eddy (where quality matters most).
- **Database**: SQLite via `sqlite3` stdlib or `sqlmodel` for ORM if useful
- **Scheduling**: `APScheduler` for cron-style jobs in-process
- **AWS**: `boto3` for S3 access (use existing `weekly-thing` credentials)
- **Pinboard**: existing Pinboard MCP server Jamie built, OR direct API
- **Tinylytics**: REST API
- **Buttondown**: REST API (`api.buttondown.com/v1/`)
- **Env management**: `python-dotenv`, secrets in `.env`

Match the existing codebase conventions in `librarian-core/`, `apps/archive-chat/`, and `apps/librarian/lambda/`.

---

## Architectural Principles

1. **One bot, multiple personas.** Single Python process, single Discord connection, four agent personalities dispatched by channel + mention.
2. **Personas are config, not code.** Each agent's system prompt lives in `prompts/{name}.md` so they're editable without code changes.
3. **Shared corpus.** All agents that need archive access import the same retrieval module. Don't duplicate the BM25 logic.
4. **Discord history is session state.** When an agent responds in a thread, it reads the last N messages of that thread for context. No separate session table for chat continuity.
5. **SQLite for persistence beyond chat.** Analytics, research notes, supporter tracking, scheduled job outputs — all in SQLite.
6. **S3 only for build pipeline artifacts.** If it doesn't go into the newsletter or get read by Shortcuts, it doesn't go to S3.
7. **Scheduled jobs are first-class.** Most agents run on a cadence, not just on-demand. The bot is a scheduled worker as much as it is a chat interface.
8. **Cross-talk is just shared thread visibility.** When agents are in the same thread, each can see what the others wrote. No orchestrator. Jamie moderates by asking follow-ups.

---

## Database Schema (Starting Point)

```sql
-- Agent outputs and work-in-progress
CREATE TABLE agent_outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_name TEXT NOT NULL,         -- 'eddy', 'linky', 'marky', 'patty'
  output_type TEXT NOT NULL,        -- 'critique', 'link_preview', 'analytics',
                                    -- 'cta_draft', 'subject_line', etc.
  content TEXT NOT NULL,            -- JSON string of the output
  metadata TEXT,                    -- JSON for agent-specific context
  status TEXT DEFAULT 'ready',      -- 'pending', 'ready', 'used', 'archived'
  created_at TEXT DEFAULT (datetime('now')),
  related_issue INTEGER             -- issue number if applicable
);

-- Tinylytics & engagement metrics from Marky
CREATE TABLE analytics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_date TEXT NOT NULL,
  metric_type TEXT NOT NULL,        -- 'page_views', 'unique_visitors', etc.
  value INTEGER,
  details TEXT,                     -- JSON of full Tinylytics response
  created_at TEXT DEFAULT (datetime('now'))
);

-- Pinboard link analysis from Linky
CREATE TABLE link_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  title TEXT,
  description TEXT,
  pinboard_tags TEXT,               -- comma-separated
  linky_summary TEXT,
  linky_themes TEXT,               -- JSON array
  archive_resonance TEXT,           -- what archive issues this connects to
  status TEXT DEFAULT 'unpublished',-- 'unpublished', 'selected', 'published'
  pinboard_added TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  used_in_issue INTEGER
);

-- Supporter signals from Patty
CREATE TABLE supporter_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email_hash TEXT NOT NULL,         -- never store raw emails
  event_type TEXT NOT NULL,         -- 'joined', 'churned', 'milestone'
  event_date TEXT NOT NULL,
  details TEXT,                     -- JSON
  created_at TEXT DEFAULT (datetime('now'))
);

-- Agent execution log
CREATE TABLE agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_name TEXT NOT NULL,
  trigger TEXT NOT NULL,            -- 'scheduled', 'mention', 'webhook'
  status TEXT NOT NULL,             -- 'success', 'error', 'partial'
  duration_ms INTEGER,
  error TEXT,
  records_written INTEGER,
  started_at TEXT DEFAULT (datetime('now')),
  ended_at TEXT
);

-- Discord channel routing config (lookup table; small)
CREATE TABLE channel_routes (
  channel_name TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  primary_agent TEXT,
  category TEXT                     -- 'workshop' or 'heartbeat'
);
```

---

## Implementation Approach (Recommended Order)

### Phase 1 — Foundation (build first)
1. Repo skeleton at `apps/workshop_bot/` with the structure above.
2. SQLite schema + migration runner.
3. Discord bot connection, channel-to-agent routing.
4. Shared `tools/anthropic_client.py` wrapper with prompt caching.
5. Single agent end-to-end: pick **Eddy** because Jamie can test it on a real draft.

### Phase 2 — Eddy works
6. Eddy reads draft from S3 path, fetches archive context via shared retrieval.
7. Eddy posts summary in `#editorial` thread, full critique in SQLite.
8. Verify with a real draft.

### Phase 3 — Add the other on-demand agents
9. Marky on-demand: subject + description generation given S3 draft path.
10. Linky on-demand: pull unpublished Pinboard items, return curated preview.
11. Patty on-demand: draft CTA snippet (writes to S3 + SQLite).

### Phase 4 — Scheduling
12. APScheduler setup.
13. Marky daily Tinylytics fetch → `#chatter` (tagged as engagement signal).
14. Linky weekly Pinboard scan → `#research`.
15. Patty weekly CTA draft → S3.

### Phase 5 — Webhooks (later)
16. Buttondown webhook receiver for `subscriber.created` / `subscriber.deleted` → Patty posts in `#chatter` (tagged as signup/churn signal).

### Phase 6 — Cross-talk
17. Agents in `#chatter` see and respond to each other's posts. This is mostly system-prompt work, not new code.

---

## What NOT to Build (Yet)

- Reader-facing Discord (no supporters in the server yet).
- Thingy in Discord (Thingy stays on the website for v1).
- Voice match enforcement / style checkers (Eddy can flag, but no automated rejection).
- Web UI / dashboard (Discord IS the dashboard).
- Authentication for multiple users (single-user system).
- Agent autonomy on publishing (agents propose, Jamie approves manually except for Patty's CTA which is auto-included via S3).

---

## Conventions to Match

This repo already has conventions worth respecting:

- Python style follows what's in `librarian-core/` and `apps/archive-chat/`.
- Prompts as separate `.md` files (see `apps/librarian/lambda/prompts/`).
- `.env` for secrets, never commit. Use `.env.example`.
- Logging: structured, JSON-friendly. CloudWatch-compatible if it ever moves to Lambda.
- Citation convention: when agents reference archive issues, use `#NNN` format consistent with Thingy and archive_chat.

---

## Secrets Needed

Add to `.env.example`:

```
# Discord
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_WORKSHOP_CATEGORY_ID=

# Anthropic (already in repo)
ANTHROPIC_API_KEY=

# AWS S3 (already in repo)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
WEEKLY_THING_ASSETS_BUCKET=files.thingelstad.com

# Pinboard
PINBOARD_API_TOKEN=

# Tinylytics
TINYLYTICS_API_KEY=
TINYLYTICS_SITE_UID=

# Buttondown (already in repo)
BUTTONDOWN_API_KEY=

# Workshop Bot
WORKSHOP_DB_PATH=apps/workshop_bot/data/workshop.db
WORKSHOP_LOG_LEVEL=INFO
```

---

## First Task for Claude Code

Start by:

1. Reading the existing repo structure: `apps/archive-chat/archive_chat.py`, `apps/librarian/lambda/`, `librarian-core/`, `data/buttondown/`, top-level `Makefile`, `requirements.txt`.
2. Asking Jamie any clarifying questions before scaffolding.
3. Proposing the v1 directory structure for `apps/workshop_bot/` and a minimal working example: bot connects to Discord, responds to `@eddy hello` with a placeholder reply.
4. Once that works, building Eddy end-to-end against a real S3 draft path.

Don't try to build all four agents at once. One agent fully working is more valuable than four agents half-built.

---

## Open Questions for Jamie

(Things to confirm before deep implementation)

- Discord library: `discord.py` or `nextcord`? (Recommend `discord.py`.)
- Hosting: where does the bot run? Mac mini (alongside Otto Thing)? Lambda with a long-lived container? Fly.io? Recommend Mac mini for v1 — same pattern as Elixir bot.
- Pinboard access: use the MCP server you already built, or direct API in this bot?
- Discord IDs: provide channel IDs or have the bot discover them by name on first run?
- S3 prefix for build artifacts: confirm `weekly-thing/issues/{n}/` is the right path under `files.thingelstad.com`.
- Subject line convention: Marky needs the rule. Is it always exactly 3 words, or "around 3 words"?
