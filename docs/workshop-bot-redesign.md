# Workshop Bot — Tool & Autonomy Redesign Spec

> Source: `apps/workshop_bot/`. This spec is a build target for Claude Code. Treat anything not specified here as preserved from current behavior unless it conflicts with the goals below.

## 1. Goal

The four agent personas (Eddy, Linky, Marky, Patty) are working and showing real promise but are too narrowly scoped: each only sees a slice of the available tools, the tool surface is uneven across systems, and there is no first-class autonomy loop that lets agents propose work unprompted. This redesign reorganizes the tool layer around **systems**, exposes the full tool surface to all four personas, introduces a per-persona **heartbeat** loop for self-directed work, and adds a lightweight **inbox** for structured handoffs.

Thingy is out of scope. It bridges to the production Librarian Lambda; nothing here changes that.

## 2. Goals and non-goals

**In scope.**

- Reorganize external-API tools into **system modules** named after their system (`buttondown`, `pinboard`, `tinylytics`, `stripe`).
- Adopt a uniform `<system>.<action>` tool naming convention.
- Drop per-persona tool tuples; expose the full tool surface to every agent persona.
- Add a `stripe` system (new — read-only, live API).
- Expand the `buttondown` system with sent-email engagement stats and richer subscriber detail.
- Introduce per-persona **heartbeats**: a scheduled wake-up agent turn driven by a `heartbeat.md` prompt file.
- Introduce **inboxes** (per-persona + a shared `team` inbox) for structured agent-to-agent handoffs.
- Fold lighter-weight existing scheduled jobs into heartbeats; preserve the high-care rituals as bespoke jobs.
- Phased migration — system modules land alongside the existing tool registry; personas migrate one at a time, Marky first.

**Out of scope.**

- Thingy / Librarian Lambda changes.
- MCP. Each system module follows an MCP-compatible shape (`list_tools` / `call_tool`) so any one of them can be lifted to a real MCP server later by adding a transport adapter, but no MCP SDK or transport is used today.
- Write actions to external systems (no Buttondown drafts, no Stripe writes, no Pinboard edits in this round).
- Replacing the existing SQLite, archive corpus, web fetch, or S3 helpers — those stay as direct Python helpers.
- Discord routing, peer reactions, team round orchestration — `personas/base.py` and `personas/team.py` keep their current behavior.
- Subscriber emails reaching the LLM in raw form — hashing rule stays.

## 3. Architecture overview

```
                 Discord events
                       │
                       ▼
        ┌──────────────────────────────┐
        │  PersonaBot (per persona)    │
        │  routing + agent loop entry  │
        └──────────────┬───────────────┘
                       │ run_async(prompt, history, persona)
                       ▼
        ┌──────────────────────────────┐
        │  agent_loop.run              │
        │  ─ system prompts (cached)   │
        │  ─ tool call dispatch        │
        └──────────────┬───────────────┘
                       │ uniform Tool registry (boot-composed)
                       ▼
        ┌──────────────────────────────────────────────┐
        │  ToolRegistry                                │
        │   ├── External-system tools (one module each)│
        │   │     ─ buttondown.* (systems/buttondown)  │
        │   │     ─ pinboard.*   (systems/pinboard)    │
        │   │     ─ tinylytics.* (systems/tinylytics)  │
        │   │     ─ stripe.*     (systems/stripe)      │
        │   └── Local-helper tools                     │
        │         ─ archive.*    (BM25 corpus)         │
        │         ─ memory.*     (SQLite agent_notes)  │
        │         ─ inbox.*      (NEW; SQLite)         │
        │         ─ s3_issues.*  (per-issue workspace) │
        │         ─ s3_personas.*(persona scratchpad)  │
        │         ─ web.fetch_url                      │
        │         ─ site.support_state                 │
        │         ─ issue.current_number               │
        └──────────────────────────────────────────────┘
```

Two key shifts relative to today:

1. **The tool registry is composed at boot from system modules and local helpers**, not handwritten in `agent_tools.py`. Each system module registers its own tools; local helpers register via a small declarative table. Adding a tool inside a system is a one-file change in that system's module.
2. **Every persona gets the full tool surface.** The `tools` ClassVar on each persona is removed. Persona prompts and the heartbeat prompt drive when an agent reaches for a tool, not a hardcoded allowlist.

## 4. Tool naming and namespace conventions

All tools follow `<server>.<action>` (dotted) naming. Anthropic accepts dots in tool names; the existing agent loop dispatches by name string and is unaffected.

| Pattern | Example |
|---|---|
| External-system | `buttondown.list_subscribers`, `tinylytics.top_pages`, `stripe.recent_donations` |
| Local helper | `archive.search`, `memory.recall`, `s3_issues.write_file`, `inbox.post`, `web.fetch_url` |

Renames in the migration:

