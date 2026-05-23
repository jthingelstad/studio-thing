# Publishing workflow — wizard planning brief

Captured from the WT349 ship night (2026-05-22 / 23). This is the source material for the design session: what happened, what hurt, what we discussed as a remediation, and the decisions left open.

Treat the actual `apps/workshop_bot/CLAUDE.md` + `docs/workshop-content-loop-design-brief.md` as the architectural ground truth; this doc is *operator experience* notes layered on top.

---

## 1. Context

**WT349 — "Owning the Rails"** was the first full ship through the new per-channel content pipeline (each format — buttondown.md / archive.md / transcript blocks / audio MP3 — composes directly from structured input rather than from a shared intermediate body).

Architecture as it stands (post-tonight):

- **`data/issues/{N}/archive.md`** is editorial truth. Workshop bot's `/eddy issue publish website` commits it to `main` via the GitHub Git Data API.
- **Atoms live in `s3://files.thingelstad.com/weekly-thing/{N}/atoms/`** — `intro.md`, `outro.md`, `cover.json`, `haiku.md`, `metadata.json`, `thesis.md`, `cta-1.md`, `cta-2.md`, `thanks-1.md`, `closer.md`.
- **Daily-rendered artifacts** at the issue root: `draft.md`, `draft.html`, `archive.md`, `links.json`, `buttondown.md`, `buttondown.html`, `transcript-full.txt`, `transcript/NNN-{slug}.txt`.
- **`update-draft`** rebuilds `draft.md` from the template + fires the three sibling renderers (`render_archive_for_issue`, `render_email_for_issue`, `render_transcript_for_issue`) so all four artifacts stay current every cron tick.

**Architectural verdict from Jamie:** the per-channel rendering is *good*. The flexibility for each format to render unique aspects (transcript "There are N links" anchor, email-only CTA Liquid, archive-only YAML front matter) is a feature. The pain is *operator UX*, not architecture.

---

## 2. What actually happened tonight — chronological

The week's content authoring (intro, journal, notable, briefly, outro, cover) was already in good shape before this session. What follows is everything after that point — the publishing run + the issues we hit.

### 2a. Editorial fixes (caught by Eddy's review drawer)

- Double-space before "slight improvements" in intro paragraph 2 → fixed in intro.md
- `**no close friends**` bolding mid-paragraph in the adult-friendship blurb → fixed
- Two journal alt-text issues — `s'more` apostrophe truncating the rendered alt, and the broader "we keep generating alts but Jamie's blog never sees them" gap

### 2b. Bugs encountered + fixed

These are *all closed* now. The next session shouldn't relitigate them.

