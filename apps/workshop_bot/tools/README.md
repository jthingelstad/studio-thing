# Workshop bot tools

This directory holds the **local-helper** tool surface available to the workshop personas (Eddy, Linky, Marky, Patty) inside the agent loop. External-system tools live one directory up at `apps/workshop_bot/systems/<name>/` (`buttondown`, `pinboard`, `stripe`, `tinylytics`). Thingy is a bridge persona and does not run the agent loop, so it gets none of these.

The intent of this README is to be a primer — a future reviewer (human or another agent) should be able to read this once and understand what's available, how to add to it, and what conventions to follow without re-deriving them from `tools/llm/agent_tools.py`.

## Naming convention

Every tool the model sees uses a `<system>__<action>` name — `archive__search`, `memory__remember`, `workspace__write`, `buttondown__list_subscribers`. There are no flat names; the migration window where both flat and dotted forms coexisted ended in phase 5 of the original redesign.

## Registration pattern

Each tool is a Python function plus an Anthropic JSON-schema spec. The agent loop in `agent_loop.py` looks up tools on the persona's `Deps.registry` by their full `<system>__<action>` name (e.g. `archive__search`, `buttondown__list_subscribers`), calls the function with `(deps, **kwargs)` from the LLM tool-use input, and serializes the return value as the tool result. The double-underscore separator is API-safe (Anthropic enforces `^[a-zA-Z0-9_-]{1,128}$` on custom tool names) so the same name is used in the registry, in the API call, and in prompts — there is no boundary translation. The registry rejects any name that doesn't match that regex, so a slipped `archive.search` fails loudly at boot.

Two paths into the registry, both composed at boot in `bot.py`:

- `register_local_helpers(registry)` — registers every entry in `tools/llm/agent_tools.py`'s `FUNCS` / `SPECS` maps (the local-helper tools defined in this directory).
- `registry.register_system(server)` — registers every tool exposed by a `SystemServer` under its `<server.name>__<tool.name>` prefix (e.g. `ButtondownServer.list_tools()` → `buttondown__<action>`).

The registry rejects duplicate names at registration time. Each `Tool` carries a `source` tag (`"local"` or `"system:<name>"`) so the boot path can audit composition and tests can assert provenance.

### `deps` — what flows in

`deps` is a `Deps` object (`personas/base.py`) carrying:

- `corpus` — the archive corpus handle (used by `archive__search`, `archive__get_issue`, `archive__quote_search`, etc.)
- `team` — the `TeamRegistry` (only used by team-orchestration tools)
- `registry` — the composed `ToolRegistry` (the agent loop reads this; tools rarely need it)

Tools that don't need any of these ignore the parameter — Python's `(deps, **kwargs)` shape stays uniform so the loop can dispatch generically.

### `active_persona` — the ContextVar

`agent_tools.active_persona` is a `ContextVar[str]` set by the loop before each tool call to the calling persona's name (`"eddy"`, `"marky"`, etc.). The memory tools (`memory__remember`, `memory__recall`, `memory__forget`) read this so per-persona state is correctly attributed without threading the persona name through every call.

The default `"unknown"` should never appear in production; if it does, the loop is calling a tool outside its `_execute_tool` wrapper.

### Adding a new local-helper tool

1. Write `t_<name>(deps, **kwargs) -> JSON-serializable`. Keep the input shape simple — the model sees the JSON schema and gives back JSON; nested types beyond list/dict/primitives confuse the surface.
2. Add a spec entry to `SPECS["<namespace>__<action>"]` with a *concrete* description. The description is the model's only context for when to call this tool. The spec's internal `name` field must equal the dict key.
3. Add `"<namespace>__<action>": t_<name>` to `FUNCS`.
4. Add a unit test under `apps/workshop_bot/tests/`.

Every persona sees the full tool surface composed in `bot.py`; lane discipline lives in persona prompts (`prompts/<persona>/prompt.md`), not in a per-persona allowlist.

### Adding a new external-system tool

If the new tool wraps an external API, prefer adding it to a `SystemServer` under `apps/workshop_bot/systems/<name>/server.py` rather than as a local helper. See the four existing system modules for the shape — `list_tools()` returns a list of `ToolDef` records and the registry namespaces them automatically. Adding a brand-new system means a new directory + a one-line `registry.register_system(NewServer())` in `bot.py`.

## Tool inventory — local helpers

These are the tools registered by `register_local_helpers`. Every persona sees all of them.