| Today | After |
|---|---|
| `search_archive` | `archive.search` |
| `get_issue` | `archive.get_issue` |
| `get_section` | `archive.get_section` |
| `list_recent_issues` | `archive.list_recent` |
| `quote_search` | `archive.quote_search` |
| `remember` | `memory.remember` |
| `recall` | `memory.recall` |
| `forget_note` | `memory.forget` (status enum unchanged: `resolved` / `stale` / `active`) |
| `current_issue_number` | `issue.current_number` |
| `s3_list_issue_workspaces` | `s3_issues.list_workspaces` |
| `s3_list_issue` | `s3_issues.list` |
| `s3_read_issue_file` | `s3_issues.read_file` |
| `s3_write_issue_file` | `s3_issues.write_file` |
| `persona_list` | `s3_personas.list` |
| `persona_read` | `s3_personas.read_file` |
| `persona_write` | `s3_personas.write_file` |
| `fetch_pinboard` | `pinboard.recent` |
| `fetch_pinboard_unread` | `pinboard.unread` |
| `fetch_pinboard_popular` | `pinboard.popular` |
| `read_stored_bookmarks` | `pinboard.stored_recent` |
| `fetch_url` | `web.fetch_url` |
| `fetch_tinylytics` | `tinylytics.summary` |
| `fetch_tinylytics_ref` | `tinylytics.ref_traffic` |
| `fetch_buttondown_subscribers` | `buttondown.list_subscribers` |
| `get_support_state` | `site.support_state` |

**Backward compatibility during migration.** Both names exist in the registry simultaneously, each pointing at the same handler function. The model sees two tools but they do the same thing. After the last persona migrates, the old names are deleted in one cleanup PR. This is dumber than aliasing but unambiguous to debug.

## 5. System modules

### 5.1 The `SystemServer` shape

Each external system is a class in `apps/workshop_bot/systems/<name>/server.py`:

```python
# apps/workshop_bot/systems/_base.py

from dataclasses import dataclass
from typing import Any, Callable, Protocol

@dataclass(frozen=True)
class ToolDef:
    name: str               # action name only; namespace prefix added by registry
    description: str
    input_schema: dict
    handler: Callable[..., Any]   # (deps, **kwargs) -> JSON-serializable

class SystemServer(Protocol):
    name: str               # namespace prefix, e.g. "buttondown"

    def list_tools(self) -> list[ToolDef]: ...
```

Concrete servers subclass or implement the protocol:

```python
# apps/workshop_bot/systems/buttondown/server.py

from .._base import ToolDef
from . import client  # the existing buttondown.py logic, refactored

class ButtondownServer:
    name = "buttondown"

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="list_subscribers",
                description="...concrete model-facing description...",
                input_schema={...},
                handler=lambda deps, **kw: client.recent_subscribers(**kw),
            ),
            ...
        ]
```

The shape mirrors MCP's `list_tools` so a single server can be lifted to a real MCP server later by adding a transport. No SDK is required today.

### 5.2 The `ToolRegistry`

`apps/workshop_bot/tools/agent_tools.py` becomes a registry composer:

```python
# Sketch

@dataclass(frozen=True)
class Tool:
    name: str            # full dotted name, e.g. "buttondown.list_subscribers"
    spec: dict           # Anthropic tool spec
    func: Callable       # (deps, **kwargs) -> JSON-serializable
    source: str          # "system:<name>" or "local"

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register_system(self, server: SystemServer) -> None:
        for tdef in server.list_tools():
            full = f"{server.name}.{tdef.name}"
            self._add(full, tdef.input_schema, tdef.description, tdef.handler, source=f"system:{server.name}")

    def register_local(self, name: str, description: str, input_schema: dict, handler: Callable) -> None:
        self._add(name, input_schema, description, handler, source="local")

    def all_specs(self) -> list[dict]: ...
    def all_names(self) -> list[str]: ...
    def dispatch(self, name: str, deps, args: dict, persona: str) -> Any: ...
```

The agent loop calls `registry.all_specs()` once per turn (cached) and `registry.dispatch(name, ...)` per tool use.

**Where the registry lives.** Add a `registry: ToolRegistry` field to the `Deps` dataclass in `personas/base.py` (which already carries `corpus` and `team`). The agent loop reads it as `deps.registry`. One instance per process; constructed in `bot.py` boot before any persona is instantiated.

**How system modules get registered.** Explicit list in `bot.py` boot — no auto-discovery. Something like:

```python
# bot.py — sketch
from .systems.buttondown.server import ButtondownServer
from .systems.pinboard.server import PinboardServer
from .systems.tinylytics.server import TinylyticsServer
from .systems.stripe.server import StripeServer

registry = ToolRegistry()
registry.register_system(ButtondownServer())
registry.register_system(PinboardServer())
registry.register_system(TinylyticsServer())
registry.register_system(StripeServer())
register_local_helpers(registry)   # archive.*, memory.*, inbox.*, s3_*, web.*, site.*, issue.*
```