| Symptom | Root cause | Fix |
|---|---|---|
| `_prune_stale` failing with `FOREIGN KEY constraint failed` on every update-draft | `editorial_comments.item_id` FK had no `ON DELETE` action; deletes of stale `issue_items` blocked when a draft-review comment anchored to them | `96a65c6` — `_prune_stale` nulls the FK before delete |
| Alt regex `["\']([^"\']*)["\']` truncating at apostrophes (`s'more` → `Hand holding a s`) | Character class treats both quote styles as opener AND closer | `8797ba6` — quote-aware back-reference `(["\'])(.*?)\1` |
| `render-audio` TypeError on `ensure_bumpers()` | Wrapper passed no args; `pipeline/audio/bumpers.py:ensure_bumpers(manifest, force=False)` requires the manifest | `d15e539` — read manifest first, thread through |
| `publish_buttondown` "No metadata.json for #349" even with subject set | `pipeline/content/content.py:_workspace_get_text` hardcoded `weekly-thing/{N}/{filename}`; workshop_bot writes atoms under `atoms/{filename}` | `09795ff` — local atom-aware key resolver with dual-read fallback |
| Buttondown `buttondown.md` showing stale CTA after edit | `s3.write_issue_file` didn't trigger CloudFront invalidation; `.md` files served from edge cache hours after the bot rewrote them | `ec6c58b` — `write_issue_file` invalidates the path it just wrote |
| `update-draft` asyncio loop blocked 30-60s during TTS, faulthandler dumped "raise SystemExit(main())" stacks repeatedly | `audio_mod.build_issue` ran on the event loop synchronously | `8e145b5` — wrapped in `asyncio.to_thread` |
| Eddy's draft-review comments going stale (referenced fixes that were already in) | `_store_review_comments` only superseded prior open comments when the new pass wrote *new* anchored comments. A PASS verdict left old guidance open. | `818bd3a` — `editorial_comments.closed_at`; `_draft_review` closes prior open comments on PASS |
| `/eddy edit intro` failing when intro.md didn't exist yet | Discord rejects `TextInput(default="", required=False)` combo silently | `be4454b` — pass `default=None` for missing files; placeholder hint per asset |
| CTA still showing two Stripe payment buttons; thanks block double `<hr/>` for non-premium | `supporter_block` two-button table; trailer-divider auto-emitted by `_section_part` even when conditional renders empty | `d3c234e` → `7bd5c02` → `18dfe9c` — single "Become a Supporting Member" button to `/members/`; trailer divider moved inside the Liquid conditional |
| Audio progress card stuck on "starting…" through the 3-minute render | `_print_intercept` not landing the hook on the synthesize module; still investigating, instrumented in `29a54c7` | (open — see §6) |

### 2c. The actual command sequence Jamie ran (roughly)

After the bugs above were fixed mid-session:

1. `/eddy issue update` — rebuilds draft.md and the three sibling artifacts. Implicit refire from various other operations too.
2. Eddy posts the draft-review card; Jamie reads, makes fixes upstream (intro.md edits via Drafts → Shortcut).
3. `/eddy edit cta-1`, `/eddy edit cta-2`, `/eddy edit thanks-1` — first-time CTA authoring. Used the modal flow.
4. `/eddy issue publish audio` — hit the `ensure_bumpers` TypeError, then the asyncio blocking issue. Audio actually rendered successfully (the "appeared to die" was misleading visible-Discord silence).
5. `/eddy issue publish buttondown` — failed with "No metadata.json"; turned out metadata.json was set but in `atoms/`. Fixed, ran again, succeeded. Buttondown draft created at `em_1mp1fy5aar9yp97xdpma9dhk0w`.
6. `/eddy issue publish website` — committed `bdd6baa` "Ship WT349 — WT349 — Owning the Rails" to `main` with 17 files. GitHub Actions deploy run `26322158802` finished `success` 3m02s. Site live at `https://weekly.thingelstad.com/archive/349/`.

The whole sequence (commands + waits + bug fixes) took multiple hours and many context switches between Discord and this Claude session.

### 2d. Things Jamie *also* needed to remember to do

- Generate haiku via `/eddy issue haiku` (interactive option pick)
- Generate subject + description via `/eddy issue subject` (interactive option pick; produces `metadata.json.subject` + `metadata.json.description`)
- The reorder pass via `/eddy issue reorder` (Eddy proposes Notable/Brief ordering)
- All three CTA atoms (`cta-1`, `cta-2`, `thanks-1`) — Patty's `/patty cta` handles all three but individual edits go via `/eddy edit cta-N`

There is no single surface that says "these are the things you still need to do."

---

## 3. The friction — concentrated in three places

### 3a. Metadata is doing too much under one name

`/eddy issue subject` is misleadingly named. It produces:

- `metadata.json.subject` — the email subject line, Jamie picks from 5 LLM-generated options
- `metadata.json.description` — the comma-separated topic line, LLM generates a single answer
- … and `metadata.json` already carries deterministic fields filled at `start-issue` time: `number`, `slug`, `image`, `publish_date`
- … plus stamped-by-publish fields: `buttondown_id`, `absolute_url`

