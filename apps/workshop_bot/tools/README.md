# Workshop bot tools

This directory holds the tool surface available to the workshop personas (Eddy, Linky, Marky, Patty) inside the agent loop. Thingy is a bridge persona and does not run the agent loop, so it gets none of these.

The intent of this README is to be a primer — a future reviewer (human or another agent) should be able to read this once and understand what's available, how to add to it, and what conventions to follow without re-deriving them from `agent_tools.py`.

## Registration pattern

Each tool is a Python function plus an Anthropic JSON-schema spec. The loop in `agent_loop.py` looks up tools by name, calls the function with `(deps, **kwargs)` from the LLM tool-use input, and serializes the return value as the tool result.

Three module-level dicts in `agent_tools.py` form the registry:

- `FUNCS: dict[str, Callable]` — name → function. Each function takes `(deps, **kwargs)` and returns a JSON-serializable Python value (str, int, bool, None, list, dict). Serialization is automatic; if a single tool result exceeds ~50 KB it gets truncated by the loop.
- `SPECS: dict[str, dict]` — name → Anthropic tool spec (`{"name", "description", "input_schema"}`). The schema is what the model sees; keep descriptions tight and concrete.
- `UNIVERSAL: tuple[str, ...]` — names of tools every non-Thingy persona gets by default. Persona classes opt into more by appending to this tuple in their `tools` ClassVar.

`get(name)` and `get_many(names)` build `Tool` dataclass instances (`name`, `spec`, `func`) for the loop to consume.

### `deps` — what flows in

`deps` is a `Deps` object (`personas/base.py`) carrying:

- `corpus` — the archive corpus handle (used by `search_archive`, `get_issue`, `quote_search`, etc.)
- `team` — the `TeamRegistry` (only used by team-orchestration tools)

Tools that don't need either ignore the parameter — Python's `(deps, **kwargs)` shape stays uniform so the loop can dispatch generically.

### `active_persona` — the ContextVar

`agent_tools.active_persona` is a `ContextVar[str]` set by the loop before each tool call to the calling persona's name (`"eddy"`, `"marky"`, etc.). Memory tools (`remember`, `recall`, `forget_note`) read this so notes are correctly attributed without threading the persona name through every call. The same mechanism lets tools that touch per-persona state — like the planned `persona_list`/`persona_read`/`persona_write` — derive their scope automatically.

The default `"unknown"` should never appear in production; if it does, the loop is calling a tool outside its `_execute_tool` wrapper.

### Adding a new tool

1. Write `t_<name>(deps, **kwargs) -> JSON-serializable`. Keep the input shape simple — the model sees the JSON schema and gives back JSON; nested types beyond list/dict/primitives confuse the surface.
2. Add a spec entry to `SPECS["<name>"]` with a *concrete* description. The description is the model's only context for when to call this tool.
3. Add `"<name>": t_<name>` to `FUNCS`.
4. If every persona should have it, append to `UNIVERSAL`. Otherwise, the relevant persona's `tools` ClassVar in `personas/<name>.py` opts in.
5. Add a unit test under `apps/workshop_bot/tests/`.

## Tool inventory

### Universal tools — every persona gets these