Adding a fifth system later is a one-line change in `bot.py` plus the new `systems/<name>/` module. No registration magic.

### 5.3 The four system modules

#### `buttondown`

Wraps the existing `apps/workshop_bot/tools/buttondown.py` logic plus net-new endpoints. Auth: `BUTTONDOWN_API_KEY`.

| Tool | Status | Returns |
|---|---|---|
| `buttondown.counts` | preserved | `{total, premium, unsubscribed}` |
| `buttondown.list_subscribers` | preserved | normalized subscriber records, emails hashed |
| `buttondown.recent_unsubscribes` | preserved (was bundled into `kind="unsubscribed"`) | recent churn list |
| `buttondown.subscriber_sources` | **new** | aggregated source attribution counts over a trailing window |
| `buttondown.subscriber_growth` | **new** | net subscriber delta + cohort-by-source for trailing window |
| `buttondown.email_engagement` | **new** | per-issue open rate, click rate, top-clicked links |
| `buttondown.list_recent_emails` | **new** | last N sent emails: `id, subject, sent_at, recipients, opens, clicks` (no body) |

PII rule: emails always hashed before they reach the model; raw addresses never leave `systems/buttondown/`.

**Pre-flight (phase 1).** Before committing to `buttondown.email_engagement` / `list_recent_emails`, verify the analytics endpoint shape with one curl against the live API. If those endpoints require a Buttondown plan tier you're not on, the tool returns a "not configured" error and is shipped behind a feature flag rather than removed from the spec.

#### `pinboard`

Wraps `apps/workshop_bot/tools/pinboard.py`. Auth: `PINBOARD_API_TOKEN`.

| Tool | Status | Returns |
|---|---|---|
| `pinboard.recent` | preserved | recent bookmarks (live fetch, persists to SQLite) |
| `pinboard.unread` | preserved | the to-read pile |
| `pinboard.popular` | preserved | site-wide popular feed |
| `pinboard.stored_recent` | preserved | recent bookmarks from SQLite (no API call) |
| `pinboard.tag_summary` | **new** | tag frequency over the unread pile (currently computed inline in `linky_wednesday_check`) |

#### `tinylytics`

Wraps `apps/workshop_bot/tools/tinylytics.py`. Auth: `TINYLYTICS_API_KEY`, `TINYLYTICS_SITE_UID`.

| Tool | Status | Returns |
|---|---|---|
| `tinylytics.summary` | preserved | trailing-window stats + top pages + referrers + events |
| `tinylytics.ref_traffic` | preserved | hits attributed to a `?ref=<tag>` URL |
| `tinylytics.top_pages` | **new (already wrapped, not exposed)** | top pages with hits |
| `tinylytics.referrers` | **new (already wrapped, not exposed)** | top external referrers |
| `tinylytics.events` | **new (already wrapped, not exposed)** | recent custom events (donate, membership) |

#### `stripe` — net new

Auth: `STRIPE_API_KEY` (already required by the build pipeline; reuse). Read-only. No writes, no payment-method touching. Donor data is metadata-only — name and email are hashed before reaching the model.

| Tool | Returns |
|---|---|
| `stripe.balance` | available + pending balance, in USD |
| `stripe.recent_donations` | last N successful charges with `id, amount, currency, created_at, donor_hash, donor_domain, ref_tag (from metadata)`. Donor name/email never returned. |
| `stripe.donations_by_month` | trailing 12 months, `[{month, count, total_usd}]` |
| `stripe.donations_by_ref` | breakdown by `?ref=<tag>` from Stripe metadata, trailing window |
| `stripe.year_to_date` | `{count, total_usd, average_usd, current_nonprofit}` for the current calendar year |

PII rule: donor names and email addresses are hashed before leaving the system module.

