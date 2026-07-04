# Atom editor — build 1 plan

Implements step 1 of the migration seams in [`issue-atoms.md`](issue-atoms.md):
**read-side atom projection + web issue editor skeleton.** No new atoms table,
no store migration, publish path byte-identical by default.

## Scope

One new page — `/productions/{WTn}/editor` — that shows the in-flight issue as
**one ordered list of atoms** and supports the first four interactions:

1. **Edit in place** — authored atoms only (intro/outro/haiku/CTA/…, via the
   existing `content_store`). Pin/blog-derived atoms are **read-only bodies**
   in build 1 (the two-way Pinboard mirror is step 3; until then Pinboard is
   authoritative, and an edit here would be silently overwritten by the next
   sync — the UI says "edit in Pinboard" and links the pin).
2. **Promote / demote** — briefly ↔ notable as a one-tap kind flip.
3. **Select / deselect** — any derived atom (the Journal filter).
4. **Reorder** — up/down within a section (JS-free buttons, same pattern as
   the rest of the webapp).

## The editor-vs-sync ownership rule (the key design point)

`issue_items_sync` runs inside daily `update-draft` and **refreshes
section/title/body/metadata on UPSERT** — so a naive section flip would be
reverted within a day. Fix: split column ownership.

- **Sync owns:** `section`, `title`, `body_md`, `metadata_json` (upstream
  truth, keeps mirroring).
- **Editor owns (new columns, sync never writes them):**
  - `section_override TEXT` — render reads `COALESCE(section_override,
    section)`. Promote = set override; undo = clear it. The Pinboard `_brief`
    tag stays an *input signal*, the editor's word wins — exactly the
    Featured-category precedent (signal seeds, editor overrides).
  - `excluded INTEGER NOT NULL DEFAULT 0` — render skips excluded rows.
    Deselect is reversible and survives sync (sync prunes only rows whose
    upstream item disappeared; an excluded row with a live pin stays).

Migration: one additive `ALTER TABLE issue_items ADD COLUMN …` pair
(`_m_00xx`), no data rewrite.

## Pieces

| Piece | Where | ~Size |
|---|---|---|
| Projection `atoms_view.build(issue_number)` — assembles the ordered atom list from `production_content` (intro/outro/echoes/closer…), `currently_entries`, cover.json, and `issue_items`; each atom carries kind, store-key, title, body, provenance (pin URL), editable/selected flags | `tools/content/atoms_view.py` (new) | ~150 loc |
| Editor route + POST handlers (atom body save → content_store; flip → section_override; select → excluded; move → position swap) | `webapp/routes.py` | ~120 loc |
| Editor template — atoms in reading order, per-kind affordances | `webapp/templates/editor.html` (new) | ~150 loc |
| Render awareness — `issue_items_render` reads the two new columns (one COALESCE, one WHERE) | `tools/issue_items_render.py` | ~10 loc |
| Sync guard — assert UPSERT column list stays disjoint from editor-owned columns (test, not code, if already disjoint) | `tools/issue_items_sync.py` + test | ~10 loc |
| Link from the newsletter production page ("open editor") — existing page untouched otherwise | `production.html` | 1 line |

## Verification (publish path safety)

- **Byte-diff gate:** render WT349's archive/buttondown/transcript artifacts
  before and after the change with no overrides/exclusions set — must be
  byte-identical (the new columns default to no-op).
- Unit tests: projection shape per kind; override/exclude round-trips
  surviving a simulated sync pass; render with/without override + exclusion;
  editor routes (auth, CSRF, 404s) following `test_webapp_productions.py`
  patterns.
- The editor is a *new* URL; nothing existing changes behavior until an
  override/exclusion is actually set. Rollback = don't use the page.

## Non-goals (build 1)

New `atoms` table · currently/`production_content` migration · Pinboard
write-back · derived-body editing · drag-and-drop · thesis retirement ·
envelope batching · photo-promotion flow · podcast cue view. Each lands in
later steps per the seams; the projection is written so swapping its reads to
a real atoms table later changes `atoms_view.py` only.

## Sequence

1. Migration + render/sync column split (+ byte-diff gate green)
2. Projection module + tests
3. Editor page + handlers + tests
4. Full suite + lint; restart workshop_bot; hands-on pass on the live WT350
   (needs an in-flight issue to be meaningful)
