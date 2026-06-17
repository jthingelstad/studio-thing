# Workshop Bot — Discord agent runtime

Author-only Discord bot for *The Weekly Thing*. Five agent personas help Jamie assemble each week's issue: **Scout** (producer), **Eddy** (editor), **Linky** (link curator), **Marky** (promotion + analytics), **Patty** (supporter steward).

> Operational memory for working in this codebase lives in [`CLAUDE.md`](CLAUDE.md). This README is the human-facing overview — what the bot is, how to run it, what env vars it needs. Don't expect the jobs table or per-job semantics here; those live in CLAUDE.md.

## What it is

One Python process running five `discord.py` clients in the same asyncio loop, plus an APScheduler instance. Each persona is its own Discord application (own bot token, own avatar) so messages appear under the right name. Slash commands are per-persona (`/scout …`, `/eddy …`, `/linky …`, `/marky …`, `/patty …`), gated by Discord's `manage_guild` permission.

| Persona | Role | Default model | Home channel |
|---|---|---|---|
| **Scout** | Producer — production slate, issue lifecycle, Build/Publish cards | Sonnet 4.6 | `#production` |
| **Eddy** | Editor — draft review, editorial reorder, subject/haiku generation | Sonnet 4.6 (Opus for review jobs) | `#editorial` |
| **Linky** | Curator — Pinboard scan every 3h 07:00–22:00 CT, ad-hoc URL research | Sonnet 4.6 | `#research` / `#discovery` |
| **Marky** | Promotion — syndication drafts post-ship, daily metrics, campaign ledger | Sonnet 4.6 | `#promotion` |
| **Patty** | Supporter steward — per-issue membership CTA in **Thingy's** voice (Patty is invisible to readers) | Sonnet 4.6 | `#supporters` |

The reader-facing Thingy bot (the `#ask-thingy` Q&A surface) lives in [`../thingy_bridge/`](../thingy_bridge/) as a separate process. The split lets workshop_bot restart for an author-flow change without dropping `#ask-thingy`.

## Project context

| Component | Where | Relationship |
|---|---|---|
| **thingy_bridge** | [`../thingy_bridge/`](../thingy_bridge/) | Separate process. Reader-facing. Shares the Discord server, nothing else. |
| **Librarian Lambda** | [`../librarian/`](../librarian/) | Production agent for reader Q&A. workshop_bot uses its `/retrieve` endpoint for semantic archive lookups (Bedrock embed + Cohere rerank), via `tools/thingy_retrieve.py`. |
| **Eleventy site** | [`../site/`](../site/) | `weekly.thingelstad.com`. workshop_bot's BM25 corpus loads from `apps/site/archive/`. |
| **Buttondown** | external | Email delivery. `send-to-buttondown` pushes `buttondown.md` as a draft (idempotent POST/PATCH); Jamie schedules + sends from the Buttondown UI. |
| **iOS Shortcuts** | external | Legacy: assembles each issue Sunday morning, reading from `s3://files.thingelstad.com/weekly-thing/{N}/`. Recovery tool until 3-4 ships succeed via the new flow. |

## Quick start

```bash
# from the repo root
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in values

python -m apps.workshop_bot.bot
```

Offline persona evaluation (no Discord):

```bash
python -m apps.workshop_bot.eval --persona eddy --model sonnet
```

For production use, run under launchd via `scripts/admin.sh` — see [`scripts/README.md`](scripts/README.md). Run under `caffeinate` so the Mac doesn't sleep and drop the Discord gateways.

## Tests

```bash
# from the repo root, using the local venv
make test-workshop
# or:
venv/bin/python -m unittest discover -s apps/workshop_bot/tests -t .
```

`make test-workshop-env` loads `.env` first; use only for runtime-config smoke checks. 850+ unit tests; Discord / Anthropic / httpx stubbed via `tests/_stubs.py`; S3 / Pinboard / micro.blog / Anthropic stubbed per-test.

## Environment

All config via env vars in `.env` (see `.env.example` at the repo root). The bot reads from the repo-root `.env`, not a per-app one.

**Discord — one token per persona** (so each shows its own avatar):

| Variable | Notes |
|---|---|
| `DISCORD_TOKEN_EDDY` / `_LINKY` / `_MARKY` / `_PATTY` / `_SCOUT` | Per-persona bot tokens. A persona with a missing token is skipped at startup; the rest still run. |
| `DISCORD_SERVER_ID`, `DISCORD_WORKSHOP_CATEGORY_ID`, `DISCORD_TEAM_ROLE_ID` | Server scoping |
| `DISCORD_CHANNEL_EDITORIAL`, `_RESEARCH`, `_DISCOVERY`, `_PROMOTION`, `_SUPPORTERS`, `_PRODUCTION`, `_WORKSHOP`, `_CHATTER` | Per-channel IDs |
| `DISCORD_OWNER_USER_ID` | Operator account (Jamie) — gates picker reactions |

(`DISCORD_TOKEN_THINGY` + `DISCORD_CHANNEL_ASK_THINGY` are read by [`../thingy_bridge/`](../thingy_bridge/), not by workshop_bot.)

**API access:**