You have to know all that to debug "where did the description come from?" or "what's still missing?" There's no operator-visible distinction between author-input / derived / stamped fields.

### 3b. Pre-ship requirements are only checked at publish time

`publish_buttondown` has `REQUIRED_FOR_BUTTONDOWN = ("haiku.md", "metadata.json", "intro.md", "cover.jpg")` and refuses with a missing-list message. But:

- The check fires at publish click, not at issue-state-glance time
- `/eddy issue status` is read-only and out of the flow — you have to remember to run it
- The status report doesn't single-out "you're 4 of 5 ready and here's the missing one"

### 3c. The compose-* surface is undifferentiated

`/eddy issue` has eight verbs (`start`, `update`, `status`, `reorder`, `haiku`, `subject`, `publish`, `put-to-bed`, plus `reset`). Each is memorable individually but the *ordering* lives only in this document and in `docs/workshop-content-loop-design-brief.md`. There's no path-through-them surfaced in Discord. Jamie said: "It was really arcane after the links were in and blog post done."

---

## 4. The wizard idea (Jamie's proposal, refined in tonight's conversation)

**Core idea:** `/eddy issue ship` posts a persistent checklist card to `#editorial` and walks Jamie through every authored decision in order. The card edits in place as he advances; each row has buttons / reactions for the operator's gestures.

Mock:

```
🚀  Ship checklist — WT349 — "Owning the Rails"
    Draft: ✅ 2 626 words · 8 notable · 6 brief · 7 journal · last refresh 22:14

    1. ✅  Draft reads clean         [view ↗] [refresh]
    2. ✅  Reorder pass              [view ↗] [re-roll]
    3. ✅  Subject                   "WT349 — Owning the Rails"   [change]
    4. ✅  Description               "Internet of AI, Flipcash…"  [change]
    5. ✅  Haiku                     [view ↗] [re-roll]
    6. ✅  Cover                     caption + alt set            [edit]
    7. ⚠️  Currently                 4 entries, 1 type stale      [edit]
    8. ✅  CTAs                      cta-1, cta-2, thanks-1       [edit]
    9. ✅  Closer                    "From the archive: WT287…"   [view] [re-roll]

   📨  Audio:        ☐ not rendered
   📨  Buttondown:   ☐ no draft
   📨  Website:      ☐ not committed

   When everything ✅:  🚀 Ship all     (or 🚀 audio  🚀 buttondown  🚀 website)
```

Mechanics:

- **One state-of-the-issue card.** Replaces the run-command-see-ack-run-next loop with a single canvas. State derived from DB + atom presence (no separate wizard state to persist).
- **Each row is the existing compose-* job under the hood.** Wizard sequences them with the right prompts. `subject` and `description` get split visually so it's obvious they're two distinct decisions even though one `compose-meta` produces both.
- **Pre-flight checks inline, always-visible.** Required-atoms check moves from "fires at publish time" to "shown on the card now." Currently-entry staleness shows up as ⚠️ without needing to remember to check.
- **Ship buttons gated.** Can't click 🚀 Ship all until every author step is ✅. Per-destination buttons gate on their own subsets:
  - audio: needs transcripts (always exist by then)
  - buttondown: needs subject + description + haiku + cover + intro
  - website: needs buttondown to have run (so absolute_url is stamped)
- **Re-runnable, resumable.** Close Discord, come back tomorrow, `/eddy issue ship` posts the latest state.
- **Existing commands still callable** for power-use / debugging. The wizard is the well-paved happy path; the granular `/eddy issue subject` etc. stay as escape hatches.

---

## 5. Open design decisions (decide in tomorrow's session)

