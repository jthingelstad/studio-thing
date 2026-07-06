"""Anthropic JSON-schema specs for the local-helper tools (moved from local_tools.py).

One entry per tool name to its Anthropic tool schema. Pure data, consumed by
``local_tools.register_local_helpers`` alongside the ``FUNCS`` dispatch map.
"""

from __future__ import annotations

from typing import Any


SPECS: dict[str, dict[str, Any]] = {
    "archive__search": {
        "name": "archive__search",
        "description": (
            "BM25 LEXICAL search over Weekly Thing archive chunks. Use when the query is a SPECIFIC "
            "PHRASE, person, or product name — anything where the exact words matter. Cheap, fast, "
            "always available. For thematic / conceptual lookups (where the words may differ from "
            "the meaning) prefer archive__retrieve. Iterate — refine the query based on what comes back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "description": "max results, default 8"},
            },
            "required": ["query"],
        },
    },
    "archive__retrieve": {
        "name": "archive__retrieve",
        "description": (
            "SEMANTIC archive retrieval via Bedrock Cohere embed + Cohere rerank against the "
            "pre-embedded corpus. Use for THEME / CONCEPT / IDEA queries — finds matches by meaning, "
            "not by shared words. The right pick when the user asks 'what has Jamie written about X' "
            "where X is a concept (privacy, agent collaboration, slow software) rather than a literal "
            "string. Slower and more expensive than archive__search (~1s round trip, ~$0.001/call) — "
            "use the lexical search first when an exact phrase will do. Returns the same shape as "
            "archive__search; on retrieval failure returns an error dict so you can fall back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "description": "max results, default 8"},
            },
            "required": ["query"],
        },
    },
    "archive__get_issue": {
        "name": "archive__get_issue",
        "description": (
            "Return one full issue (front matter + body, truncated if very long). "
            "Use when you need full context for a specific issue you already have a number for."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": ["integer", "string"]}},
            "required": ["number"],
        },
    },
    "archive__get_section": {
        "name": "archive__get_section",
        "description": (
            "Pull one named section from one issue (e.g. 'Notable', 'Briefly', 'Featured', 'Microposts'). "
            "Cheaper than archive__get_issue when you only need that section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": ["integer", "string"]},
                "section": {"type": "string"},
            },
            "required": ["number", "section"],
        },
    },
    "archive__list_recent": {
        "name": "archive__list_recent",
        "description": (
            "Last N issues by number (newest first), with date, subject, topics, and abstract. "
            "Use to ground 'the latest', 'last few', 'recent' references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "default 10"}},
        },
    },
    "archive__quote_search": {
        "name": "archive__quote_search",
        "description": (
            "Exact substring search across issue bodies. Use to verify a specific phrase or product name "
            "actually appears in the archive — do not infer presence from archive__search hits alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phrase": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["phrase"],
        },
    },
    "archive_lookup__get_issue": {
        "name": "archive_lookup__get_issue",
        "description": (
            "Structured metadata for one shipped issue from the historical DB record — "
            "subject, slug, description, publish_date, word_count, notable/briefly/domain/link "
            "counts, audio_url + duration + voice, era. Sub-millisecond SQL lookup. Distinct from "
            "archive__get_issue (which reads the markdown body): use this when you need NUMBERS "
            "(counts, durations, era buckets) instead of prose. Returns a not-filed message if "
            "the issue hasn't been put to bed yet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": "integer"}},
            "required": ["number"],
        },
    },
    "archive_lookup__find_by_domain": {
        "name": "archive_lookup__find_by_domain",
        "description": (
            "All issues citing the given domain in any link, newest first. Each result carries "
            "{number, publish_date, subject, absolute_url, hit_count}. Use for questions like "
            "'has Jamie linked to this site before?' or 'how often does Daring Fireball show up?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Lowercase domain, e.g. 'daringfireball.net'"},
                "limit": {"type": "integer", "description": "default 50"},
            },
            "required": ["domain"],
        },
    },
    "archive_lookup__find_in_year": {
        "name": "archive_lookup__find_in_year",
        "description": (
            "All issues shipped in the given year, newest first. Use for yearly retrospectives or "
            "filtering historical questions by a specific year."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"year": {"type": "integer", "description": "Four-digit year"}},
            "required": ["year"],
        },
    },
    "archive_lookup__link_history": {
        "name": "archive_lookup__link_history",
        "description": (
            "Every shipping of an exact URL — issue number, section ('notable' or 'briefly'), "
            "position within section, publish_date. Forward-looking: today Pinboard refuses to "
            "re-pin a URL already bookmarked, so dupes can't reach workshop via the current "
            "ingest path. This will matter when workshop hosts link commentary directly. "
            "Returns an empty list if the URL has never been shipped (the common case)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "archive_lookup__domain_history": {
        "name": "archive_lookup__domain_history",
        "description": (
            "Aggregate snapshot for a domain: total link_count, issue_count, first/last issue "
            "numbers + dates, plus the latest 5 issues that cited it. Empty dict if the domain "
            "isn't in the corpus. Cheaper and more decisive than scanning archive__search hits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
    "archive_lookup__recent": {
        "name": "archive_lookup__recent",
        "description": (
            "The N most recently shipped issues by number, sourced from the DB record — carries "
            "word_count, audio_url, era columns the corpus-backed archive__list_recent doesn't. "
            "Use for 'what just shipped?' questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "description": "default 10"}},
        },
    },
    "archive_lookup__stats": {
        "name": "archive_lookup__stats",
        "description": (
            "Corpus-wide totals from the DB record: total_issues, total_links, total_notable, "
            "total_briefly, total_words, unique_domains, issues_with_audio, audio_coverage_pct, "
            "first_date, last_date. The numbers Marky reports in retros and the home-page hero "
            "displays. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "archive_lookup__list_links": {
        "name": "archive_lookup__list_links",
        "description": (
            "Every link row for one issue, ordered by (section, position). Pass `section` to "
            "filter to 'notable' or 'briefly' only. Useful when you want the exact link list "
            "without parsing markdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "section": {"type": "string", "description": "Optional: 'notable' or 'briefly'"},
            },
            "required": ["issue_number"],
        },
    },
    "site__support_state": {
        "name": "site__support_state",
        "description": (
            "Current support program state: this year's nonprofit, supporter count, amount raised, "
            "past nonprofits. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "web__fetch_url": {
        "name": "web__fetch_url",
        "description": (
            "Fetch a URL and return readable text (title + extracted body). Use to actually "
            "read what a bookmark is about — Pinboard's title and tags often aren't enough "
            "to judge fit. Truncates long pages; binary content rejected; ~12KB cap on text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "description": "default 12000"},
            },
            "required": ["url"],
        },
    },
    "web__read_length": {
        "name": "web__read_length",
        "description": (
            "Fetch a URL and bucket how long it is to read: 'short' (<~800 words), 'medium', "
            "'long' (>~2500 words), or 'unknown' if it can't be fetched (paywall, login, "
            "binary). Returns {url, bucket, word_count}. Cheaper to reason over than fetching "
            "the whole body when you only need the length (e.g. gauging a toread pile)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "memory__remember": {
        "name": "memory__remember",
        "description": (
            "Save a note to long-term memory — visible to all teammates and persists across "
            "sessions. Use for: preferences Jamie has expressed, observations to carry "
            "forward, todos for yourself, themes you're tracking, context that mattered. "
            "`kind` is one of: preference, observation, todo, context, theme. `key` is an "
            "optional short retrieval label (e.g. 'jamie:ai-fatigue')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["preference", "observation", "todo", "context", "theme"],
                },
                "key": {"type": "string"},
                "related_issue": {"type": "integer"},
                "expires_in_days": {"type": "integer"},
            },
            "required": ["content"],
        },
    },
    "memory__recall": {
        "name": "memory__recall",
        "description": (
            "Read notes from long-term memory. Default scope is your own active notes; "
            "set `agent_name` to a teammate's name to read theirs, or '*' to read everyone's. "
            "`query` does substring search across content and key. Use to surface relevant "
            "preferences/themes/todos before answering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string"},
                "agent_name": {"type": "string"},
                "limit": {"type": "integer", "description": "default 20"},
                "include_resolved": {"type": "boolean"},
            },
        },
    },
    "memory__forget": {
        "name": "memory__forget",
        "description": (
            "Mark a memory note as resolved (the todo is done) or stale (no longer "
            "applicable). Notes are never hard-deleted; resolved/stale notes drop out of "
            "default memory__recall results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["resolved", "stale", "active"]},
            },
            "required": ["note_id"],
        },
    },
    "followup__schedule": {
        "name": "followup__schedule",
        "description": (
            "Schedule a follow-up for yourself — the ONLY thing that will actually bring a "
            "commitment back; there is no other reminder or heartbeat. Use it whenever you tell "
            "Jamie you'll revisit something at a specific time or once the issue reaches a "
            "number. Give a clear `note` (what you're following up on, written so future-you "
            "understands it without this conversation) and exactly one trigger: `when` — an ISO "
            "date `YYYY-MM-DD` (taken as ~6pm that day) or datetime `YYYY-MM-DDTHH:MM` (compute "
            "it from today's date in your context); `in_days` — a relative offset that fires "
            "~6pm that many days out (`1` = tomorrow evening, `30` = roughly next month); or "
            "`at_issue` — an issue number, fires once that issue is the in-flight one. When it "
            "comes due, you're handed the note + current context and post a check-in in your "
            "channel. `followup__list` / `followup__cancel` to manage them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "What you're following up on — self-contained."},
                "when": {"type": "string", "description": "ISO date YYYY-MM-DD or datetime YYYY-MM-DDTHH:MM."},
                "in_days": {"type": "integer", "description": "Relative offset in days (1 = tomorrow evening)."},
                "at_issue": {"type": "integer", "description": "Fire once this issue number is in flight."},
            },
            "required": ["note"],
        },
    },
    "followup__list": {
        "name": "followup__list",
        "description": "List your pending follow-ups — id, when each fires, and the note.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "followup__cancel": {
        "name": "followup__cancel",
        "description": "Cancel one of your pending follow-ups by id (from followup__list).",
        "input_schema": {
            "type": "object",
            "properties": {"followup_id": {"type": "integer"}},
            "required": ["followup_id"],
        },
    },
    "issue__current_window": {
        "name": "issue__current_window",
        "description": (
            "Return the active in-flight issue window — the one Jamie is "
            "assembling this week. Returns {issue_number, pub_date, end_date, "
            "start_date, day_count, set_at, set_by}. **The in-flight issue is "
            "NOT in your archive corpus** (archive__search / archive__get_issue "
            "won't find it; it's a draft). Date semantics: pub_date is the "
            "Saturday it ships; end_date = pub_date - 1 day is the content "
            "cutoff; start_date = end_date - day_count days is the prior "
            "issue's cutoff (so a normal issue covers the 7 days from "
            "start_date+1 through end_date). Returns {error: ...} when Jamie "
            "hasn't set a window yet. Use when Jamie says 'the current "
            "issue', 'this weekend's issue', or 'the one I'm working on'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "issue__list_windows": {
        "name": "issue__list_windows",
        "description": (
            "List recent issue windows (newest issue number first). Same "
            "shape as issue__current_window plus an is_active flag. Use to "
            "answer 'when did issue #N ship?' or 'what content window did "
            "the last double issue cover?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "default 12"},
            },
        },
    },
    "currently__list_types": {
        "name": "currently__list_types",
        "description": (
            "The pool of canonical Currently labels — what types a Currently "
            "entry can hang off of (Listening, Watching, Installing, …). Use "
            "before `currently__set` to confirm a label exists; if it doesn't, "
            "call `currently__add_type` first. Each row carries "
            "`last_used_issue` so you can see which types are fresh vs cold. "
            "Active-only by default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include retired types. Default false.",
                },
            },
        },
    },
    "currently__list_entries": {
        "name": "currently__list_entries",
        "description": (
            "The filled Currently entries for an issue, in render order. "
            "Defaults to the active in-flight issue. Returns {issue_number, "
            "count, entries:[{label, value, position, updated_at}]}. Empty "
            "list = nothing's set yet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "Optional. Defaults to the in-flight issue.",
                },
            },
        },
    },
    "currently__set": {
        "name": "currently__set",
        "description": (
            "Set one Currently entry for the active in-flight issue. On INSERT "
            "the new entry appends with the next position (insertion order); "
            "on UPDATE the existing position is preserved. The value may "
            "contain markdown links — pass them through verbatim in Jamie's "
            "voice (don't paraphrase or summarise). If the `label` isn't a "
            "known canonical type, this errors — call `currently__add_type` "
            "first when Jamie mentions a brand-new type (e.g. 'Printing'). "
            "Refires `update-draft` so the preview reflects the change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Canonical type, e.g. 'Listening'. Case-insensitive match against currently_types.",
                },
                "value": {
                    "type": "string",
                    "description": "The Currently entry text. Markdown OK; preserve Jamie's voice.",
                },
            },
            "required": ["label", "value"],
        },
    },
    "currently__clear": {
        "name": "currently__clear",
        "description": (
            "Delete one Currently entry for the active in-flight issue. "
            "Remaining entries renumber contiguously. Refires "
            "`update-draft`. Idempotent — clearing a missing entry returns "
            "{ok: true, deleted: false} without error."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
    },
    "currently__add_type": {
        "name": "currently__add_type",
        "description": (
            "Add a new canonical Currently type (e.g. 'Printing'). Idempotent "
            "for an exact match — duplicates (case-insensitive) are refused "
            "with a friendly error. Use when Jamie mentions a type not in "
            "`currently__list_types` yet, then call `currently__set` to fill "
            "the value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
    },
    "currently__reorder": {
        "name": "currently__reorder",
        "description": (
            "Reorder the active issue's Currently entries to the given "
            "permutation of filled labels — positions 1..N. Must be a STRICT "
            "permutation of every currently-filled label for the issue (a "
            "missing or extra label is refused). Use when an issue has 3+ "
            "entries and a particular sequence reads better — narrative "
            "grouping, strongest first, or a deliberate shuffle. Refires "
            "`update-draft`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Strict permutation of currently-filled labels.",
                },
            },
            "required": ["labels"],
        },
    },
    "currently__suggest_stale": {
        "name": "currently__suggest_stale",
        "description": (
            "Top-K active Currently types ordered by recency — never-used "
            "first, then least-recent. Each entry carries `gap_issues` "
            "(issues since last use; null for never-used). Use to pick a "
            "fresh type to ask Jamie about when opening the week's Currently "
            "conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "k": {"type": "integer", "description": "max picks, default 3"},
            },
        },
    },
    "draft__section_status": {
        "name": "draft__section_status",
        "description": (
            "Deterministic completeness report for the in-flight issue's "
            "draft.md: per-section item counts + 'present' flags for "
            "Notable / Briefly / Journal, presence of the standalone assets "
            "(intro.md, currently.md, haiku.md, cover.jpg, "
            "metadata.json, cta-*.md), word count, the list of what's still "
            "missing for ship, and a ship_ready flag. Read this rather than "
            "eyeballing the draft and counting headings yourself. Returns "
            "{error: ...} if no issue is in flight. No arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    "react__add": {
        "name": "react__add",
        "description": (
            "Add a single emoji reaction to the message you're currently "
            "responding to (mention, peer message, or team-round trigger). "
            "Posts under your persona's avatar — Eddy's react shows as Eddy. "
            "Especially useful in `#workshop`: when a peer's message lands "
            "but you wouldn't add anything in prose, drop a brief reaction "
            "and PASS instead of staying invisible. Use sparingly — one "
            "reaction per message, only when the emoji is your honest take. "
            "Picks should match your persona: Eddy 📝👀🤔, Linky 🔗📚⏩, "
            "Marky 📈🔥, Patty 🤝💚 — but anything fitting works. Returns "
            "{ok, emoji} on success, {error: …} if there's no message in "
            "context (heartbeat path) or Discord rejects the emoji."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "emoji": {
                    "type": "string",
                    "description": "Single Discord emoji (unicode, e.g. 👀). Custom guild emoji as <:name:id>.",
                },
            },
            "required": ["emoji"],
        },
    },
    "editorial__get_comment": {
        "name": "editorial__get_comment",
        "description": (
            "Fetch one editorial review comment by its handle "
            "(e.g. 'E349-N1', 'E349-X3'). Returns the comment body + "
            "scope + verdict, the anchored item (when item-scoped), "
            "and the replacement handle when this comment has been "
            "superseded by a later review. Use when Jamie asks "
            "about a specific handle ('tell me about E349-N1')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Editorial handle, e.g. 'E349-N1'. Case-insensitive.",
                },
            },
            "required": ["handle"],
        },
    },
    "editorial__list_open": {
        "name": "editorial__list_open",
        "description": (
            "List open (not-yet-superseded) editorial comments for an "
            "issue with their handles + short snippets. Defaults to "
            "the in-flight issue. Useful for 'what did you flag on "
            "this issue?' — follow up with editorial__get_comment(handle) "
            "for any entry you want the full body for."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "Optional. Defaults to in-flight issue.",
                },
            },
        },
    },
    "campaigns__list": {
        "name": "campaigns__list",
        "description": (
            "List campaigns from Marky's ad-placement ledger. Default "
            "returns every campaign — live and sunset — newest first. "
            "Each row carries id, name, ref, url, platform, status, "
            "started_at, actual_signups (the denormalised KPI), cost, "
            "copy, notes. Pair with campaigns__get for a single "
            "campaign + its latest metric, or campaigns__history for "
            "the trajectory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": (
                        "Optional filter: 'live' (currently polling), "
                        "'sunset' (historical). Omit for all."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows. Default 50, max 200.",
                },
            },
        },
    },
    "campaigns__get": {
        "name": "campaigns__get",
        "description": (
            "Read one campaign by name (e.g. 'DD388'). Returns the row "
            "plus the most recent metric snapshot under 'latest_metric'. "
            "For the full poll trajectory use campaigns__history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    "campaigns__history": {
        "name": "campaigns__history",
        "description": (
            "Recent campaign_metrics rows for one campaign, newest "
            "first. Use to read a placement's trajectory — when traffic "
            "landed, how it tapered. Default limit 30 days of polls; "
            "cap 365."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "description": "Max rows. Default 30, max 365.",
                },
            },
            "required": ["name"],
        },
    },
    "campaigns__set_actual_signups": {
        "name": "campaigns__set_actual_signups",
        "description": (
            "Write the campaign's current attribution-realised signups "
            "count (the KPI denormalised on the campaign row). The "
            "daily-metrics job updates this after each poll, so the "
            "routine flow doesn't need this tool. Use it for manual "
            "corrections — you read attribution yourself via "
            "buttondown__attribution_summary and the stored value is "
            "stale or missing — or for ad-hoc placements you're "
            "tracking outside daily-metrics. Returns the updated "
            "campaign row."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "signups": {
                    "type": "integer",
                    "description": "Current cumulative signups count (≥0).",
                },
            },
            "required": ["name", "signups"],
        },
    },
    "productions__list": {
        "name": "productions__list",
        "description": (
            "List newsletter issues. Optionally filter by status "
            "(active/done/archived)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_type": {"type": "string", "enum": ["newsletter"]},
                "status": {"type": "string", "enum": ["active", "done", "archived", "abandoned"]},
            },
            "required": [],
        },
    },
    "productions__get": {
        "name": "productions__get",
        "description": "Full detail for one newsletter issue by id (e.g. 'WT350').",
        "input_schema": {
            "type": "object",
            "properties": {"production_id": {"type": "string"}},
            "required": ["production_id"],
        },
    },
    "productions__create": {
        "name": "productions__create",
        "description": (
            "Retired. Newsletter issues are created in the Studio web UI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_type": {"type": "string", "enum": ["newsletter"]},
                "title": {"type": "string"},
                "due_at": {"type": "string", "description": "Optional target date (YYYY-MM-DD)."},
            },
            "required": ["production_type", "title"],
        },
    },
    "productions__set_phase": {
        "name": "productions__set_phase",
        "description": (
            "Move a newsletter issue to a phase in its vocabulary "
            "(planned/write/build/publish/share)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_id": {"type": "string"},
                "phase": {"type": "string"},
            },
            "required": ["production_id", "phase"],
        },
    },
    "production_content__read": {
        "name": "production_content__read",
        "description": (
            "Read an authored content block of a newsletter issue. Returns "
            "{found, text}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_id": {"type": "string"},
                "name": {"type": "string", "description": "Block name, e.g. 'body.md'."},
            },
            "required": ["production_id", "name"],
        },
    },
    "production_content__write": {
        "name": "production_content__write",
        "description": (
            "Write an authored content block of a production. IMPORTANT: Jamie "
            "writes his own prose — NEVER use this to draft his sentences. Use "
            "it for structure/outline scaffolds, notes, or metadata you've been "
            "asked to record, not to ghostwrite the piece."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_id": {"type": "string"},
                "name": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["production_id", "name", "body"],
        },
    },
    "production_content__list": {
        "name": "production_content__list",
        "description": "List the content block names present for a production.",
        "input_schema": {
            "type": "object",
            "properties": {"production_id": {"type": "string"}},
            "required": ["production_id"],
        },
    },
    "tasks__list": {
        "name": "tasks__list",
        "description": (
            "List the tasks on a production — the shared board. Each task has an "
            "owner (jamie or an agent) and a status. Optionally filter by status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_id": {"type": "string"},
                "status": {"type": "string", "enum": ["todo", "doing", "done", "blocked"]},
            },
            "required": ["production_id"],
        },
    },
    "tasks__add": {
        "name": "tasks__add",
        "description": (
            "Add a task to an issue's board. Assign it to jamie or Eddy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "production_id": {"type": "string"},
                "title": {"type": "string"},
                "owner": {"type": "string", "enum": ["jamie", "eddy"]},
                "phase": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["production_id", "title"],
        },
    },
    "tasks__update": {
        "name": "tasks__update",
        "description": (
            "Update a task — claim it (set owner to yourself + status 'doing'), "
            "reassign, retitle, or change status (todo/doing/done/blocked)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["todo", "doing", "done", "blocked"]},
                "owner": {"type": "string", "enum": ["jamie", "eddy"]},
                "title": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    "tasks__complete": {
        "name": "tasks__complete",
        "description": "Mark a task done.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
}