Available to Eddy, Linky, Marky, Patty by default (Thingy gets none — it's a bridge).

| Tool | Purpose |
|---|---|
| `search_archive(query, k)` | BM25 search over archive chunks. Cheapest first stop for a topic. |
| `get_issue(number)` | Full body of one issue. |
| `get_section(number, section)` | One named section (`Notable`, `Briefly`, `Featured`, `Microposts`, `Journal`, etc.) of one issue. |
| `list_recent_issues(limit)` | Last N issues, newest first, with subject + abstract. |
| `quote_search(phrase, limit)` | Exact substring across all bodies — verify a phrase appears before claiming it does. |
| `remember(content, kind, key?, related_issue?, expires_in_days?)` | Write a per-persona note to SQLite. `kind` ∈ `preference, observation, todo, context, theme`. |
| `recall(query?, kind?, agent_name?, limit?)` | Read notes. Default: own active notes. `agent_name="*"` reads all personas; pass a name to read theirs. |
| `forget_note(note_id, status)` | Mark a note `resolved` (todo done) or `stale` (no longer applies). Notes are never hard-deleted. |
| `current_issue_number()` | Resolve which issue is in flight (S3 workspace folder). Use when the user says "this weekend's issue". |
| `s3_list_issue_workspaces()` | List every per-issue workspace folder. Highest number is the in-flight issue. |
| `s3_list_issue(issue_number)` | List the files under one workspace folder. |
| `s3_read_issue_file(issue_number, filename)` | Read a text file from `s3://files.thingelstad.com/weekly-thing/issues/{N}/{filename}`. |
| `s3_write_issue_file(issue_number, filename, content)` | Write a text file to that path. Locked: bare filename only, whitelisted extensions, 256 KB max. |

### Per-persona tools

| Persona | Adds (on top of universal) | Notes |
|---|---|---|
| **Eddy** | `fetch_url` | Pull readable text from an external URL — used when reviewing a draft that references an article. |
| **Linky** | `fetch_pinboard`, `fetch_pinboard_unread`, `fetch_pinboard_popular`, `read_stored_bookmarks`, `fetch_url` | Pinboard suite. `fetch_pinboard_unread` is the working set for the next issue (the "to read" pile). `fetch_pinboard_popular` is the site-wide discovery surface. `read_stored_bookmarks` is the cached recent bookmarks (no API hit). |
| **Marky** | `fetch_tinylytics`, `fetch_buttondown_subscribers` | Engagement and subscriber telemetry. Tinylytics is trailing-window; Buttondown subscriber emails are hashed before reaching the model. |
| **Patty** | `get_support_state` | Current nonprofit + dollars-raised + member count, pulled from `apps/site/_data/{stats,support}.json`. |
| **Thingy** | (none) | Thingy is a bridge to the Librarian Lambda — it doesn't run the agent loop. |

### External-API tool details

| Tool | API | Required env | Notes |
|---|---|---|---|
| `fetch_url` | none (HTTP) | none | Read-only, capped at 12 KB by default. |
| `fetch_pinboard*` | Pinboard | `PINBOARD_API_TOKEN` | Linky-only. |
| `fetch_tinylytics` | Tinylytics | `TINYLYTICS_API_KEY`, `TINYLYTICS_SITE_UID` | Marky-only. Currently exposes site-wide stats / pages / referrers / events for a trailing-N-day window. |
| `fetch_buttondown_subscribers` | Buttondown | `BUTTONDOWN_API_KEY` | Marky-only. Email addresses are SHA-256 hashed before reaching the model — never raw addresses. |
| `get_support_state` | none (reads tracked JSON) | none | Patty-only. Reads `apps/site/_data/stats.json` + `support.json` straight from disk; no live API. |

## Path-locking convention (S3 tools)

The `s3_*_issue_file` tools are write-locked via `_resolve_key` in `s3.py`:

- The path is always `weekly-thing/issues/{int issue_number}/{filename}` — no other prefix is reachable.
- `filename` must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$` — single component, no slashes, no `..`.
- Extension must be in `ALLOWED_EXTENSIONS` (`.md`, `.markdown`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv`, `.html`).
- 512 KB read cap, 256 KB write cap.

Any new S3-touching tool should follow the same pattern: a private `_resolve_key` that constructs the bucket-relative path from validated inputs and raises `S3PathError` on any violation. Never let a model-supplied string flow into a key without going through a resolver — otherwise a clever prompt could write outside the intended prefix.

## Conventions

- **Concrete descriptions over clever ones.** The spec description is the model's only signal for when to call. "Use to ground 'what's working lately' instead of guessing" beats "fetch analytics summary".
- **Cap result size.** A tool that can return arbitrary content (HTTP fetch, S3 read) should cap bytes at the helper level, not rely on the agent-loop truncation. Truncated tool results read poorly.
- **JSON-serializable returns.** No `datetime`, no `Path`, no custom classes — convert at the tool boundary.
- **Hash sensitive data.** `fetch_buttondown_subscribers` hashes emails before they reach the model. Apply the same rule to any future tool that touches PII.
- **Per-persona scope via `active_persona`.** When a tool's behavior depends on which persona called it, read `active_persona.get()` rather than asking the model to pass its own name — the model can lie or get confused, the ContextVar can't.
- **`PASS` no-reply convention.** Personas can return the literal string `PASS` (no quotes, no markdown) to indicate "nothing worth saying right now". The team-orchestration handler swallows `PASS` responses without posting. This convention extends to scheduled handlers (heartbeats) — keep it consistent.

## Module layout

```
tools/
├── README.md              ← this file
├── agent_loop.py          ← multi-turn tool-using agent loop, tool dispatch
├── agent_tools.py         ← Tool registry: SPECS, FUNCS, UNIVERSAL, get/get_many
├── anthropic_client.py    ← Claude SDK wrapper, prompt loader, model registry
├── archive.py             ← BM25 corpus loader, search/get_issue/get_section helpers
├── buttondown.py          ← Buttondown subscriber API helper (hashed)
├── conversation.py        ← Discord history → agent-loop history conversion
├── corpus.py              ← Archive corpus handle (loaded once at boot)
├── db.py                  ← SQLite — agent_notes (memory) + agent_runs (telemetry)
├── discord_io.py          ← Chunking + posting helpers for Discord 2000-char limit
├── pinboard.py            ← Pinboard API: live, unread, popular, stored
├── s3.py                  ← Per-issue workspace S3 helper with path-locking
├── startup.py             ← Boot-time announce/coordinate across personas
├── support_state.py       ← Reads apps/site/_data/{stats,support}.json
├── thingy_client.py       ← Thingy bridge HTTP client (Lambda /chat)
├── thingy_render.py       ← Format Lambda streaming output for Discord
├── tinylytics.py          ← Tinylytics REST wrapper
└── web.py                 ← fetch_url helper (readable text only)
```

Updated as new tools land.
