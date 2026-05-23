# docs/ — project memory

`docs/` is the **canonical editorial spec for how The Weekly Thing works** — the north star. It
describes how things *should* work, in plain English, so the implementation has something to be
verified against. The human-facing index is [`README.md`](README.md).

## What this is (and isn't)

- **This is the spec, Jamie-authored.** Agents may *seed* or *consolidate* these docs from canonical
  sources (the persona prompts, the per-app CLAUDE.md, the renderers), but **Jamie owns the voice**
  — especially [`voice-and-style.md`](voice-and-style.md) and anything marked *"draft — refine in
  your voice."* Don't silently rewrite his editorial declarations; propose and let him decide.
- **Distinct from the per-app `CLAUDE.md`s** (e.g. `apps/workshop_bot/CLAUDE.md`): those are
  *runtime* memory — how the code is built and what to keep in mind editing it. `docs/` is the
  *editorial* model the code serves.
- **Distinct from [`../notes/`](../notes/README.md)** (point-in-time history, non-canonical) and
  [`../reference/`](../reference/README.md) (durable technical reference). When `notes/` conflicts
  with `docs/`, `docs/` wins.

## The discipline

- **Verify against this.** When building or changing a surface/job/persona, the test is *does it
  respect this model?* When `docs/` and the code disagree, that's a flag to resolve deliberately —
  either the doc is the target (change the code) or the doc is stale (update it). Don't let them
  drift silently.
- **Keep docs small.** One concern per file, ~1 screen each (≤~120 lines); scannable bullets/tables
  over prose; **link, don't duplicate** — each doc owns its slice and cross-links the rest. If a
  doc sprawls, split it (the `phases/` + `programs/` + `agents/` layout exists for this).

## Voice: two files, one canonical

[`voice-and-style.md`](voice-and-style.md) is the **canonical human voice declaration**. There's
also `pipeline/content/marketing-brief.md` — a **machine-maintained** file (read+rewritten by
`pipeline/content/refresh_marketing_copy.py`) that's the persistent context for the home-page
pull-quote generator. It lives with its script, not here, because it's pipeline state, not
editorial canon. Its Voice section should track `voice-and-style.md`; this doc wins on conflict.