1. **One ship card per issue, or a fresh card per ship attempt?** Default to *one persistent card* that lives through the cycle and gets new entries appended as ships repeat (Buttondown PATCH, website re-commit). Reads as a runbook.
2. **Buttons vs reactions.** Discord buttons are cleaner UX but tied to message TTL — they expire. Reactions are more durable but less obvious. Lean buttons for "next" / "re-roll" and reactions for ✅/❌/🔄 (matching existing `await_choice`).
3. **Auto-advance or manual?** When step 3 finishes, auto-prompt step 4, or mark 3 ✅ and wait? Instinct: manual — might want to edit something between steps without committing yet.
4. **Where does `put-to-bed` fit?** Today it's a separate step after Buttondown sends. Could be row 10 of the ship card, marked ☐ until you confirm the send happened in Buttondown's UI, then ✅ via a button. Or folded into "Ship website" since by that point the issue is committed.
5. **How aggressive about renaming commands?** Keep `/eddy issue subject` etc. as-is (callable individually) but introduce `/eddy issue ship` as the new front door. Or rename internals for clarity (`compose-meta` → `compose-subject-description`, `create-final` → `compose-reorder`). Instinct: leave internals, add the wizard as the surface.
6. **Does the wizard replace `/eddy issue publish`?** Or run alongside? Cleanest if `/eddy issue ship` becomes the front door and `/eddy issue publish` stays as the lower-level escape hatch (e.g., for re-ships after a metadata correction).
7. **What about `start-issue`?** Today `/eddy issue start <N> <pub_date>` is the entry to the cycle. The wizard could front that too — `/eddy issue start <N> <pub_date>` posts the ship card right away with rows 1-9 all ☐, then naturally walks through them as Jamie writes the issue over the week. The card grows ✅s as content lands.

---

## 6. Things still in flight from tonight

These are *not* fully resolved and the next session should be aware:

- **Audio progress card stuck on "starting…"** Instrumentation added in `29a54c7` (logs which modules got patched + every classified progress event). Next render-audio run will tell us whether it's a patch-install miss, a classify miss, or a relay miss. Worth fixing because the wizard's per-destination ship-progress display will hit the same plumbing.
- **`#editorial` review-drawer staleness for `E349-I7` / `E349-N12`** — I manually `closed_at`-stamped those in SQLite as a one-time fix. The PASS-closure mechanism (`818bd3a`) is in for future passes. Eddy's hallucination on rebuilt-but-not-actually-changed text is a separate model-behavior issue worth its own thinking.
- **The CTA URL `/members/`** assumes the page exists; the site has `/members/` but it's a stable URL. No regression here, just noting the ship CTAs now point at it.

---

## 7. Current command surface (reference for the next session)

`/eddy issue` verbs (from `apps/workshop_bot/personas/commands/eddy.py`):