**Pre-flight (phase 3).** `stripe.donations_by_ref` requires the donate flow to set `ref` (or similar) on Checkout Session / Payment Link metadata. Verify the existing donate flow (Payment Links from `support.json`'s `stripe_donate_url`) actually sets metadata. If it doesn't, that one tool is documented as "returns empty until donate-link metadata is wired up" and ships anyway — fixing the donate side is a separate task.

### 5.4 Tool description discipline

Every tool description follows the existing `tools/README.md` rule:

> "Concrete descriptions over clever ones. The spec description is the model's only signal for when to call."

Each description includes (a) what the tool returns, (b) when to use it, (c) any caveats (caps, hashing, rate limits).

### 5.5 Errors and partial-failure shape

System tools return errors as a structured payload, never raise into the agent loop:

```json
{ "error": { "type": "RateLimitError", "message": "...", "retry_after_seconds": 30 } }
```

The agent loop renders the error into the tool result so the model can choose to back off or try a different tool.

## 6. Local helpers

These stay as direct Python helpers, but are renamed and registered through the same `ToolRegistry` so the model sees them with consistent dotted naming.

| Group | Module | Tools |
|---|---|---|
| `archive` | `tools/archive.py` + `tools/corpus.py` | `archive.search`, `archive.get_issue`, `archive.get_section`, `archive.list_recent`, `archive.quote_search` |
| `memory` | `tools/db.py` | `memory.remember`, `memory.recall`, `memory.forget` |
| `inbox` (NEW) | `tools/inbox.py` | `inbox.post`, `inbox.list`, `inbox.read`, `inbox.mark_read` |
| `s3_issues` | `tools/s3.py` | `s3_issues.list_workspaces`, `s3_issues.list`, `s3_issues.read_file`, `s3_issues.write_file` |
| `s3_personas` | `tools/persona_s3.py` | `s3_personas.list`, `s3_personas.read_file`, `s3_personas.write_file` |
| `web` | `tools/web.py` | `web.fetch_url` |
| `site` | `tools/support_state.py` | `site.support_state` |
| `issue` | new tiny module `tools/issue.py` | `issue.current_number` (unchanged behavior) |

The path-locking and PII rules from `tools/README.md` carry over verbatim.

## 7. Persona/team binding model

### 7.1 All tools to all personas

Remove the `tools` ClassVar from each persona class (`personas/eddy.py`, `personas/linky.py`, `personas/marky.py`, `personas/patty.py`). This is a **one-shot runtime change** that lands in phase 1 alongside Marky's first migration — all four personas drop their tuples at the same moment so the agent loop has a single code path. The per-persona phasing in §12 is about prompt rewriting and behavior verification, not about the runtime change.

`PersonaBot.core()` passes the full registry into the agent loop on every turn:

```python
# personas/base.py — sketch of the change
async def core(self, *, latest, history, model):
    issue_index = anthropic_client.format_issue_index(...)
    return await agent_loop.run_async(
        persona=self.persona,
        user_message=latest or "(no new content; continue from history)",
        history=history or [],
        tool_names=self.deps.registry.all_names(),  # was list(self.tools)
        deps=self.deps,
        model=self._resolve_model(model),
        issue_index=issue_index,
    )
```

Persona prompts (`prompts/<persona>/prompt.md`) shape lane discipline. Each persona's prompt currently has a "Your tools (in addition to the universal …)" section that becomes incorrect when the per-persona tuple goes away — these need editing as part of each persona's migration phase. The team prompt (`prompts/shared/team.md`) gets a small new section:

> "You have the full team tool surface. Tools that aren't your lane (Marky reaching for Pinboard, Eddy reaching for Stripe) are still available — use them when crossing lanes is the right answer, but stay in your lane by default."

Thingy is unaffected — it remains a bridge persona without the agent loop, gets no tool surface.

### 7.2 Caching

The agent loop already caches the team prompt and the issue index via ephemeral cache markers. With a larger tool list, keep the cache marker on the last tool spec (existing pattern). All four personas share the same tool list, so the cached tool block hits across personas.

### 7.3 Token budget impact

Today's tool list per persona is ~10–15 tools; the post-redesign list is ~35 tools. Each tool spec is small (~200 tokens with description + schema), so the full list is ~7 KB of cached input — a noticeable but tolerable cache footprint. **During transition** (phases 0–4), both the old and new names for the ~17 renamed local helpers are registered simultaneously, pushing the tool block to ~12 KB. Phase 5 cleanup removes the old names and the block returns to ~7 KB. Verify with the `usage_total` accumulator already in the agent loop after the first persona migrates.

## 8. Heartbeat architecture

### 8.1 What a heartbeat is

A heartbeat is a scheduled agent turn that fires with a heartbeat-specific prompt instead of a Discord message. The persona's full tool surface is available. The default action is `PASS` (the existing convention) unless the heartbeat finds something material to surface.

The agent loop already supports loading `<persona>-heartbeat` prompt files (see `tools/anthropic_client.py:_resolve_prompt_path`); this is operationalized.

### 8.2 File layout

```
apps/workshop_bot/prompts/
├── shared/
│   └── team.md              ← cached system prompt; small new section
├── eddy/
│   ├── prompt.md
│   └── heartbeat.md         ← NEW — Eddy's daily wake-up
├── linky/
│   ├── prompt.md
│   └── heartbeat.md         ← NEW
├── marky/
│   ├── prompt.md
│   └── heartbeat.md         ← NEW
└── patty/
    ├── prompt.md
    └── heartbeat.md         ← NEW
```

A heartbeat prompt:

- Briefs the persona on the cadence ("It's a 3-hour heartbeat. Default is PASS.").
- Lists a small checklist (inbox first, then live campaigns / queue / draft / etc.).
- Specifies output discipline (PASS vs. concrete observation).
- References the inbox by name so the agent looks there before doing anything else.

Voice-neutral skeleton Claude Code starts each persona's `heartbeat.md` from (Jamie tunes voice afterward):

```
It's a <cadence> heartbeat. Default is PASS unless something material has changed.

Step 1: `inbox.list(filter='unread')` — read what's waiting for you. Mark each item read or acted before continuing.
Step 2: <persona-specific checklist of 2–4 bullets>
Step 3: Decide. If you have something concrete to surface, post 1–3 sentences. Otherwise return exactly: PASS
```

### 8.3 Authorship

Claude Code drafts initial heartbeat prompts in phase 4, following each persona's existing `prompt.md` voice. Jamie reviews and tunes before flipping `WORKSHOP_HEARTBEATS_ENABLED=1`. Heartbeats are creative content; reasonable v1 from Claude Code is faster than a back-and-forth on tone.

### 8.4 Cron entries

Add to `scheduler/jobs.py`:

| Job ID | Cron (Central) | Persona | Cadence rationale |
|---|---|---|---|
| `eddy-heartbeat` | daily at 08:30 | Eddy | One pulse per day; hit it before Jamie's morning writing window. Replaces `eddy-saturday-prep` (folded). |
| `linky-heartbeat` | every 6h, 06:00–22:00 | Linky | Replaces `linky-popular-scan` and `linky-research-unread`; one prompt covers both behaviors. |
| `marky-heartbeat` | every 3h, 07:00–22:00 | Marky | Already referenced in marky/prompt.md. Replaces `marky-daily-engagement` (folded). |
| `patty-heartbeat` | daily at 09:00 | Patty | Lightweight check on supporter activity. Thursday `patty-thursday-member-json` ritual is preserved. |

### 8.5 Handler

A single shared handler in `scheduler/handlers.py`. Wrap in the existing `db.AgentRun` context manager so heartbeats land in `agent_runs` telemetry the same way interactive turns do (see `personas/base.py:handle` for the pattern):

```python
import functools
from ..tools import db, anthropic_client
from ..personas.base import is_pass_response

async def heartbeat(persona: str, ctx: JobContext) -> None:
    bot = ctx.bot(persona)
    if bot is None:
        return
    prompt_text = anthropic_client.load_prompt(f"{persona}-heartbeat")
    with db.AgentRun(persona, trigger="heartbeat") as run:
        answer, meta = await bot.core(latest=prompt_text, history=[], model=None)
        run.records_written = 0 if (not answer or is_pass_response(answer)) else 1
    if not answer or is_pass_response(answer):
        return
    channel = ctx.channel(<persona's home channel env>, persona=persona)
    if channel:
        await ctx.post(channel, answer, suppress_embeds=True)
```

Each `JobSpec`'s `func` is `functools.partial(heartbeat, persona='<name>')` so the existing dispatcher signature `Callable[[JobContext], Awaitable[None]]` is preserved without inventing a wrapper class:

```python
JobSpec(
    id="marky-heartbeat",
    cron="0 7-22/3 * * *",
    func=functools.partial(handlers.heartbeat, persona="marky"),
),
```

### 8.6 Loop budget and model

Each heartbeat is one agent loop run, max 8 iterations (current default). Add `WORKSHOP_HEARTBEAT_MODEL` env var (default `haiku`) so cost is controllable without code changes. Rituals continue to use Sonnet/Opus per the persona's `preferred_model`.

### 8.7 Disabling

`WORKSHOP_HEARTBEATS_ENABLED` env var (default `1`) lets Jamie kill all heartbeats independently of `WORKSHOP_SCHEDULER_ENABLED`. Useful when an upstream API is degraded and you want the rituals to keep running while heartbeats stay quiet.

## 9. Inbox design

### 9.1 Storage

A new SQLite table:

```sql
CREATE TABLE IF NOT EXISTS agent_inbox (
    id INTEGER PRIMARY KEY,
    recipient TEXT NOT NULL,           -- persona name or 'team'
    sender TEXT NOT NULL,              -- persona name or 'system'
    kind TEXT NOT NULL,                -- 'handoff' | 'request' | 'fyi' | 'completed'
    subject TEXT NOT NULL,             -- short summary
    body TEXT NOT NULL,                -- markdown payload
    metadata TEXT,                     -- JSON
    related_issue INTEGER,             -- optional
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TEXT,                      -- null until recipient marks read
    expires_at TEXT                    -- optional; defaults to created_at + 14 days
);
CREATE INDEX idx_agent_inbox_recipient ON agent_inbox(recipient, read_at);
```

Migration: add the `CREATE TABLE` and `CREATE INDEX` blocks to `db/schema.sql` for fresh installs, and run an idempotent `CREATE TABLE IF NOT EXISTS` (+ index) at boot from `db.py` for existing DBs. This matches the convention in `apps/workshop_bot/README.md`'s Database section. `_COLUMN_MIGRATIONS` is reserved for `ALTER TABLE` on existing tables; new tables live in `schema.sql` plus the boot-time `CREATE … IF NOT EXISTS`.

### 9.2 Tools

| Tool | Description |
|---|---|
| `inbox.post(recipient, kind, subject, body, related_issue?, metadata?)` | Send a structured message. `recipient` is a persona name or `team`. Sender is derived from `active_persona` ContextVar. |
| `inbox.list(filter?, limit?)` | List your inbox (default unread). `filter` accepts `unread`, `all`, `kind=handoff`, `related_issue=N`. |
| `inbox.read(id)` | Read one inbox item. Does *not* mark it read — call `inbox.mark_read` when done acting on it. |
| `inbox.mark_read(id, status?)` | Mark an item read. `status` ∈ `read`, `acted`, `dismissed` (default `read`). |

Owner is derived from `active_persona` for `list/mark_read`. For `post`, `recipient` is supplied and validated against known persona names plus `team`.

### 9.3 Heartbeat integration

Every `heartbeat.md` opens with:

> "Step 1: `inbox.list(filter='unread')` — read anything waiting for you, mark it read or acted before continuing. Then `inbox.list(filter='unread', recipient='team')` for any team-wide handoffs."

That keeps inboxes from going stale and makes the loop visible.

### 9.4 Use case examples

- Friday Linky finishes curation and posts to Discord, then calls `inbox.post(recipient='eddy', kind='handoff', subject='Curated set for #348', body='<top items>', related_issue=348)`. Saturday-morning Eddy heartbeat picks it up.
- Marky notices a referral spike. `inbox.post(recipient='team', kind='fyi', subject='dd-2026-05-15 spike', …)`. Visible to all personas at next heartbeat.
- Patty drafts Thursday's CTA. `inbox.post(recipient='marky', kind='handoff', subject='Tone of this week's CTA', body='<framing notes>')` so Marky's subject-line draft can match.

## 10. Existing scheduled jobs — disposition

| Job ID today | Action |
|---|---|
| `linky-wednesday-check` | **Fold into `linky-heartbeat`.** |
| `linky-friday-curation` | **Keep as a bespoke ritual.** High-stakes; explicit prompt is preserved. |
| `linky-popular-scan` | **Fold into `linky-heartbeat`.** |
| `linky-research-unread` | **Fold into `linky-heartbeat`.** |
| `marky-daily-engagement` | **Fold into `marky-heartbeat`.** |
| `marky-weekly-subscriber-report` | **Keep as a bespoke ritual.** Monday 11:00. |
| `patty-thursday-member-json` | **Keep as a bespoke ritual.** Thursday member.json write. |
| `eddy-saturday-prep` | **Fold into `eddy-heartbeat`.** Saturday becomes one branch ("if today is Saturday, surface what you've stored; otherwise default scan"). |

Net: 8 scheduled jobs → 4 heartbeats + 3 rituals = 7 cron entries. Cleaner separation between everyday agent attention and deliberate weekly ritual.

## 11. File / module structure after migration

```
apps/workshop_bot/
├── README.md                       # updated: tool surface, system modules, heartbeats, inbox
├── bot.py                          # unchanged shape; loads system modules at startup
├── eval.py                         # extended to run heartbeats offline (--heartbeat flag)
├── personas/
│   ├── base.py                     # tools ClassVar removed; passes registry.all_names()
│   ├── team.py                     # unchanged
│   ├── eddy.py / linky.py / ...    # tools tuple removed; only identity + model
│   └── thingy.py                   # unchanged
├── prompts/
│   ├── shared/team.md              # small new section on full tool surface
│   └── <persona>/{prompt.md, heartbeat.md}
├── systems/                        # NEW
│   ├── __init__.py
│   ├── _base.py                    # SystemServer protocol + ToolDef dataclass
│   ├── _loader.py                  # discovers + registers system modules at boot
│   ├── buttondown/
│   │   ├── __init__.py
│   │   ├── server.py               # ButtondownServer.list_tools / handler dispatch
│   │   └── client.py               # the existing buttondown.py logic, refactored
│   ├── pinboard/
│   │   ├── server.py
│   │   └── client.py
│   ├── tinylytics/
│   │   ├── server.py
│   │   └── client.py
│   └── stripe/
│       ├── server.py
│       └── client.py
├── tools/
│   ├── README.md                   # updated: dotted naming, system modules, inbox, heartbeats
│   ├── agent_loop.py               # passes tool_names through; resolves model for heartbeats
│   ├── agent_tools.py              # ToolRegistry composes system + local tools
│   ├── anthropic_client.py         # unchanged (already supports heartbeat prompts)
│   ├── archive.py / corpus.py      # unchanged behavior; renamed in registry
│   ├── conversation.py             # unchanged
│   ├── db.py                       # adds agent_inbox table + helpers
│   ├── discord_io.py               # unchanged
│   ├── inbox.py                    # NEW — wraps the agent_inbox table
│   ├── issue.py                    # NEW — issue.current_number (extracted)
│   ├── persona_s3.py               # unchanged behavior; renamed in registry
│   ├── s3.py                       # unchanged behavior; renamed in registry
│   ├── support_state.py            # unchanged behavior; renamed in registry
│   ├── thingy_client.py            # unchanged
│   ├── thingy_render.py            # unchanged
│   └── web.py                      # unchanged behavior; renamed in registry
├── scheduler/
│   ├── jobs.py                     # 4 heartbeat JobSpecs + 3 ritual JobSpecs
│   ├── handlers.py                 # bespoke ritual handlers + shared heartbeat handler
│   └── runner.py                   # unchanged
└── tests/
    ├── test_inbox.py               # NEW
    ├── test_systems.py             # NEW — list_tools / dispatch round-trip per system
    ├── test_heartbeats.py          # NEW — heartbeat handler dispatch + PASS swallow
    └── test_*.py                   # existing tests updated for renamed tools