| Variable | What it powers |
|---|---|
| `ANTHROPIC_EDDY_API_KEY` / `_LINKY` / `_MARKY` / `_PATTY` / `_SCOUT` | Claude API keys for persona LLM calls. Bot startup validates a key for each configured Discord persona token. |
| `ANTHROPIC_GENERAL_API_KEY` | Offline eval and non-persona pipeline LLM calls. |
| `BUTTONDOWN_API_KEY` | `buttondown__*` tools, ship sequence |
| `TINYLYTICS_API_KEY` + `TINYLYTICS_SITE_UID` | `tinylytics__*` tools (Marky) |
| `PINBOARD_API_TOKEN` | `pinboard__*` tools (Linky) |
| `STRIPE_API_KEY` | `stripe__*` tools (Patty) |
| `MICROBLOG_API_KEY` | Journal pull (Micropub source query) |
| `OPENAI_API_KEY` | TTS for the audio pipeline |
| `LIBRARIAN_BRIDGE_SECRET` | Auth for `archive__retrieve` (semantic search via Thingy's `/retrieve`) |
| `GITHUB_PAT_TOKEN` | Fine-grained PAT with Contents:write — for the ship sequence's atomic commit |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` | S3 workspace + CloudFront invalidation |
| `WEEKLY_THING_ASSETS_BUCKET` | Public assets bucket; defaults to `files.thingelstad.com` |

**Runtime:**

| Variable | Default | Purpose |
|---|---|---|
| `WORKSHOP_DB_PATH` | `apps/workshop_bot/data/workshop.db` | SQLite path |
| `WORKSHOP_LOG_LEVEL` | `INFO` | Python log level |
| `WORKSHOP_DEFAULT_MODEL` | `haiku` | Fallback model; per-persona `preferred_model` takes precedence |
| `WORKSHOP_SCHEDULER_ENABLED` | `1` | Set `0` to disable all scheduled jobs |
| `WORKSHOP_EDDY_REVIEW_MODEL` | tier-based | Override for Eddy's post-update review (default: tiered by weekday) |
| `WORKSHOP_ALT_VISION_CAP` | `15` | Per-run cap on alt-text vision calls |

## Tech stack

- Python 3.14
- `discord.py >= 2.4` — async Discord client
- `anthropic` — Claude API
- `apscheduler >= 3.10` — cron-style jobs
- `boto3` — S3 access
- `httpx` — Lambda bridge SSE
- `requests` — REST APIs (Pinboard, Buttondown, Tinylytics, Thingy `/retrieve`)
- `beautifulsoup4` — HTML cleanup for `web__fetch_url` and RSS
- `python-dotenv` — env loading

Models are configurable per-persona (`preferred_model` class attr), per-message (`--haiku` / `--sonnet` / `--opus` flag in the message body), or globally (`WORKSHOP_DEFAULT_MODEL`). Cascade: per-message flag → persona preferred → env default → `haiku` fallback. API keys are purpose-scoped so Anthropic usage can be attributed by persona.

## Storage at a glance

Two layers with a hard boundary:

- **SQLite** at `apps/workshop_bot/data/workshop.db` (gitignored) — operational state. Anything not destined for the published newsletter lives here.
- **S3** at `s3://files.thingelstad.com/weekly-thing/{N}/` — only files the iOS Shortcuts pipeline reads on Sunday. Internal observations, research notes, draft versions never go to S3.

Full table list, the unified asset pattern, and the `tools/s3.py` write-lock convention are in [`CLAUDE.md`](CLAUDE.md). The two thingy_bridge tables (`thingy_tokens` / `thingy_requests` / `thingy_conversations`) moved to [`../thingy_bridge/`](../thingy_bridge/) — workshop_bot doesn't see them.

## Conventions

- Citation format: `#NNN` consistent with the public Q&A surface.
- Prompts are markdown files cached in-process at first read; restart the bot to pick up edits.
- Logging: structured `logger.info("event_name %s", arg)` style.
- `.env` for secrets — never commit. `.env.example` is the source of truth for required keys.
- New schema columns go in `db/schema.sql` for fresh DBs and in `db._COLUMN_MIGRATIONS` for existing DBs (idempotent ALTER).

The full convention list (Pinboard tag rules, micro.blog pull behavior, journal image rehosting, HTML preview drawer, etc.) lives in [`CLAUDE.md`](CLAUDE.md).

## Operations

- [`scripts/admin.sh`](scripts/) — install / start / stop / restart / upgrade / backup / tail. Drives a launchd plist on macOS.
- [`scripts/backup_db.py`](scripts/) — safe online SQLite backup with tiered retention.
- [`scripts/clean.py`](scripts/) — remove cache cruft.
- [`tools/README.md`](tools/README.md) — local-helper + system tool inventory (the surface every persona sees in the agent loop).

## Related reading

- [`CLAUDE.md`](CLAUDE.md) — operational memory (jobs table, conventions, storage details, follow-ups)
- [`../../notes/design/workshop-content-loop-design-brief.md`](../../notes/design/workshop-content-loop-design-brief.md) — the full design rationale that produced this runtime
- [`../../docs/publishing-process.md`](../../docs/publishing-process.md) — the editorial north star: how an issue is built, published, shared
- [`prompts/shared/team.md`](prompts/shared/team.md) — shared cross-persona system prompt
- [`prompts/shared/thingy-voice-reference.md`](prompts/shared/thingy-voice-reference.md) — the voice anchor Patty uses for the supporter CTA