| Tool | Purpose |
|---|---|
| `archive__retrieve(query, k)` | **Semantic** retrieval via Thingy's `/retrieve` (Bedrock Cohere embed + rerank). Match by meaning, not vocabulary. ~1s round trip, ~$0.001/call. Use for themes/concepts. |
| `archive__search(query, k)` | **Lexical** BM25 search over archive chunks. Cheap, fast. Use for specific phrases, person/product names. |
| `archive__get_issue(number)` | Full body of one issue. |
| `archive__get_section(number, section)` | One named section (`Notable`, `Briefly`, `Featured`, `Microposts`, `Journal`, etc.) of one issue. |
| `archive__list_recent(limit)` | Last N issues, newest first, with subject + abstract. |
| `archive__quote_search(phrase, limit)` | Exact substring across all bodies — verify a phrase appears before claiming it does. |
| `memory__remember(content, kind, key?, related_issue?, expires_in_days?)` | Write a per-persona note to SQLite. `kind` ∈ `preference, observation, todo, context, theme`. |
| `memory__recall(query?, kind?, agent_name?, limit?)` | Read notes. Default: own active notes. `agent_name="*"` reads all personas; pass a name to read theirs. |
| `memory__forget(note_id, status)` | Mark a note `resolved` (todo done) or `stale` (no longer applies). Notes are never hard-deleted. |
| `issue__current_window()` | Return the active in-flight issue window — `{issue_number, pub_date, end_date, start_date, day_count}`. Operator-set via `/eddy issue start`. Returns `{error: ...}` when unset. |
| `issue__list_windows(limit?)` | Recent issue windows, newest first, with `is_active` flag. Use to answer "when did issue #N ship?". |
| `workspace__list_all()` | List every per-issue workspace folder. Use for per-folder modification times; for the active issue's number/dates, prefer `issue__current_window`. |
| `workspace__list_files(issue_number)` | List the files under one workspace folder. |
| `workspace__read(issue_number, filename)` | Read a text file from `s3://files.thingelstad.com/weekly-thing/{N}/{filename}`. |
| `workspace__write(issue_number, filename, content)` | Write a text file to that path. Locked: bare filename only, text-only extension allowlist, 256 KB max. |
| `web__fetch_url(url, max_chars?)` | Fetch a URL and return readable text. ~12 KB cap by default. |
| `site__support_state()` | Current nonprofit + supporter count + past nonprofits, read from `apps/site/_data/{stats,support}.json` (no live API). |
| `react__add(emoji)` | Add one emoji reaction to the message being responded to (posts under the persona's avatar). No-op outside a Discord message turn. |
| `editorial__get_comment(handle)` | Resolve one editorial review comment by its stable handle (`E349-N1`, `E349-X3`, …). Returns body + verdict + the anchored item (when item-scoped) + the replacement handle when superseded. Use when Jamie asks about a handle ("tell me about E349-N1"). |
| `editorial__list_open(issue_number?)` | List open (not-yet-superseded) editorial comments for an issue with their handles + short snippets. Defaults to the in-flight issue. Useful for "what did you flag on this issue?" — follow up per-handle with `editorial__get_comment`. |
| `campaigns__list(status?, limit?)` | All campaigns from Marky's ad-placement ledger, newest first. Default returns every row (live + sunset). Status filter accepts `'live'` or `'sunset'`. Each row carries name, ref, status, started_at, ends_at, expected_signups, expected_traffic, copy, notes. |
| `campaigns__get(name)` | One campaign by name + its most recent metric snapshot (`latest_metric`). Returns `{error}` for unknown names. |
| `campaigns__history(name, limit?)` | Recent `campaign_metrics` rows for one campaign, newest first — the placement's trajectory. Default 30 rows, max 365. |

## Tool inventory — system modules

Composed at boot in `bot.py` via `registry.register_system(...)`. Source code lives at `apps/workshop_bot/systems/<name>/`.

| Namespace | Purpose | Auth |
|---|---|---|
| `buttondown__*` | Subscriber + email engagement (counts, list_subscribers, recent_unsubscribes, subscriber_sources, subscriber_growth, list_recent_emails, email_engagement). Email addresses hashed inside the module. | `BUTTONDOWN_API_KEY` |
| `pinboard__*` (Linky-only) | Bookmark surfaces (recent, unread, popular, stored_recent, tag_summary, lookup_url, save, …). Restricted to Linky. | `PINBOARD_API_TOKEN` |
| `stripe__*` (Patty-only) | Read-only donation surface (balance, recent_donations, donations_by_month, donations_by_ref, year_to_date). Donor name + email hashed inside the module. Restricted to Patty — donor data never enters the other personas' transcripts. | `STRIPE_API_KEY` |
| `tinylytics__*` | Site engagement (summary, top_pages, referrers, sources, leaderboard, journeys, kudos, insights, uptime, attribution). | `TINYLYTICS_API_KEY`, `TINYLYTICS_SITE_UID` |

## Path-locking convention (S3 tools)

The `workspace__*` tools are write-locked via `_resolve_key` in `s3.py`:

- The path is always `weekly-thing/{int issue_number}/{filename}` — no other prefix is reachable. The published archive shares this prefix; the extension allowlist (text-only) is what keeps agents from clobbering shipped image/audio assets.
- `filename` must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$` — no slashes, no `..`.
- Extension must be in `ALLOWED_EXTENSIONS` (`.md`, `.markdown`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv`, `.html`).
- 512 KB read cap, 256 KB write cap.