```

The legacy `tools/buttondown.py`, `tools/pinboard.py`, `tools/tinylytics.py` are deleted once their system modules are stable; their content moves into `systems/<name>/client.py`.

## 12. Migration plan (phased)

Five phases. Each is a separately reviewable PR.

### Phase 0 — scaffolding (no behavior change)

- Add `systems/` package with `_base.py` and `_loader.py`.
- Add the `ToolRegistry` in `tools/agent_tools.py`. Compose system-module tools and local helpers; preserve the existing flat `FUNCS` / `SPECS` as the local-helper backing during transition.
- Register the local helpers under their dotted names. Old names remain registered too — both names point at the same handler.
- Add `tools/inbox.py` and the `agent_inbox` table migration.
- Add `WORKSHOP_HEARTBEATS_ENABLED` env var (defaulted off until phase 4).
- Tests: registry composition, dual-name dispatch, inbox lifecycle.

### Phase 1 — Marky's system migration

- Build `systems/buttondown/`, `systems/tinylytics/` (current surface + new tools listed in §5.3).
- Pre-flight Buttondown's email-engagement endpoint (one curl). If the current plan tier doesn't expose it, ship `email_engagement` and `list_recent_emails` behind a feature flag; their handler returns `{"error": ...}`.
- **Drop the `tools` ClassVar from all four persona classes** (one-shot runtime change; see §7.1). Every persona now sees the full registry.
- Rewrite Marky's `prompt.md` "Your tools (in addition to …)" section to reference dotted tool names. Eddy's, Linky's, and Patty's prompts keep their old wording until their respective phases — they still work because the registry has both old and new names registered.
- Old `tools/buttondown.py` and `tools/tinylytics.py` become thin shims that forward into `systems/<name>/client.py` while other personas still reference them.
- Tests: Marky's existing tests pass; new system tests pass; verify all four personas can call the renamed local helpers (`archive.search` etc.) via the registry.

### Phase 2 — Linky and `pinboard`

- Build `systems/pinboard/`.
- Rewrite Linky's `prompt.md` tools section to reference dotted names. (`tools` ClassVar already removed in phase 1.)
- Linky's existing scheduled jobs stay alive at this phase — heartbeat takes over in phase 4.

### Phase 3 — `stripe` + Eddy + Patty migration

- Build `systems/stripe/` from scratch.
- Pre-flight Stripe metadata: confirm whether the existing donate flow sets `ref` (or similar) on Payment Link / Checkout Session metadata. Document whatever's true; don't block on it.
- Rewrite Eddy's and Patty's `prompt.md` tools sections to reference dotted names. (`tools` ClassVar already removed in phase 1.)
- Patty's Thursday ritual now has `stripe.balance` + `stripe.year_to_date` available for the CTA.
- Marky's `prompt.md` campaign ledger section: add `stripe.donations_by_ref` to the "watching a live campaign" loop alongside `tinylytics.ref_traffic`.

### Phase 4 — heartbeats + inbox in production

- Claude Code drafts `heartbeat.md` for all four personas, voice-matched to each persona's existing `prompt.md`. Jamie reviews and tunes before activation.
- Add the four heartbeat JobSpecs.
- Fold the lighter cron jobs: delete `linky-wednesday-check`, `linky-popular-scan`, `linky-research-unread`, `marky-daily-engagement`, `eddy-saturday-prep` from `jobs.py`. Their handler functions stay in `handlers.py` for one release as a safety net, then deleted in phase 5.
- Default `WORKSHOP_HEARTBEATS_ENABLED=1`.
- Personas start using the inbox in their heartbeat opens.

### Phase 5 — cleanup

- Remove the old tool names from the registry.
- Delete legacy `tools/buttondown.py`, `tools/pinboard.py`, `tools/tinylytics.py` shims.
- Delete unused scheduled-handler functions.
- Update `apps/workshop_bot/README.md` and `apps/workshop_bot/tools/README.md`.
- Update tests still calling old names.

## 13. Test and validation strategy

The existing 81-unit-test suite is the baseline. New coverage:

- **Per system: `test_systems.py`.** For each `SystemServer`, round-trip `list_tools()` and dispatch one handler per tool. Stub the underlying HTTP client. Verify tool descriptions, input schemas, and error-shape contract.
- **Tool registry composition: `test_tool_registry.py`.** Composing system + local helpers produces a single namespace; collisions are rejected at boot; old + new names dispatch correctly during the migration window.
- **Inbox lifecycle: `test_inbox.py`.** Post → list → read → mark_read; recipient validation; team inbox semantics; unread filter.
- **Heartbeat dispatch: `test_heartbeats.py`.** Shared `heartbeat(persona, ctx)` resolves the right prompt file, invokes `bot.core`, swallows `PASS`, posts non-PASS replies through `ctx.post`. Stub the agent loop.
- **Persona offline eval (`eval.py`)** gets a `--heartbeat` flag so any heartbeat can be rehearsed without Discord.
- **End-to-end smoke (manual):** before flipping `WORKSHOP_HEARTBEATS_ENABLED=1`, run each heartbeat once via `python -m apps.workshop_bot.scheduler.runner --once <id>` and verify the channel post + inbox state.

## 14. Operational concerns

- **Cost.** With heartbeats running every 3h for Marky (8/day), every 6h for Linky (4/day), daily Eddy and daily Patty, the bot does ~14 extra LLM turns per day. At Haiku rates with the cached system prompts, the daily incremental cost is small (~$0.10–$0.20). Verify after one week; tune cadence if needed.
- **Pinboard rate limits.** The 6h `linky-heartbeat` cadence is at the edge of friendly. If extended to 3h later, add caching to `pinboard.popular`.
- **Stripe key scoping.** Use a Stripe restricted key with read-only access to charges, balance, and customer metadata. Add to `.env.example`. Confirm the existing `STRIPE_API_KEY` used by the build pipeline is suitable, or mint a separate restricted key for the bot.
- **Inbox cleanup.** A weekly cron prunes inbox items past `expires_at` (default 14 days). `acted` / `dismissed` items are removed sooner (3 days).

## 15. Open questions / future work

- **Write actions to external systems.** When Marky should be able to schedule a Buttondown email send or Patty should mint a Stripe Checkout session with metadata, add a `write` permission tier to system tools and gate them behind explicit confirmation in Discord.
- **Real MCP, separately.** The `SystemServer` shape is deliberately MCP-compatible. If you want to learn MCP for real (separate side project), the cleanest path is to build *one* real MCP server (stdio transport) for one of these systems — most likely `pinboard` for novelty or `archive` for utility — and consume it from Claude Desktop or Claude Code. That gives you the protocol experience the in-process choice doesn't.
- **Workshop_bot ↔ Thingy corpus consolidation.** Already noted in the project README as deferred. Dotted-namespace `archive.*` tools are friendly to a future swap from local BM25 to a `thingy.archive_search` tool that hits the Lambda's retrieval endpoint.
- **Memory-as-system.** Today memory is local SQLite. If Thingy or other agents need shared memory, lift it to a system module (the naming already aligns: `memory.recall` / `memory.remember`).
- **Heartbeat self-tuning.** Agents could adjust their own cadence based on observed activity. Out of scope here.

## 16. Glossary

- **System module** — a class (`SystemServer`) exposing `list_tools` plus per-tool handlers, encapsulating one external system. In-process; MCP-compatible in shape; not actually MCP.
- **Heartbeat** — a scheduled agent turn fired by cron with a persona's `heartbeat.md` prompt instead of a Discord message.
- **Inbox** — a SQLite-backed structured handoff surface; complements Discord channels and shared memory.
- **Ritual** — a high-care, deliberately preserved scheduled job (Friday curation, Thursday member.json, Monday subscriber report). Not folded into heartbeats.
- **`active_persona`** — the `ContextVar` set by the agent loop before each tool call; how `inbox.*`, `s3_personas.*`, and `memory.*` derive scope.
- **Tool surface** — the set of dotted-named tools every persona can see. Distinct from "tool capability," which is gated by prompts and (in future) by write-permission tiers.

---

## Build sequencing summary for Claude Code

1. Read this spec end-to-end before touching code.
2. Phase 0 first — registry + dual-name dispatch + inbox table — no behavior change to any persona.
3. Marky in phase 1 (most tool diversity, smallest persona surface area, easiest to verify). Pre-flight the Buttondown email-engagement endpoint before committing.
4. Linky, then Stripe + Patty + Eddy. Pre-flight Stripe metadata before committing `stripe.donations_by_ref`.
5. Heartbeats last — once tool surface is stable. Claude Code drafts heartbeat prompts; Jamie reviews before flipping the env var.
6. Cleanup phase removes legacy names and shims.

Land each phase as a reviewable PR. After each phase, the bot must pass the full test suite plus the hand-rehearsed smoke check (one heartbeat dry-run + one ritual dry-run + one Discord-mention turn per persona).
