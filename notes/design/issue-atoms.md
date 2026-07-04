# How a Weekly Thing is created — the atom model

Rethinking how an issue of the Weekly Thing is assembled. Design brief —
Jamie's concept notes ("How a Weekly Thing is created") turned into an
implementable shape through Q&A with Jamie (2026-07-04).
**Status: design settled (see Decision log at the end); build not started.**

## The idea

An issue has always had clear sections, and each section has been a block of
markdown. The rethink: **each *item* in each section is a content atom** — an
independently-addressable object that renders to a markdown block. An issue is
then just an ordered set of atoms tagged `WT350`.

An atom may be an original idea of Jamie's, or derive from an external input
(a Pinboard bookmark, a blog post). Either way it has an id, a kind, a body,
and — when derived — a live connection back to its source.

## Why this isn't as scary as it looks

Most of this model already shipped in the June rearchitecture, just in three
different shapes:

| Concept | Where it lives today |
|---|---|
| notable / briefly / journal items as rows | `issue_items` (synced from Pinboard / micro.blog) |
| currently entries | `currently_types` + `currently_entries` tables |
| intro / outro / haiku / CTA | `production_content` atoms |
| article from multiple pins | seeds → cluster → graduate |

The rethink is a **unification**, not a rebuild: one atom vocabulary over what
is now three stores. The renderers are already pure functions over structured
input — that's the seam that makes incremental migration safe.

**The Currently lesson (Jamie):** `currently_types`/`currently_entries` was
over-built — a whole two-table system for what the atom model expresses as *a
kind of atom with a selectable label and a short string of markdown*. That's
the general principle for the whole design: kinds carry small structured
fields; the system stays one table of atoms, not a table per section.

## The atom

```
atom:
  id            stable id (per-atom, not per-issue)
  kind          intro | currently | photo | notable | journal | briefly |
                outro | echoes | closer | …
  issue         WT-number tag (nullable — an atom can exist before it has an issue)
  position      order within its kind/section
  body          markdown (the rendered block, or the source of it)
  fields        small per-kind structured extras (see below)
  source        provenance: pinboard:{id} | blog:{url} | original | generated
  state         in | out (selected for the issue or filtered out) — see Selection
  created / updated / by
```

### Kinds and cardinality (per issue)

```
intro     1..n   pure markdown
currently 0..n   label (selectable from the label pool) + one line of markdown
photo     1      image + caption + location (+ timestamp, alt) — today's cover.json
                 fields, likely *promoted from a journal atom* (see Promotion)
notable   1..n   pin-derived; markdown mirrors the Pinboard description
journal   1..n   blog-derived; carries photos routinely (WT348 shipped 18
                 images, WT349 12 — rehosted as native <img> tags)
briefly   1..n   pin-derived; markdown mirrors the Pinboard description
outro     0..n   pure markdown
echoes    1      its own atom, full stop — Thingy's archive note is first-class
closer    1      a *templated micro-atom*: template text + a haiku placeholder —
                 structurally like a currently atom (label/template + short
                 generated content). The template prose itself is a candidate
                 for Thingy authorship later.
```

**Not in the model: thesis.** Jamie: thesis existed before the shape of the
issue was known — retire it. The envelope calls (subject, description, haiku)
instead read **the in-flight draft, assembled on demand from the atoms** —
and are requested in **one batched LLM call**, so all envelope pieces share
one context. That shared context is the consistency thesis was providing the
hard way; the batch gives it for free.

**Intro/outro `1..n` semantics:** ordered atoms, concatenated into the issue.
n > 1 is rare but load-bearing — the real value is **ahead-drafting**: a
special intro atom ("Welcome to WT400!") written weeks early and tagged to a
future issue. This is the "atom exists before its issue" property doing work.

## Key decisions (Jamie, 2026-07-04)