| Command | Purpose | Produces |
|---|---|---|
| `start <N> <pub_date> [days]` | Begin assembly; sets `issue_windows` + writes `workshop.json` pointer | `metadata.json` skeleton (number, slug, image, publish_date), empty issue workspace |
| `update` | Re-project Pinboard + micro.blog + atoms → `draft.md`; fires the three sibling renderers (archive.md, buttondown.md, transcript/*) | The five daily-rendered artifacts |
| `status` | Read-only state report | Discord card with section counts + asset presence |
| `reorder` | Eddy proposes Notable/Brief order, ✅ applies | `issue_items.position` updated, `thesis.md` written |
| `haiku` | LLM generates haiku options, Jamie picks | `haiku.md` |
| `subject` | LLM generates 5 subject options + 1 description | `metadata.json.subject` + `metadata.json.description` |
| `publish` | Ship; takes destination=all/audio/buttondown/website | MP3 on S3, Buttondown draft (PATCH or POST), GitHub commit |
| `put-to-bed` | File the shipped issue into the `issues` table + close `is_active` window | DB rows; issue is no longer "in flight" |
| `reset <step>` | Drop previous-step artifacts | clears promotions, drops thesis.md (`reorder`) or drops buttondown.md (`publish`) |
| `edit <asset>` | Modal for atom files | intro.md / outro.md / haiku.md / cover.json / cta-N.md / thanks-N.md |

Other relevant verbs:

- `/patty cta` — Patty composes all three slot atoms (`cta-1`, `cta-2`, `thanks-1`) in one interactive run
- `/eddy currently {list,edit,set,clear,reorder,add-type,retire-type}` — DB-backed `## Currently` section editor; Eddy can also handle these conversationally
- `/eddy review <text>` — ad-hoc editorial review of pasted text (not in the ship flow)

Atom files (`atoms/` prefix in S3, per-issue):

| File | Who writes | Read by |
|---|---|---|
| `intro.md` | Jamie via Drafts → Shortcut | update-draft (intro block), audio script preamble |
| `outro.md` | Jamie via Drafts → Shortcut | update-draft (outro block), audio |
| `cover.json` | Jamie (Shortcut) — caption / location / timestamp. Optionally `alt` (post Phase 3 alt-text rework) | update-draft (cover block), archive/email |
| `cover.jpg` | Jamie (Shortcut) | rendered <img src> |
| `haiku.md` | `compose-haiku` | update-draft (haiku block), audio close |
| `metadata.json` | mix — start-issue, compose-meta, publish-buttondown | renderers (front matter, email subject), publish-website |
| `thesis.md` | `create-final` (the reorder job) | compose-meta, compose-haiku, compose-cta, compose-closer |
| `cta-1.md`, `cta-2.md` | `compose-cta` (Patty) or `/eddy edit cta-N` | renderers (email-only Liquid splice via supporter_block) |
| `thanks-1.md` | `compose-cta` (Patty) | renderers (email-only premium-only thanks_block) |
| `closer.md` | `compose-closer` (auto-fired after reorder ✅) | renderers (after haiku, before "discuss on Reddit") |

---

## 8. The session's git trail

Commits landed tonight in chronological order. Useful to walk if you want to see exactly what changed:

```
c330f99   (pre-session baseline)
96a65c6   issue_items_sync FK fix
d2a212e   microblog Micropub update support + dry-run scripts
6882a46   Phase 2: alt-fill at micro.blog read, drop journal alt cache
9b31cfd   Phase 3: cover alt to cover.json
444f1c7   Phase 4: backfill 27 cached journal alts to micro.blog
3d35485   Phase 5: drop image_alt_cache table
3d80a44   currently: write to DB only — don't refire update-draft
8797ba6   img alt/src regex: apostrophe-safe back-reference
01a0047   draft.html: Subject / Description + convenience links
be4454b   /eddy edit: blank modal works for missing files
818bd3a   editorial_comments.closed_at — clear stale guidance on PASS
df84eb7   audio transcript: "There are N links" anchor
d3c234e   CTA: route to /members/ not Stripe
7bd5c02   CTA: fix URL `?email=` key
ec6c58b   s3.write_issue_file: invalidate CloudFront
18dfe9c   CTA: drop elsif; move `---` inside conditional
d15e539   render-audio: pass manifest to ensure_bumpers
8e145b5   render-audio: build_issue on a worker thread
09795ff   buttondown publish: read metadata.json from atoms/
7268ca1   render-audio: live per-block progress card
bdd6baa   Ship WT349 — WT349 — Owning the Rails  (← the actual ship commit, from the bot)
29a54c7   render-audio: instrument progress hook + harden module lookup
eb61ac8   Thingy corpus: bring About + Membership + FAQ into embeddings
```

(There's also a `manual closed_at` on `E349-I7` / `E349-N12` rows in `workshop.db` — not a commit, just direct UPDATE.)

---

## 9. Suggested next-session opening

A fresh Claude Code session can pick this up cold. Suggested first message:

> Read `docs/publishing-workflow-wizard-plan.md`. We're designing a wizard-style ship flow for workshop_bot to replace the current "remember which of eight commands to run in which order" UX. Walk me through how you'd structure §4's checklist card and §5's open decisions. Don't write code yet — let's get the design tight first.