Any new S3-touching tool should follow the same pattern: a private `_resolve_key` that constructs the bucket-relative path from validated inputs and raises `S3PathError` on any violation. Never let a model-supplied string flow into a key without going through a resolver — otherwise a clever prompt could write outside the intended prefix.

## Conventions

- **Concrete descriptions over clever ones.** The spec description is the model's only signal for when to call. "Use to ground 'what's working lately' instead of guessing" beats "fetch analytics summary".
- **Cap result size.** A tool that can return arbitrary content (HTTP fetch, S3 read) should cap bytes at the helper level, not rely on the agent-loop truncation. Truncated tool results read poorly.
- **JSON-serializable returns.** No `datetime`, no `Path`, no custom classes — convert at the tool boundary.
- **Hash sensitive data.** `buttondown__list_subscribers` and `stripe__recent_donations` hash emails/names inside the system module. Apply the same rule to any future tool that touches PII.
- **Per-persona scope via `active_persona`.** When a tool's behavior depends on which persona called it, read `active_persona.get()` rather than asking the model to pass its own name — the model can lie or get confused, the ContextVar can't.
- **`PASS` no-reply convention.** Personas / jobs can return the literal string `PASS` (no quotes, no markdown) to indicate "nothing worth saying right now". The team-orchestration handler and the agent-loop jobs (Eddy's review, `pinboard-scan`, `daily-metrics`) swallow `PASS` responses without posting. Keep this consistent in new prompts.

## Module layout

```
tools/
├── README.md              ← this file
├── llm/
│   ├── agent_loop.py       ← multi-turn tool-using agent loop, tool dispatch
│   ├── agent_tools.py      ← ToolRegistry, FUNCS/SPECS, register_local_helpers
│   └── anthropic_client.py ← Claude SDK wrapper, prompt loader (<persona>-<file> → prompts/<persona>/<file>.md)
├── content/
│   ├── archive.py / corpus.py / issue.py / draft.py / context.py
│   ├── microblog.py        ← micro.blog Micropub q=source client (journal source)
│   └── journal_images.py   ← rehost micro.blog photo uploads
├── discord/
│   ├── conversation.py / discord_io.py / interaction.py / startup.py
├── issue_items.py         ← row-backed in-flight content model (Notable/Brief/Journal as rows) + editorial_comments (handles like E349-N1)
├── issue_items_sync.py    ← Pinboard + micro.blog → issue_items rows (UPSERT, prune-on-disappearance)
├── issue_items_render.py  ← rows → section markdown bytes (preamble, items, featured sections, marker-interleaved variants)
├── issue_assembly.py      ← atoms + section bodies + features → final.md / buttondown.md (the assembler create-final + build-publish share)
├── db/                    ← SQLite — agent_notes, agent_runs, link_candidates, issue_windows, job_locks, draft_digests, goals, campaigns, issue_items, editorial_comments, …
├── render.py              ← markdown → standalone HTML preview page (draft/final/publish .html twins) + option-cards page (subject/haiku/cta pickers) + side-by-side proposal page (create-final reorder view) + handle badges for the editorial drawer
├── cdn.py                 ← CloudFront invalidation (best-effort) for the public assets bucket
├── avoid_domains.py       ← popular-feed exclusion set (copy of pipeline/content/domain_exclusions.py) — used by pinboard__popular_unseen
├── rss.py                 ← latest_published_issue() from weekly.thingelstad.com/feed.xml (Marky's trigger)
├── s3.py                  ← per-issue workspace S3 helper (path-locked) — backs workspace__*; + write_journal_image (binary, journal/ sub-prefix, not an agent tool)
├── support_state.py       ← Reads apps/site/_data/{stats,support}.json
└── web.py                 ← fetch_url helper (readable text only)
```

External-API clients (`buttondown`, `pinboard`, `stripe`, `tinylytics`) live one directory up at `apps/workshop_bot/systems/<name>/client.py`; their server modules expose the dotted-namespace tool surface.

Updated as new tools land.