1. **Pinboard stays the link archive — two-way mirror, last edit wins.**
   We are not building a link archiver. A pin-derived atom's description
   mirrors its Pinboard bookmark *as long as the pin exists*, in both
   directions: edit the pin → the atom updates; edit the atom in the studio →
   the change writes back to the pin. Jamie is the only editor ("I can only
   do one thing at a time"), so last-write-wins is safe absent a system bug.
   This keeps the Pinboard archive complete and authoritative for downstream
   uses like the annual book (which may itself become a studio production
   later — that decision is out of scope here).
2. **The web issue editor is the BIG change.** A responsive, web-based editor
   for the issue as a whole: atoms in reading order, edit in place, reorder,
   promote, select/deselect. This replaces the Discord-mediated reorder/edit
   round-trips.
3. **Selection replaces filtering logic.** Journal entries (and any derived
   atoms) carry an in/out state — filtering the Journal is just deselecting an
   atom in the editor. No special-case filter rules.
4. **Promotion is the universal verb.** The same one-tap mechanic covers:
   - briefly ↔ notable (kind flip)
   - journal → its own featured section (today: micro.blog `Featured` category)
   - journal → **photo of the issue** — Jamie leans toward the photo section
     being a *promotion of a journal atom that leads with a photo* rather than
     a standalone thing. The promoted atom keeps its journal provenance; the
     photo fields (caption/location) come along.

## Podcasts: same atoms, different render target

Jamie's draft note "pod — inside of sections" decoded: a podcast episode is
assembled as an **outline of timed segments**, and its final form is not a
script but a **recording cue surface** — a slideshow-like view on the studio
screen with segment cards, intended timings, and a timer, used as a cue while
recording. No prose to read aloud.

That generalizes the atom model cleanly: an atom renders to a
*surface-appropriate block* — markdown for the newsletter, a cue card for the
podcast. Podcast atom kinds (sketch): `segment` (title + talking points +
intended duration), `bumper`, `break`. The cue view is a later build, but the
atom table should not assume "renders to markdown."

## What the atom model buys

- **Item-level lifecycle.** An atom can be drafted before its issue exists,
  moved from WT350 to WT351 (retag), or deselected without deletion — the same
  pause/park control productions got, one level down.
- **Provenance as data.** pin → atom and blog → atom edges become queryable;
  "which pins fed this issue" and "is this pin already used" are lookups, not
  archaeology. The two-way mirror is a sync over these edges.
- **One editor.** The web issue page stops being a set of per-block forms and
  becomes one surface over one table.
- **Agent legibility.** Agents get one tool surface (`atoms__*`) instead of
  three; review/reorder/promote proposals become row operations with stable
  ids — same pattern that already works for `issue_items` reorder.

## Migration seams (no big bang)

The publish path must never break (a botched ship-path change can skip a
week). Sequence:

1. **Read-side first.** New `atoms` table + a projection that *reads* the
   three existing stores and presents the unified atom view in the web editor.
   Renderers untouched.
2. **Migrate one store at a time behind the renderers.** Start with
   `currently` (smallest, and the known over-build): fold
   `currently_types`/`currently_entries` into atoms (label pool becomes kind
   metadata; keep the stale-pick suggestion). Verify a full issue ships.
3. **Then `issue_items`** (notable/journal/briefly) — the sync jobs UPSERT
   into atoms instead; promotion becomes the universal verb (kind flip /
   section flag / photo-of-issue). Pinboard write-back lands here (the
   Pinboard API update call is the only new external write). Verify a full
   issue ships.
4. **Then `production_content`** for the newsletter's authored blocks
   (intro/outro/echoes/closer), retiring the per-block forms.
5. Each step: same pattern as the June pivot — `DROP TABLE IF EXISTS`
   convergence, renderer reads swapped one function at a time, full-issue
   render byte-diffed against the old path before cutover.

## Out of scope (for this brief)

- The podcast cue view build (the atom table just mustn't preclude it).
- Article bodies as atom sets — seeds → cluster → graduate covers article
  genesis; the writing itself stays a body.
- The annual book as a studio production.
- The temporal layer, or any Librarian/corpus impact — atoms change how an
  issue is *assembled*, not what ships or what the corpus sees.

## Journal → Featured

The micro.blog `Featured` category is an **auto-promotion signal** (decided
2026-07-04): sync seeds the promotion; the editor can undo it. Same universal
promotion verb, machine-initiated.

## Pinboard write-back — verified semantics (live-tested 2026-07-04)

Probed against the real API with a private throwaway bookmark:

| Question | Result |
|---|---|
| Re-`posts/add` an existing URL — original add **time**? | **Preserved**, even on sparse updates. Issue-window math is safe; repeated identical writes converge. |
| Omit fields (extended/tags/shared) on update? | **Wiped** — and `shared` resets to the account default (a sparse write-back would make a private pin public). |
| `replace=no` on an existing URL? | Safe no-op guard — `item already exists`, nothing mutated. |
| API reliability | Random 500s observed mid-sequence — the mirror job needs retry + backoff on 5xx. |

So the write-back is a **read-modify-write**: `posts/get` → change one field →
`posts/add` with *every* field echoed back + `replace=yes`. Deterministic,
idempotent, two calls per edit. Field mapping note: Pinboard `description` =
the bookmark *title*; the notable/briefly body text mirrors Pinboard's
`extended` field.

**Pin deleted upstream → the atom is removed from Studio** (decided
2026-07-04). The mirror includes deletion; Pinboard is the archive of record
for links. Two consequences worth noting in the build:
- "Don't want it in the issue" is a *deselect* (state=out); "gone from the
  archive" is a Pinboard delete. Two different verbs, no ambiguity.
- Deletion only touches working state. A shipped issue's rendered artifacts
  in `data/issues/` are already frozen — upstream deletes never rewrite
  history.

## Decision log

All settled 2026-07-04 unless noted:

1. Atoms unify the three stores; kinds carry small fields (the Currently lesson).
2. Pinboard stays the link archive — two-way mirror, last edit wins, RMW
   write-back, upstream delete removes the atom.
3. Web issue editor is the centerpiece; selection replaces filtering.
4. Promotion is the universal verb (briefly ↔ notable, journal → featured
   [auto via micro.blog `Featured`, editor can undo], journal → photo).
5. Echoes is a first-class atom; closer is a templated micro-atom.
6. Thesis retired; envelope composed in one batched LLM call over the
   on-demand-assembled draft.
7. Intro/outro: ordered, concatenated, ahead-draftable.
8. Podcasts assemble as timed outline segments rendering to a recording cue
   surface (view itself parked).

**Status: design settled. Next: a build-planning pass for step 1 of the
migration seams (read-side atom projection + web issue editor skeleton).**
