> **OBSOLETE (historical).** This brief describes the S3-workspace / draft.md / Shortcuts era. Superseded by the 2026-06 productions rearchitecture and the 2026-07 "DB is the draft" rip — see `apps/workshop_bot/CLAUDE.md` and `notes/design/issue-atoms.md` for current reality.

# Workshop Content Production Loop — Design Brief

> Redesign of how `apps/workshop_bot/` helps Jamie assemble each Weekly Thing issue. The runtime (personas, S3 workspace, Discord plumbing) is mature; this brief defines what work happens, who does it, and on what trigger.

> **This brief replaces an earlier draft.** The earlier version was over-agentified — too much of the workflow was modeled as agent skills, inboxes, and inter-agent handoffs. The actual work is mostly deterministic Python that runs on a schedule. This redesign reorganizes around **jobs** as the spine, with two narrow agents (Eddy, Linky) and two personas-as-job-voice (Patty, Marky). The old draft sits in git history.

---

## Context

Jamie has assembled every issue of *The Weekly Thing* since 2017 via an iOS Shortcuts pipeline that runs once on Sunday morning and produces a single rigid markdown artifact. The pipeline is one-way (no edits flow back to Pinboard or micro.blog), time-ordered (no narrative reordering), and solo (no agent collaboration).

The redesign replaces this with an **iterative, week-long workflow**: a `draft.md` is materialized at the start of the issue window, refreshed daily (and on demand) from source systems, reviewed by Eddy after each refresh, locked toward end-of-week, then enriched with a membership CTA and prepared for promotion. Linky operates in parallel as a Pinboard curator. Patty and Marky engage post-`final.md`.

---

## Guiding principles

1. **Jamie is the author. Agents are staff.** No agent writes prose in Jamie's voice that ships, except Patty — and Patty composes in *Thingy's* voice (the public-facing librarian persona), not Jamie's. Eddy reviews and proposes; Linky captures Jamie's verbatim replies into Pinboard; Marky drafts framings for Jamie to edit and post.

2. **Source systems remain canonical.** Pinboard owns bookmark blurbs. micro.blog owns journal markdown. `currently.md` and `intro.md` are static markdown files Jamie writes (manually, via Shortcuts, or however he prefers — that pipeline is out of scope here). The `draft.md` is a *rendering* of upstream truth, regenerable at any time. Edits that should persist flow back upstream (Linky writes Briefly blurbs to Pinboard's description field).

3. **Jobs are the spine.** Every workshop_bot action — pulling content into the draft, reordering for the final, composing CTAs, drafting promotion copy — is a job. Jobs are deterministic Python in `apps/workshop_bot/jobs/`. Some jobs make small encapsulated LLM calls (Haiku poem, description metadata, voice-shaped composition). The job is the unit of scheduling and on-demand execution. Slash commands fire jobs.

4. **Agents are narrow.** Two real-time Discord agents:
   - **Eddy** is invoked by jobs (`update-draft`, `create-final`). No heartbeat. Posts editorial assessments to `#editorial`.
   - **Linky** has his own cadence (`pinboard-scan` job, scheduled morning + evening). Operates entirely on Pinboard.
   Patty and Marky are **personas** — their `prompts/<name>/prompt.md` shapes the voice of their respective jobs, but they don't run as Discord clients with heartbeats or inboxes.

5. **Closed loops, no agent-to-agent handoffs.** Each lane is independent; Jamie is the integrator. State synchronizes through file presence in S3 (`draft.md` → `final.md` → `publish.md`) and slash commands Jamie fires. No `inbox__post` calls between agents; no payload-routing matrix.

6. **Storage discipline — two layers.** Issue content (text only via the `tools/s3.py` allowlist) lives in the public `files.thingelstad.com/weekly-thing/{N}/` bucket — that's what Eleventy and the iOS Shortcuts read. Everything else — agent operational state, Patty's goals, Marky's campaigns, Eddy's digests, job locks — lives in `workshop.db` (SQLite). No private S3 bucket. The boundary is "ships vs doesn't ship."

---

## Architecture overview

```
apps/workshop_bot/
├── jobs/                     ← deterministic Python, schedulable, /workshop triggerable
│   ├── _base.py              ← Job protocol + scheduler integration
│   ├── start_issue.py        ← bootstrap issue context
│   ├── update_draft.py       ← pull content into draft.md
│   ├── create_final.py       ← Eddy reorder review → final.md
│   ├── compose_haiku.py      ← generate haiku options → haiku.md
│   ├── compose_meta.py       ← generate subject + description → metadata.json
│   ├── compose_cta.py        ← Patty's CTAs → cta-{1,2}.md
│   ├── build_publish.py      ← assemble publish.md from final.md + assets
│   ├── pinboard_scan.py      ← Linky popular + toread + briefly-suggest
│   ├── promotion_prep.py     ← Marky Reddit + LinkedIn drafts
│   ├── daily_metrics.py      ← Marky daily report
│   ├── add_campaign.py       ← register an ad campaign
│   ├── campaign_report.py    ← campaign performance summary
│   └── issue_status.py       ← read-only state report
├── templates/
│   └── draft_starter.md      ← the issue template with section content blocks
├── personas/
│   ├── eddy.py               ← Discord client; called by jobs
│   ├── linky.py              ← Discord client; runs on heartbeat schedule
│   ├── patty.py              ← persona only (no client) — voice for compose_cta
│   └── marky.py              ← persona only (no client) — voice for promotion_prep, daily_metrics
├── prompts/
│   ├── shared/team.md        ← shared voice + identity (existing)
│   └── <persona>/prompt.md   ← per-persona voice
├── scheduler/
│   └── jobs.py               ← cron registrations: update_draft, pinboard_scan, daily_metrics, ship-detection
├── tools/                    ← system clients + helpers (existing)
└── data/workshop.db          ← operational state (existing)
```

**Storage at a glance — two layers, hard boundary:**

- `s3://files.thingelstad.com/weekly-thing/{N}/` — public, what ships. `draft.md`, `final.md`, `publish.md`, `currently.md`, `intro.md`, `haiku.md`, `metadata.json`, `cta-*.md`, plus binaries (`cover.jpg`, `journal/*.jpg`, `body-{N}.mp3`, `weekly-thing-{N}.mp3`) written by other pipelines. Workshop_bot writes only the text/JSON files.
- `apps/workshop_bot/data/workshop.db` — SQLite. Everything else: issue window, agent runs/outputs/notes, link candidates, Pinboard dedup state, Eddy's draft digests, job locks, Patty's goals, Marky's campaigns + metrics.

No private bucket. An earlier draft had `s3://weekly-thing-workshop/` for persona-private state — dropped during design review. SQLite is the right home for goals, campaigns, locks, digests; the public bucket is the right home for issue artifacts. Two layers, not three.

### Job execution model

Jobs run serialized per asset. The lock unit is the asset being written, not the issue: two jobs that touch the same file (e.g., two `update-draft` runs both writing `draft.md`) can't overlap; jobs that touch different assets can. The lock lives in a small SQLite table (`job_locks: asset, job, started_at, pid`). When a job starts:

1. Acquire the lock on each asset it intends to write.
2. If any lock is held by another running job, exit immediately with a Discord message identifying what's running.
3. Release the locks on completion (success or failure).

The model assumes jobs do their writes inside a single execution; long-running jobs that need to wait for Jamie's review (compose jobs, `create-final`) hold their locks for the duration of the interaction, which is what we want.

This is enough for the workflow as designed — Jamie is the only operator, jobs are rare, and races are pathological cases (auto-fire chain colliding with a manual re-fire). External edits to S3 files outside the system are out of scope; the design assumes Jamie views `draft.md` but doesn't edit it directly. Real authoring happens in upstream systems (Pinboard, micro.blog, Drafts → Shortcut for `intro.md` / `currently.md`).

### Dynamic context for prompts

Persona prompts get small **dynamic context blocks** injected at runtime — facts that change day-to-day or per-issue, computed by Python rather than left for the model to derive. The agent reads them, doesn't compute them.

Per-persona surface area:

| Persona | Dynamic context surfaced |
|---|---|
| **Eddy** | Today's date. Days to publish (`pub_date - today`). Current `draft.md` word count. Per-section item counts and blurb completeness. Cover image present (yes/no). Intro present (yes/no). |
| **Linky** | Today's date. Days to publish. Days into window. Toread queue depth + estimated read-length distribution. Items captured to Briefly so far this week. |
| **Patty** | Today's date. Days to next May 13 (Weekly Thing anniversary — issue #1 was 2017-05-13; used for pacing context, not as a goal anchor). Expected number of issues between today and the anniversary (Saturdays in range, minus Saturdays in July, Saturdays in August, Saturdays between Dec 15 and Jan 15 — those are no-publish weeks). **Current active goal** from the `goals` table (`{kind, target_value, started_at}`). **Current progress** toward that goal (live member count from Buttondown for `kind='members'`; live total raised from Stripe for `kind='dollars'`). **Recent goals** — last 2–3 achieved rows with their durations, so Patty can see the arc. Current nonprofit. |
| **Marky** | Today's date. Latest-published issue number + ship date + days since ship. Active campaigns with days running. |

**Implementation:** new `apps/workshop_bot/tools/context.py` module with named builders — `build_eddy_context()`, `build_linky_context()`, `build_patty_context()`, `build_marky_context()`. Each returns a dict that gets rendered into a `## Today` (or similar) section of the persona prompt. Job runs and heartbeats both call the builder before invoking the agent loop. Same mechanism the existing `format_issue_index` already uses for the archive directory — the dynamic context block sits in the system prompt as its own ephemeral cache slot, so the static persona prefix stays cached across calls.

The bigger principle: **don't ask the model to compute facts the runtime can compute deterministically.** Date math, word counts, queue depths — all Python. The model spends its budget on judgment.

---

## The slash command surface

All workshop_bot user-facing actions are jobs. One command shape:

```
/workshop job <name> [<args>]
```

| Job | Args | What it does |
|---|---|---|
| `start-issue` | `<number> <pub-date> <day-count>` | Records the issue window in workshop.db, creates the S3 folder, writes `draft.md` from `templates/draft_starter.md`, auto-fires `update-draft`. The only command that takes the issue number explicitly. |
| `update-draft` | — | Pure projection: pulls content from sources, fills template content blocks, writes `draft.md`. Idempotent. Auto-fires after `start-issue` and daily 5pm CT during the issue window. Eddy reviews on Tue–Fri (silent Sun/Mon). Manual re-fire any time before `final.md` exists. |
| `create-final` | — | Invokes Eddy's reorder review (interactive in `#editorial`), writes `final.md`, then auto-fires `compose-haiku` + `compose-meta` + `compose-cta` in parallel. When all three complete and required Jamie-authored assets (`intro.md`, cover image) are present, auto-fires `build-publish`. |
| `compose-haiku` | — | Generates 2–3 haiku options from the issue themes. Posts options to `#editorial` for Jamie to pick. Writes choice to `haiku.md` in the workspace. Required for ship. |
| `compose-meta` | — | Generates 2–3 subject + description option pairs. Posts to `#editorial` for Jamie to pick. Writes choice to `metadata.json` in the workspace. Required for ship. |
| `compose-cta` | — | Patty's CTA composition. Generates 1–2 framings per CTA slot (0–2 slots, Patty decides). Posts to `#supporters` for approval. Writes accepted CTAs to `cta-1.md` / `cta-2.md` in the workspace (each with `placement:` frontmatter). Optional for ship. |
| `build-publish` | — | Final assembly. Reads `final.md` + `haiku.md` + `metadata.json` + `cta-*.md` + `intro.md` + `currently.md`. Refuses if any required asset is missing — surfaces the missing list. Writes `publish.md` — the artifact the existing content pipeline pushes to Buttondown. |
| `promotion-prep` | — | Marky's Reddit (megathread + per-link) + LinkedIn drafts. Auto-fires when RSS polling detects the issue is live; manual re-fire. Posts to `#promotion`. |
| `pinboard-scan` | — | Linky's popular + toread + briefly-suggest pass. Auto-fires Mon–Fri 6:30a / 6:30p during the issue window. Manual re-fire. Posts to `#research`. |
| `daily-metrics` | — | Marky's daily website + subscriber + campaign report. Auto-fires daily 7pm CT. Manual re-fire. Default-PASS when nothing material moved. Posts to `#promotion`. |
| `add-campaign` | `<name> <ref> [<expected_signups>] [<expected_traffic>]` | Register a new ad campaign for Marky to track (e.g., a Dense Discovery placement). Inserts a row into the `campaigns` SQLite table. |
| `campaign-report` | — | Lists active campaigns + current performance vs expected. |
| `issue-status` | — | Read-only state report on the in-flight issue: required + optional asset presence, section completeness, queue depth, days to pub. |

**Implicit context:**
- Issue-bound jobs operate on whatever `start-issue` recorded last in workshop.db. No `<number>` argument needed.
- Marky's jobs derive their context from the RSS feed at `weekly.thingelstad.com` (the most recent published issue), independent of the in-flight issue.

**Hosted on Eddy's Discord application** (per existing convention from `/workshop next-issue`). Flat hyphenated naming inside the `job` subcommand group; no further nesting.

**Removed:** the existing `/workshop heartbeat <agent>` and `/workshop next-issue` commands. The former is replaced by running the relevant job directly (`pinboard-scan` for Linky; the others have no heartbeat). The latter is renamed to `start-issue`.

---

## The issue lifecycle

End-to-end flow for a single issue. T-7d through T+0 covers a normal week; trailing post-publish work continues into T+1d–T+3d.

```
T-7d (Sat)   /workshop job start-issue 458 2026-05-16 7
       → workshop.db: issue 458, pub 2026-05-16 (Sat), window 5/9–5/15
       → S3: weekly-thing/458/ created
       → draft.md written from template (all section blocks empty)
       → update-draft auto-fires (Eddy silent — Sat/Sun/Mon are no-review days)

T-6d → T-5d (Sun, Mon)   Quiet capture
       → Jamie tags Pinboard items (_brief or untagged=Notable)
       → Jamie writes microblog posts (auto-pulled at next harvest)
       → Linky scans Pinboard popular morning + evening, surfaces in #research
       → Linky tends toread, suggests Briefly candidates, captures Jamie's
         verbatim replies back to Pinboard (description + remove toread tag)
       → update-draft fires daily 5pm CT, draft.md grows; Eddy stays silent

T-4d (Tue) → T-1d (Fri)   Editorial cycle
       → update-draft fires daily 5pm CT
       → Eddy posts delta-aware review card to #editorial each evening
       → Jamie pushes intro.md / currently.md to the workspace via
         Drafts + Shortcut whenever he writes them
       → Late Friday: Jamie fires /workshop job create-final
       → Eddy proposes section reorderings (Notable narrative flow,
         Briefly thematic grouping, Journal cuts/elevations) in #editorial
       → Jamie accepts/modifies → final.md written
       → Auto-fires compose-haiku + compose-meta + compose-cta in parallel

T-1d (Fri)   Composition cycle (auto-chained)
       → compose-haiku posts 2–3 haiku options in #editorial
                       → Jamie picks → haiku.md written
       → compose-meta posts 2–3 subject + description options in #editorial
                       → Jamie picks → metadata.json written
       → compose-cta (Patty) posts 1–2 CTA framings per slot in #supporters
                       → Jamie picks → cta-1.md / cta-2.md written
       → When all three compose jobs complete AND intro.md + cover.jpg
         are present, build-publish auto-fires
       → build-publish reads final.md + all assets, writes publish.md
       → If anything required is missing, build-publish PASSes and posts
         the missing list to #editorial

T+0 (Sat)   Ship (existing pipeline)
       → Jamie pushes via existing pipeline/content/ (Buttondown create_draft)
         which reads publish.md
       → Jamie reviews in Buttondown UI, schedules send

T+0 weekend   RSS detection + Marky drafts
       → Marky polls weekly.thingelstad.com/feed.xml on weekends
       → On detecting issue 458: promotion-prep auto-fires
       → Reads publish.md from the workspace (same artifact other agents use)
       → Reddit megathread + per-link Reddit threads + LinkedIn share
         drafted, all posted to #promotion for Jamie to copy/edit/publish

T+1d → T+next   Marky monitors
       → daily-metrics fires 7pm CT
       → Reports notable shifts in subscribers / website traffic /
         active campaign performance, default-PASS otherwise

T+next (Sat)   /workshop job start-issue 459 ...
       → Cycle repeats. The previous issue stays accessible (S3 folders
         are immutable history; published archive shares the prefix).
```

---

## Job specifications

### `start-issue` (deterministic)

**Inputs:** `<number>`, `<pub-date>` (YYYY-MM-DD, must be a Saturday), `<day-count>` (positive integer, normally 7).

**Effects:**
1. Validate inputs (reuse `tools/issue.compute_window`).
2. Insert / replace row in workshop.db `issue_window` table.
3. Create `s3://files.thingelstad.com/weekly-thing/{N}/` if absent.
4. Read `apps/workshop_bot/templates/draft_starter.md`, write to S3 as `draft.md`.
5. Fire `update-draft` synchronously (so the first draft has real content).
6. Ack to invoker; Eddy posts the initial completeness card.

**The starter template** has named content blocks the `update-draft` job knows how to fill:

```markdown
<!-- block:intro -->
<!-- /block:intro -->

## Notable

<!-- block:notable -->
<!-- /block:notable -->

## Briefly

<!-- block:brief -->
<!-- /block:brief -->

## Journal

<!-- block:journal -->
<!-- /block:journal -->

## Currently

<!-- block:currently -->
<!-- /block:currently -->

## Haiku

<!-- block:haiku -->
<!-- /block:haiku -->
```

Each `<!-- block:X -->` marker delimits a section `update-draft` fills. `update-draft` doesn't *author* anything itself — it reads from upstream (Pinboard, micro.blog) or from standalone asset files (`intro.md`, `currently.md`, `haiku.md`) and pastes the content into the right block.

### `update-draft` (deterministic, pure projection)

**Inputs:** none (operates on the in-flight issue).

**Effects:** for each section block, runs a fill function that pulls from a source and renders into the block. `update-draft` is a **pure projection of upstream state** — re-run it and you get the same output (modulo upstream changes). No "additive merge," no special preserve-on-conflict logic. The block content is replaced wholesale each run. Real authoring lives upstream (Pinboard, micro.blog, Drafts → Shortcut for the static files).

| Block | Source | Function |
|---|---|---|
| intro | `intro.md` in the workspace (Jamie writes via Drafts + Shortcut) | `intro.fill(N)` — read file, paste contents into block; empty if absent |
| notable | Pinboard items in window with no `_brief` tag | `notable.fill(N)` |
| brief | Pinboard items in window with `_brief` tag (post-Linky-capture) | `brief.fill(N)` |
| journal | All micro.blog posts in window (no filtering) | `journal.fill(N)` |
| currently | `currently.md` in the workspace (Jamie writes via Drafts + Shortcut) | `currently.fill(N)` — read file, paste contents into block; empty if absent |
| haiku | `haiku.md` in the workspace (written by `compose-haiku`) | `haiku.fill(N)` — read file, paste contents into block; empty if absent |

**Tag conventions (single source of truth for what `update-draft` reads):**

- **Pinboard.** One tag: `_brief`. Untagged-in-window = Notable. `_brief` = Briefly. That's the whole convention. Earlier issues used a `_featured` tag for a separate Featured section; that section was retired, and the tag is no longer recognized.
- **micro.blog.** Pull everything in window. No tag filtering at harvest. Filtering and journal curation happen at `create-final` time (Eddy can cut entries).
- **Toread tag** (Pinboard built-in): used by Linky's `pinboard-scan` to find items awaiting blurbs; not used by `update-draft`.

**`intro.md`, `currently.md`, `haiku.md` are standalone assets**, each written by a different actor (Jamie via Shortcut for the first two, `compose-haiku` for the third). `update-draft` doesn't know or care who wrote them — it just reads and pastes. If a file is absent, the corresponding block is empty; Eddy's review surfaces the gap if it's a required-for-ship asset.

**After `final.md` exists**, `update-draft` refuses to run with a clear error: "issue is locked; delete `final.md` to unlock." Re-firing `update-draft` against a locked issue would silently produce a stale `draft.md` divergent from `final.md`; better to fail loudly.

After fills, writes `draft.md` back to S3, then invokes Eddy's review (unless today is Sun or Mon — see Eddy's review below).

### Eddy's review (after `update-draft` completes)

**When Eddy posts.** Tue–Fri only. On Sat/Sun/Mon, `update-draft` runs but Eddy stays silent — issues just shipped on Saturday, the prior week's send is still fresh in subscribers' inboxes, and the early-week draft has too little content to comment on usefully. The "you can stop checking #editorial until Tuesday" property is intentional. From Tuesday onward, Eddy posts one review card per `update-draft` run.

**Delta-aware context.** Each `update-draft` run also writes a small digest to workshop.db:

```sql
draft_digests(issue, ran_at, word_count, notable_count, brief_count, journal_count,
              intro_present, currently_present, haiku_present, cover_present, source_hash)
```

When Eddy runs, his dynamic context block reads the previous digest for this issue, computes the delta, and surfaces it. He doesn't summarize what was already in yesterday's card — he focuses on what changed.

**Review card shape:**

```
📋 WT{N} — draft refreshed  ·  Tue, {date}  ·  {n} days to pub

Since yesterday: +2 Notable, +1 Briefly, +380 words, intro now present

Required for ship:
  ✅ Notable / Brief / Journal (from update-draft)
  ❌ haiku.md       → run /workshop job compose-haiku
  ❌ metadata.json  → run /workshop job compose-meta
  ❌ intro.md       → write it, push via Shortcut
  ❌ cover.jpg

Optional:
  ✅ currently.md
  ⚪ CTAs (compose-cta not yet run)

Editorial observations:
  - {recurring thread building across sections}
  - {potential duplication / link reused}
  - {tone shift worth flagging}
  - {section weight feels off}
```

Editorial observations sharpen as content fills in. Early-week (Tue/Wed), the card is mostly the readiness checklist with light commentary. By Friday, it's mostly editorial. The model tier scales accordingly — Haiku for early-week skeleton checks, Sonnet or Opus for substantive end-of-week reviews.

**Required vs optional.** The checklist distinguishes "required for ship" (build-publish refuses without these) from "optional" (build-publish proceeds without). The classification:

| Asset | Status | Why |
|---|---|---|
| Notable + Brief + Journal sections | required | Core issue content |
| `haiku.md` | required | Every issue has one |
| `metadata.json` (subject + description) | required | Buttondown needs them |
| `intro.md` | required | Every issue has one (Jamie sometimes writes it post-lock; build-publish refuses without it) |
| `cover.jpg` | required | Every issue has one |
| `currently.md` | optional | Some issues skip it |
| `cta-*.md` | optional | Patty may decide 0 CTAs for this issue |

The completeness check itself is a deterministic computation Eddy reads from a helper (`draft__section_status` style). Eddy spends his model budget on the editorial observations, not on the checklist arithmetic.

**Editorial guards.** Beyond completeness, Eddy applies a set of guards each review and surfaces what he finds:

- **Word count guard.** 2000–3000 words is the comfortable range for an issue. Above 2500, gentle flag with one or two suggestions for cuts. Above 3000, firm pushback with concrete cut candidates (the longest Notable blurb, a Journal entry that feels thin, a Briefly that could go). Below 1500, note the issue is running short — not necessarily a problem, but worth knowing. Word count is computed from the draft and surfaced via dynamic context.
- **Section weight balance.** Notable / Briefly / Journal counts way out of usual ratio (e.g., 8 Notable to 2 Briefly) → flag as unusual.
- **Recurring-frame detection.** A frame from last week's issue showing up in this draft → flag with an `#NNN` archive citation. Drift toward repetition is the most common editorial failure mode worth catching early.
- **Item-length sanity.** A Notable blurb running multiple paragraphs is suspect — flag it for a possible cut or restructure. A Briefly item running long might want to be a Notable instead.
- **Cover image presence.** Cover photo missing within a few days of publish → flag.

Word count, item count, and cover presence are deterministic — Eddy reads them from `draft__section_status` and the dynamic context block. Frame repetition and item-length sanity are judgment work — Eddy spends his model budget here.

### `create-final` (Eddy reorder review)

Triggered by `/workshop job create-final`.

1. Read `draft.md`. Refuse if `final.md` already exists (delete it explicitly to re-run).
2. For each ordered section (Notable, Brief, Journal): Eddy proposes an ordering with a short rationale, posts in `#editorial`, waits for Jamie's accept/modify reaction.
3. Eddy may also propose:
   - Cutting a Journal entry that doesn't fit (this is where micro.blog's pull-everything posture gets filtered — content that's in `draft.md` but doesn't belong gets dropped here).
   - Surfacing a Journal entry as its own section if it warrants the weight (rare).
4. After all sections approved, write `final.md` to S3.
5. Auto-fire `compose-haiku`, `compose-meta`, `compose-cta` in parallel. Each runs its own review loop with Jamie. When all three complete *and* required Jamie-authored assets (`intro.md`, `cover.jpg`) are present, auto-fire `build-publish`.

### `compose-haiku`

**Trigger:** auto on `create-final` completion. Manual via `/workshop job compose-haiku`.

**Inputs:** `final.md` (for the issue themes). The published-archive corpus (for "haiku I've used before — don't repeat them"). Dynamic context block.

**Behavior:**
1. Read `final.md`. Identify the dominant themes / tensions / one-liners in the issue.
2. Generate 2–3 haiku options. Each option is a complete haiku block (5-7-5 syllable count or Jamie's looser conventions — observe past issues for the actual shape).
3. Post the options in `#editorial`:
   ```
   📜 Haiku options for WT458 — pick one or ask for more
   
   1. [haiku 1]
   2. [haiku 2]
   3. [haiku 3]
   ```
4. Jamie reacts with 1/2/3 (or asks for a refresh).
5. Write the chosen text to `haiku.md` in the workspace.

Re-fire any time before publish to get fresh options.

### `compose-meta`

**Trigger:** auto on `create-final` completion. Manual via `/workshop job compose-meta`.

**Inputs:** `final.md`. The last ~10 issues' subjects (from the archive — for "don't repeat the same words" — see `metadata.json` from past issues at `data/buttondown/emails/*.json`). Dynamic context block.

**Behavior:**
1. Read `final.md`. Identify the three most distinctive themes / items.
2. Generate 2–3 paired options of `(subject, description)`:
   - Subject convention: "Weekly Thing {N} / Three Words Title" — three comma-separated words, title case, distilling the issue.
   - Description: 1–2 sentences capturing the essence; reads well as a Buttondown preview snippet.
3. Post the options in `#editorial`:
   ```
   📰 Subject + description options for WT458

   1. "Weekly Thing 458 / Three Words Title"
      OpenAI Codex App, Cloudflare Email Service, ...
   2. "Weekly Thing 458 / Different Three Words"
      Different framing of the same content.
   3. ...
   ```
4. Jamie picks (or asks for a refresh).
5. Write the chosen pair to `metadata.json` in the workspace (subset of the existing `data/buttondown/emails/*.json` schema):

   ```json
   {
     "number": 458,
     "subject": "Weekly Thing 458 / Three Words Title",
     "description": "...",
     "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
     "slug": "458",
     "publish_date": "2026-05-16T12:00:00Z"
   }
   ```

   `image`, `slug`, `number`, `publish_date` are deterministic (known from `start-issue` + standard cover path). Only `subject` and `description` are generated.

### `compose-cta` (Patty)

**Trigger:** auto on `create-final` completion. Manual via `/workshop job compose-cta`.

**Inputs:**
- `final.md` (issue context).
- Recent supporting-member signups (Stripe + Buttondown premium count via existing tools).
- **Current goal** from the SQLite `goals` table (one active row at a time; see Storage architecture). Jamie maintains this — when a milestone hits, he marks `achieved_at` on the current row and inserts the next.
- **Arc continuity** — Patty reads the last 3–4 issues' `publish.md` files (which contain her previous CTAs verbatim) to ground the arc. No separate notes file needed.
- **Dynamic context block** (computed by `build_patty_context()` — not Patty's own arithmetic): today's date, days to next May 13 anniversary (pacing context only), expected number of issues remaining before the anniversary, current active goal + current progress, recent achieved goals + their durations, current nonprofit. See "Dynamic context for prompts" in Architecture overview.

**Persona prompt:** `prompts/patty/prompt.md` shapes Patty's voice. Patty composes in **Thingy's** voice — light "public voice" reference: not salesy, librarian-adjacent, the same persona readers see on the website and engage with directly. Patty herself is invisible to readers.

**Behavior:**
1. Decide on 0, 1, or 2 CTAs for this issue based on tone + arc.
2. For each CTA, draft 1–2 framings.
3. Post in `#supporters`:
   ```
   💝 Patty's CTA proposal for WT458 — {n} CTAs
   
   Slot 1 (after Notable):
     Option A: [framing A]
     Option B: [framing B]
   
   Slot 2 (after Briefly):
     Option A: [framing A]
   ```
4. Jamie picks per slot (or asks for a refresh).
5. Write each chosen CTA to `cta-1.md`, `cta-2.md` in the workspace, with YAML frontmatter encoding placement:

   ```markdown
   ---
   placement: after_brief
   ---
   
   [CTA copy]
   ```

   Placement values: `after_notable`, `after_brief`, `after_journal`, `before_haiku`. Never above intro. Second CTA's placement is fairly toward the end.

**Constraints:**
- Patty doesn't edit `final.md`. Her output is two standalone files.
- CTA length-capped (initial soft cap to be tuned after seeing real output).

### `build-publish`

**Trigger:** auto when all of `compose-haiku`, `compose-meta`, `compose-cta` have completed AND required Jamie-authored assets are present. Manual via `/workshop job build-publish`.

**Behavior:**
1. Check required assets: `final.md`, `haiku.md`, `metadata.json`, `intro.md`, `cover.jpg`. If any are missing, post the missing list to `#editorial` with the slash command(s) to run, and stop.
2. Read `final.md`. Inline:
   - `intro.md` at the top
   - `haiku.md` at the end (`<!-- block:haiku -->` marker)
   - `currently.md` if present (`<!-- block:currently -->` marker)
   - `cta-*.md` at their declared placements
3. Write `publish.md` to the workspace.
4. Ack in `#editorial`: "publish.md ready — push via the existing pipeline whenever you're ready."

`publish.md` is the artifact the existing `pipeline/content/` push reads. No fallback to `final.md` needed in the new design — if `publish.md` doesn't exist, the issue isn't ready to ship.

### `pinboard-scan` (Linky)

**Trigger:** scheduled Mon–Fri 6:30a CT and 6:30p CT during the issue window. Manual via slash command.

**Active condition:** issue window is set AND `now ∈ [start_date, end_date]` AND there's pending work (toread items exist OR popular feed has unseen items). Otherwise PASS — and "issue locked" produces the same behavior as "no toread items" (he just has nothing to do).

**Four lanes per scan:**

**Lane A — Pinboard popular review.** Closed loop, no Pinboard mutation.
- Pulls Pinboard's site-wide popular feed.
- Reads each candidate via `web__fetch_url` to actually understand it.
- Surfaces in `#research` with a 1–2 sentence "why this is interesting" rationale.
- Bar is **interesting to Jamie**, not "fits the Weekly Thing." Jamie decides what to bookmark.
- Hard rule: Linky never auto-adds anything to the toread queue.
- Dedupes against `pinboard_popular_seen`.
- Cap: 1 popular surface per scan.

**Lane B — toread queue tending.** Recurring per-item assessment.
- Reviews items in the toread queue with WT-aware framing: quality, deserves Jamie's time, how it might land in WT.
- Cap: 3–5 assessments per scan.

**Lane C — Briefly capture.** When Linky thinks a toread item belongs in Briefly:
- Posts in `#research` with the suggestion: "this could be a Briefly — one-liner? (your reply = the blurb verbatim)."
- Jamie's reply IS the blurb.
- Linky calls `pinboard__capture_blurb(url, jamie_reply)` — atomically writes description, tags `_brief`, removes `toread`.
- Item flows into the next `update-draft` run.

**Lane D — Read-length + queue-depth assistance.**
- Estimates read length per toread item: short / medium / long buckets (best-effort, skip when unfetchable).
- Watches `toread_count` against `pub_date - now`. Alerts in `#research` when end-of-week pile-up is trending.

**No inbox, no inter-agent handoffs.** Linky's loop is Pinboard ↔ `#research` ↔ Jamie. Closed.

**Pinboard tool surface (job-oriented, not 1:1 API mirror):**

| Tool | Purpose |
|---|---|
| `pinboard__issue_candidates(section?)` | Items belonging to the in-flight issue's window. `section` is `notable` (untagged) or `brief` (tagged `_brief`). No `_featured` — that section is retired. |
| `pinboard__capture_blurb(url, blurb)` | Atomic: writes description verbatim, tags `_brief`, removes `toread`. |
| `pinboard__popular_unseen(limit?)` | Popular feed deduped against `pinboard_popular_seen` and the avoid-domains list. |
| `pinboard__mark_seen(url)` | Records that Linky surfaced this URL. |
| `pinboard__estimate_read_length(url)` | Returns `short|medium|long` based on fetched content (or `unknown`). |
| `pinboard__queue_depth_vs_deadline()` | Returns toread count + days-to-pub + a trend signal. |
| `pinboard__archive_recall(query, k?)` | Convenience over Jamie's full Pinboard archive (not just the unread pile). |

The existing thin-API-mirror tools (`pinboard__recent`, `pinboard__unread`, `pinboard__lookup_url`, `pinboard__save`, etc.) stay available for ad-hoc use. The job-oriented verbs are what Linky's prompt reaches for first.

### `promotion-prep` (Marky)

**Trigger:** RSS update is the signal that "the issue is live, Marky can work on it." Once detected, `promotion-prep` auto-fires. Manual re-fire via slash command.

**Ship detection:** Marky polls `https://weekly.thingelstad.com/feed.xml` on weekends. When a new issue number appears, that's the trigger only — RSS isn't used as a source for the content itself.

**Operates on:** the most recent issue's `publish.md` in the workspace — same artifact every other agent uses. The RSS signal just tells Marky "the issue is live; you're allowed to start." She still reads from `s3://files.thingelstad.com/weekly-thing/{latest}/publish.md`.

**Inputs:**
- The previous issue's `publish.md` (the issue she's promoting).
- Recent past drafts and Jamie's edits in `#promotion` Discord history (voice calibration — built into Marky's context naturally from channel scrollback; no separate notes file).
- Per-platform conventions in Marky's prompt.

**Output to `#promotion`:**

For each platform, **2–3 alternative framings** rather than one definitive draft. Jamie picks the one closest to where he'd start, edits it, and posts. The first draft never locks the framing.

| Platform | Draft length | Notes |
|---|---|---|
| LinkedIn | 100–200 words | Professional tone. Jamie posts under his account. |
| r/WeeklyThing megathread | conversational, community tone | Master thread for the issue. |
| r/WeeklyThing per-link | 1–2 sentences + link | One per Notable item. Posted on a cadence. |

**Hard rule: never auto-posts.** All drafts staged in `#promotion` for Jamie to copy / edit / publish.

**Voice anxiety acknowledgment.** This is the highest-stakes voice work in the system — these posts go out under Jamie's name. Architecture supports it by:
- Multiple framings, not one (lower the stakes of any single draft).
- Voice anchor from team prompt + latest issue body.
- Recent `#promotion` history serves as natural voice calibration.
- Jamie always edits before posting.

Marky's prompt explicitly names this anxiety so the model treats voice tentatively, not confidently.

**Per-link Reddit thread cadence.** Marky drafts all per-link threads in one batch when `promotion-prep` fires. Jamie posts them to r/WeeklyThing on his own cadence over the following week.

**Persona, not Discord client.** Marky's `prompts/marky/prompt.md` shapes the voice. The Discord-client persona stays minimal (just enough to render messages under her avatar). All her work flows through `promotion-prep` and `daily-metrics`.

### `daily-metrics` (Marky)

**Trigger:** scheduled daily 7pm CT. Manual via slash command.

**Active condition:** there's a recently-shipped issue OR an active campaign. Otherwise PASS — stay quiet, no "nothing to report" acks.

**Inputs:**
- Buttondown subscriber growth (`buttondown__subscriber_growth(days=N)`).
- Tinylytics summary (`tinylytics__summary(days=N)`).
- Per-campaign metrics (Tinylytics + Buttondown attribution by ref).
- Comparison against expectation (each campaign's `expected_signups` / `expected_traffic`).

**Output to `#promotion`:** one terse report when something material moved. Notable signals: campaign trending below/above expectation, subscriber spike or churn, latest-issue traffic pattern. Default PASS.

### `add-campaign` and `campaign-report`

`add-campaign <name> <ref> [<expected_signups>] [<expected_traffic>]` writes a row into the `campaigns` table:

```sql
INSERT INTO campaigns (name, ref, status, started_at, expected_signups, expected_traffic)
VALUES ('dense-discovery-may-2026', 'dd-2026-05', 'live', '2026-05-15', 50, 800);
```

`daily-metrics` inserts one row per active campaign into `campaign_metrics` each run (a 90-day window of history is plenty for reporting; older rows can age out). `campaign-report` joins `campaigns` against the latest `campaign_metrics` row per campaign and posts a summary.

### `issue-status`

Read-only state report on the in-flight issue. Computes `draft__section_status` plus a few extras (cover image present, intro non-empty, queue depth, days to pub). Posts to whatever channel the slash command was invoked from (or ephemeral ack to invoker — design choice).

---

## Agents and personas

Two real-time Discord agents (Eddy, Linky) and two personas-as-job-voice (Patty, Marky). All four have `prompts/<name>/prompt.md` files for voice + behavior.

### Eddy — Editor

**Surface:** Discord client (`personas/eddy.py`), home channel `#editorial`.

**When he runs:** invoked by `update-draft` (review the just-written draft) and `create-final` (reorder review). No heartbeat. Mention-driven asks in `#editorial` continue to work for ad-hoc questions.

**What he does:**
- Composes the post-update review card (completeness + editorial scan).
- Conducts the reorder review for `create-final`.
- May write `eddy-edits.md` to S3 if he proposes substantial revisions Jamie wants preserved.

**What he doesn't do:**
- No heartbeat. No "wake up and check things."
- No editing of `draft.md` body. He proposes; Jamie disposes.
- No interaction with Patty or Marky.

### Linky — Pinboard curator

**Surface:** Discord client (`personas/linky.py`), home channel `#research`.

**When he runs:** `pinboard-scan` job, scheduled Mon–Fri 6:30a / 6:30p during the issue window. Mention-driven asks continue to work.

**What he does:** the four lanes spec'd in `pinboard-scan` above.

**What he doesn't do:**
- No work outside the issue window.
- No engagement with the draft itself — that's `update-draft`'s job, which reads Pinboard state Linky helped curate.
- No interaction with Eddy, Patty, Marky.

### Patty — Membership steward (persona on `compose-cta`)

**Surface:** persona prompt only. No Discord client, no heartbeat, no inbox. Her work is the `compose-cta` job, which uses her prompt to compose CTAs.

**Voice:** Thingy's. Patty is invisible to readers — the CTAs read as Thingy speaking. Public voice: librarian-adjacent, not salesy, inviting.

**Milestone-driven, not weekly.** Patty's frame is the current active goal in the `goals` table (e.g., "get to 50 supporting members"). Each issue's CTA is one beat in the arc toward that milestone. When a goal is achieved, Jamie marks the row and inserts the next. The May 13 anniversary is pacing context (issues remaining, year-rhythm), not the goal anchor. For arc continuity she reads the **last 3–4 issues' `publish.md` files** — her previous CTAs are right there in the artifacts. No separate notes file.

**The only agent-authored content that ships.** Patty's words appear in the published issue. This is desired — she's the membership-steward voice, not Jamie's voice.

### Marky — Promotion (persona on `promotion-prep`, `daily-metrics`)

**Surface:** persona prompt only. No Discord client of her own beyond rendering messages — her work is `promotion-prep` and `daily-metrics` jobs, which use her prompt to compose drafts in Jamie's voice.

**Voice:** Jamie's, for posts that go out under Jamie's name. Voice work is the highest-stakes thing she does; architecture mitigates by drafting multiple framings and never auto-posting. Voice calibration comes from recent `#promotion` Discord history (her own past drafts plus Jamie's edits and reactions) — no separate notes file.

**Operates on the last published issue**, not the in-flight one. RSS update is the trigger; she reads from the workspace `publish.md`.

**Owns the campaign ledger.** All ad campaigns live in the `campaigns` and `campaign_metrics` tables in workshop.db. She reports on them daily via `daily-metrics`.

---

## Storage architecture

**Public bucket — `s3://files.thingelstad.com/weekly-thing/{N}/`**

| File | Owner | Required for ship? | Notes |
|---|---|---|---|
| `draft.md` | `update-draft` | — | Working view. Pure projection of upstream + assets. |
| `final.md` | `create-final` | required | Post-Eddy. Editorial-final ordering. |
| `intro.md` | author (Drafts + Shortcut) | required | Jamie writes; pushed via iOS Shortcut. |
| `currently.md` | author (Drafts + Shortcut) | optional | Jamie writes; pushed via iOS Shortcut. |
| `haiku.md` | `compose-haiku` | required | Generated and reviewed. |
| `metadata.json` | `compose-meta` | required | Subject + description (subset of Buttondown email schema). |
| `cta-1.md`, `cta-2.md` | `compose-cta` (Patty) | optional | 0–2 files. Each has `placement:` YAML frontmatter. |
| `publish.md` | `build-publish` | the ship artifact | `final.md` + all assets inlined at their positions. |
| `cover.jpg`, `cover-large.jpg` | iOS Shortcuts | required | Binary, untouchable by agents (allowlist). |
| `journal/*.jpg` | iOS Shortcuts | — | Binary. |
| `body-{N}.mp3`, `weekly-thing-{N}.mp3` | `pipeline/audio/` | — | Binary. |
| `eddy-edits.md` | Eddy (rare) | — | Substantial revision proposals when Jamie wants them preserved. |

The `tools/s3.py` allowlist (`.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv`, `.html` only) prevents agents from clobbering binaries.

**Bucket-level versioning required** for rollback safety on `draft.md`. Verify with `aws s3api get-bucket-versioning --bucket files.thingelstad.com`; enable if absent. Rollback via boto3's native `list_object_versions` / `get_object(VersionId=...)`. No custom version-tracking tools.

**SQLite — `apps/workshop_bot/data/workshop.db`**

All operational state. The earlier design had a separate private S3 bucket for persona-private state (Patty's goals, Marky's campaigns); that's been consolidated here. The boundary is simple: **public S3 is what ships; SQLite is everything else.**

Existing tables continue: `agent_runs`, `agent_outputs`, `agent_notes`, `link_candidates`, `pinboard_popular_seen`, `subscriber_events_seen`, `thingy_tokens`, `issue_window`.

New tables for this redesign:

| Table | Schema | Purpose |
|---|---|---|
| `job_locks` | `(asset TEXT, job TEXT, started_at, pid)` | Single-asset locking. See "Job execution model." |
| `draft_digests` | `(issue, ran_at, word_count, notable_count, brief_count, journal_count, intro_present, currently_present, haiku_present, cover_present, source_hash)` | Eddy's delta context. Each `update-draft` run writes a digest; Eddy reads the previous to compute "since yesterday: ...". |
| `goals` | `(id, target_kind, target_value, started_at, achieved_at NULL, notes)` | Patty's milestone progression. At most one row with `achieved_at IS NULL` — the active goal. Historical rows preserved for arc context. |
| `campaigns` | `(name PK, ref, status, started_at, ends_at, expected_signups, expected_traffic, notes)` | Marky's per-campaign metadata. Created by `add-campaign`. |
| `campaign_metrics` | `(id, campaign_name FK, ran_at, signups, traffic)` | Marky's append-only metric history. Each `daily-metrics` run inserts a row per active campaign. |

The existing `agent_inbox` table is dropped in Step 1 (decommission pass) — see Build sequence.

**Decommissioned (was in earlier draft):**

- `s3://weekly-thing-workshop/` bucket — not needed.
- `WORKSHOP_BUCKET` env var — remove.
- `tools/persona_s3.py` — delete.
- `s3_personas__*` tools — delete (not renamed to `scratchpad__*` as the earlier draft proposed; just deleted).
- `patty/year_goal.json`, `marky/campaigns/<name>.json` — replaced by SQLite tables.
- Patty's `arc_notes.md`, Marky's `voice_notes.md` — already dropped earlier; Patty reads past `publish.md` files in the public bucket; Marky uses `#promotion` Discord history.

---

## Integration with the existing site pipeline

`apps/workshop_bot/` produces `publish.md`. The existing `pipeline/content/` (Buttondown pull/build/diff/push) handles delivery. After `build-publish` writes `publish.md`:

1. Jamie runs the existing Buttondown push flow. It reads `publish.md` from the workspace.
2. Buttondown sends. The existing GitHub Actions cron picks up the new issue, regenerates the archive, builds the corpus, redeploys.
3. RSS feed updates with the new issue.
4. Marky's RSS polling detects the issue is live → `promotion-prep` auto-fires; she reads from the same `publish.md` artifact.

Required change to `pipeline/content/`: the Buttondown push should read `publish.md`. No fallback path — if `publish.md` doesn't exist, the issue isn't ready, and Jamie should let the workshop_bot finish its job. (Old behavior of pushing whatever `draft.md` looked like from iOS Shortcuts goes away once Step 9 retires the Shortcuts pipeline.)

---

## Build sequence

Smallest-to-largest, each step shippable on its own. The first step is a **decommission pass** — clearing out machinery the previous design built up that no longer fits. Old iOS Shortcuts pipeline stays as backup until step 9.

**How to work this with Claude Code:** start at Step 1. Each step has explicit acceptance criteria — don't move to the next step until the current step's acceptance passes. Open questions noted in the brief don't block early steps; they get resolved during the step that depends on them (e.g., the per-section `fill(N)` signature is decided in Step 3, the Discord reaction-based interaction primitive in Step 6).

### Step 1 — Decommission unused machinery

The previous design built up surface area for inter-agent messaging and other patterns that are dead in the new design. Clear them out *before* adding new stuff so we don't build on a confusing foundation.

Remove:

- **`tools/inbox.py`** entirely. The four `inbox__*` tools (`post`, `list`, `read`, `mark_read`).
- **`agent_inbox` table** from `db/schema.sql` and its column migrations. Drop in a schema migration; if any rows exist, ignore them (no migration to preserve — none of it is load-bearing in the new design).
- **The "Structured handoffs — the inbox" section** in `prompts/shared/team.md`.
- **All inbox references** in the existing four heartbeat prompts (`prompts/<persona>/heartbeat.md`).
- **The `VALID_KINDS` / `VALID_RECIPIENTS` machinery** in `inbox.py`'s test file (delete the test file).
- **The existing `/workshop heartbeat <agent>` slash command** registration (no replacement needed — Linky's heartbeat becomes a job in Step 5; the others lose their heartbeats entirely).

Rename / delete in this same pass:

- **`/workshop next-issue`** → **`/workshop job start-issue`**.
- **`tools/s3.py` tool surface** — currently registered as `s3_issues__*`. Rename to **`workspace__*`** to match how the design talks about it (the per-issue working directory):

  | Old name | New name |
  |---|---|
  | `s3_issues__list_workspaces` | `workspace__list_all` |
  | `s3_issues__list` | `workspace__list_files` |
  | `s3_issues__read_file` | `workspace__read` |
  | `s3_issues__write_file` | `workspace__write` |

- **`tools/persona_s3.py` and the `s3_personas__*` tools** — delete entirely. The private bucket they backed is gone in this redesign; persona-private state moves to SQLite. Remove the `WORKSHOP_BUCKET` env var documentation too.

Update `prompts/shared/team.md` and any persona prompt that references the old names.

**Acceptance:** Tests pass. `/workshop job start-issue` works. Zero `inbox__*` and `s3_personas__*` references in the codebase. `workspace__*` tools resolve correctly.

### Step 2 — Active-window awareness in heartbeats

- Update `prompts/eddy/heartbeat.md`, `prompts/linky/heartbeat.md`, `prompts/patty/heartbeat.md`, `prompts/marky/heartbeat.md` to PASS when the issue window isn't active. (Heartbeats stay running through this step. Step 5 replaces Linky's heartbeat with `pinboard-scan`. Step 6 removes Eddy and Patty heartbeats. Step 8 removes Marky heartbeat.)

**Acceptance:** `/workshop job start-issue 999 2026-08-01 7`. Wait 24h. Zero Discord messages from any persona.

### Step 3 — Job runtime + `start-issue` + draft template + first `update-draft`

- Add `apps/workshop_bot/jobs/_base.py` — Job protocol + the single-asset locking model (`job_locks` SQLite table).
- Add `apps/workshop_bot/templates/draft_starter.md` (template with section content blocks).
- Add `apps/workshop_bot/jobs/start_issue.py`.
- Add `apps/workshop_bot/jobs/update_draft.py` with stub fill functions for each section (return placeholder content). `intro.fill`, `currently.fill`, `haiku.fill` read their respective `.md` files from the workspace (empty if missing).
- Add `apps/workshop_bot/jobs/issue_status.py`.
- Wire `/workshop job start-issue`, `/workshop job update-draft`, `/workshop job issue-status` slash commands.

**Acceptance:** `/workshop job start-issue 458 2026-05-16 7` creates the S3 folder and writes a `draft.md` with all section blocks present (placeholder for Pinboard/microblog blocks; `intro`, `currently`, `haiku` blocks empty since files don't exist yet). `/workshop job update-draft` re-runs it. `/workshop job issue-status` shows required/optional asset presence. Re-firing `update-draft` while a previous run is still in progress exits with a clear "already running" message.

### Step 4 — Real fill functions + Eddy's review + dynamic context

- Implement `notable.fill`, `brief.fill`, `journal.fill` (deterministic — read from sources, render markdown). No `featured.fill`; that section is retired. Journal pulls everything from micro.blog, no tag filtering.
- `intro.fill`, `currently.fill`, `haiku.fill` are trivial — read the file from workspace, paste contents into the block. (Note: no `haiku.compose` inside `update-draft` — the haiku is now its own composed asset; see Step 6.)
- Add `apps/workshop_bot/tools/context.py` with `build_eddy_context()` (today's date, days-to-publish, word count, section completeness summary, intro/currently/haiku/cover presence, delta from last digest).
- Add `draft_digests` table to workshop.db; write a digest at the end of each `update-draft` run.
- Implement Eddy's post-update review (delta-aware completeness card + editorial observations + editorial guards including word-count guard) as part of `update-draft`'s tail. **Silent Sun/Mon — Eddy doesn't post on those days.**
- Add `draft__section_status` helper.
- Update `update-draft` to refuse when `final.md` exists.
- Add scheduled cron for daily 5pm CT `update-draft`.

**Acceptance:** Run a real issue end-to-end through update-draft over Tue–Fri. Eddy posts a useful card each evening showing the delta from the prior day. Word count is shown; over 3000 words, Eddy flags it. Run on Sun/Mon: `update-draft` runs, no Eddy card posted. Run `update-draft` after `final.md` exists: clear refusal.

### Step 5 — Linky `pinboard-scan` + new Pinboard verbs

- Add the job-oriented Pinboard tools (`issue_candidates`, `capture_blurb`, `popular_unseen`, `mark_seen`, `estimate_read_length`, `queue_depth_vs_deadline`, `archive_recall`). `issue_candidates(section?)` takes `notable | brief` only — no `_featured`.
- Refactor `systems/pinboard/server.py` — existing tools are 1:1 API mirrors; new tools are job-oriented. Existing primitives stay available for ad-hoc use, but the prompt reaches for the job-oriented verbs first.
- Add `apps/workshop_bot/jobs/pinboard_scan.py` with the four lanes.
- Add `build_linky_context()` to `tools/context.py` (today's date, days to publish, days into window, queue depth + read-length distribution, items captured this week).
- Update `prompts/linky/prompt.md` to use the new verbs and the four-lane structure.
- Schedule the Mon–Fri 6:30a / 6:30p job. Decommission the old 6h Linky heartbeat.

**Acceptance:** Tag a Pinboard item `_brief` + `toread`, wait for Linky's ask, reply with a blurb, verify Pinboard description updated and `toread` removed. Item appears in next `update-draft` Brief section.

### Step 6 — `create-final` + compose chain + `build-publish`

The big step. After this lands, the full issue-assembly pipeline works end-to-end.

- Add `apps/workshop_bot/jobs/create_final.py` with Eddy's reorder review (interactive Discord reaction flow per section).
- Add `apps/workshop_bot/jobs/compose_haiku.py` — generates 2–3 haiku options, posts to `#editorial`, writes `haiku.md` on Jamie's pick.
- Add `apps/workshop_bot/jobs/compose_meta.py` — generates 2–3 subject + description options, posts to `#editorial`, writes `metadata.json` on Jamie's pick. Reads `data/buttondown/emails/*.json` for "don't repeat recent subjects."
- Add `apps/workshop_bot/jobs/compose_cta.py` (Patty) — generates 0–2 CTAs with 1–2 framings each, posts to `#supporters`, writes `cta-1.md` / `cta-2.md` on Jamie's pick. Each CTA file has YAML frontmatter encoding placement.
- Add `apps/workshop_bot/jobs/build_publish.py` — reads `final.md` + all assets, inlines them, writes `publish.md`. Refuses with a clear missing-list if required assets absent.
- Add the `goals` table to workshop.db. Seed it with Jamie's current active goal (`INSERT INTO goals (target_kind, target_value, started_at) VALUES ('members', 50, '2026-05-13')` or whatever the current state is).
- Add `build_patty_context()` to `tools/context.py` (today's date, days to next May 13, expected issues remaining, year-to-date progress, current nonprofit).
- Wire the auto-fire chain: `create-final` → `compose-haiku` + `compose-meta` + `compose-cta` in parallel → on all-three-complete + required-Jamie-assets-present → `build-publish`.
- Update `pipeline/content/` Buttondown push to read `publish.md`.
- Decommission Eddy and Patty heartbeats (Eddy is job-triggered; Patty has no heartbeat surface).

**Acceptance:** End-to-end on a real issue: `update-draft` runs through the week, `create-final` reorders → `final.md`, three compose jobs auto-fire in parallel, each gets Jamie's pick, `build-publish` auto-fires and writes `publish.md`. The published issue includes the CTAs in Thingy's voice, the chosen haiku, the chosen subject and description.

### Step 7 — `promotion-prep` + RSS detection (Marky)

- Add RSS polling for `weekly.thingelstad.com/feed.xml` (weekend cadence). Record "last detected issue" in `agent_notes` for dedupe.
- Add `apps/workshop_bot/jobs/promotion_prep.py` (Reddit megathread + per-link + LinkedIn drafts).
- Reads `publish.md` from the workspace (same artifact other agents use).
- Add `build_marky_context()` to `tools/context.py` (today's date, latest-published issue + ship date + days since ship, active campaigns with days running).
- Auto-fire on RSS detection.
- Update `prompts/marky/prompt.md` with the per-platform conventions and voice anxiety framing.

**Acceptance:** Ship an issue. Marky drafts all syndication content within 24h. Jamie posts each with one click + light edit.

### Step 8 — `daily-metrics` + campaign tracking + remaining tool refactors

- Add the `campaigns` and `campaign_metrics` tables to workshop.db.
- Add `apps/workshop_bot/jobs/daily_metrics.py` (Marky's daily report, default-PASS). Each run inserts one row per active campaign into `campaign_metrics`.
- Add `apps/workshop_bot/jobs/add_campaign.py` (writes a row into `campaigns`) and `campaign_report.py` (joins `campaigns` + latest `campaign_metrics`).
- Schedule daily 7pm CT. Decommission Marky heartbeat (now job-triggered).
- Review and refactor `systems/buttondown/server.py`, `systems/tinylytics/server.py`, `systems/stripe/server.py` tool surfaces to fit the jobs they support, not the underlying APIs they wrap. Same exercise as Pinboard in Step 5 — drop verbs that don't serve a job, rename verbs whose names describe the API rather than the work, collapse multi-call sequences into single job-oriented verbs where it helps.

**Acceptance:** Register a Dense Discovery campaign via `/workshop job add-campaign`. Marky reports daily on its performance. Default PASS when nothing material moved. Remaining system tool surfaces match the jobs they support.

### Step 8.5 — Update `apps/workshop_bot/CLAUDE.md`

The existing `apps/workshop_bot/CLAUDE.md` describes the prior design (heartbeats as the only scheduled surface, agent_inbox as the handoff mechanism, etc.). Rewrite to reflect the new architecture:

- The job-as-spine model (`/workshop job <name>` surface).
- The unified asset pattern (intro/currently/haiku as standalone files; `update-draft` reads them).
- The Eddy / Linky / Patty / Marky surfaces as they now stand.
- New SQLite tables (`goals`, `campaigns`, `campaign_metrics`, `job_locks`, `draft_digests`).
- Removal of `inbox__*` tools and `agent_inbox` table.
- Removal of `s3_personas__*` tools and `WORKSHOP_BUCKET`.
- The `workspace__*` rename.

Also update the project-root `CLAUDE.md` (`/Users/jamie/Projects/weekly.thingelstad.com/CLAUDE.md`) where it references workshop_bot — the existing description is partially stale.

**Acceptance:** Both CLAUDE.md files describe what's actually built, not what was planned in the earlier design.

### Step 9 — Decommission iOS Shortcuts

- After 3–4 successful ships via the new flow, retire the per-section Shortcuts.
- Shortcuts remain as a recovery tool for unusual situations.

---

## Open questions / TODOs

1. **S3 versioning verification.** `aws s3api get-bucket-versioning --bucket files.thingelstad.com`. Enable if absent. Required before Step 4 lands (so `draft.md` rollback works once real fill functions are writing it).

2. **CTA word/length cap.** Soft cap on each Patty CTA — likely 30–60 words but tune after seeing real output. Defer to a tuning round once `compose-cta` is live.

3. **Haiku format conventions.** Strict 5-7-5? Looser "haiku-shaped"? Look at past issues' haikus during Step 6 implementation and codify in `compose-haiku`'s prompt.

4. **Subject convention precision.** "Three Words Title" — comma-separated, title case. Confirm by sampling recent issues during Step 6.

5. **Discord reaction-based interaction primitive.** Several jobs (`create-final`, `compose-*`) need a "post options → wait for Jamie's reaction → continue" flow. The existing runtime has the building blocks (Discord client + `agent_outputs` table) but not a reusable reaction-wait helper. One design pass before Step 6 to nail the pattern. Likely a small `tools/interaction.py` with `await_choice(channel, options)` and `await_approval(channel, draft)`.

6. **Cross-issue read tools.** Mentioned in passing: `compose-meta` looks at recent past subjects to avoid repetition. Other future cases will surface (e.g., Patty noting past nonprofits during a transition year). When a job needs cross-issue context, prefer reading from the existing `data/buttondown/emails/*.json` files and the archive corpus — they're already canonical and queryable. No new "past issues" tool surface needed unless something specific demands one.

---

## What this brief intentionally does not cover

- **Specific Discord card markup.** Embed/component syntax — defer to implementation.
- **Pinboard API call details.** Existing client wraps Pinboard's `posts/add` etc.; new job-oriented verbs collapse onto those primitives.
- **Test strategy.** Existing `tests/test_*.py` pattern with stubbed clients applies.
- **Error handling and retries.** Standard practices; no special handling required.
- **Cost monitoring.** The job-as-spine pattern keeps costs naturally bounded — most jobs are pure Python; agent loops are narrow. `db.AgentRun` already logs token spend; existing log inspection is enough.

---

## TL;DR

- **Old approach was over-agentified.** Skills, inboxes, inter-agent handoffs were the wrong spine.
- **New spine: jobs.** Deterministic Python in `apps/workshop_bot/jobs/`, schedulable + on-demand. Single command shape: `/workshop job <name>`. Single-asset locking for concurrency.
- **Unified asset pattern.** Every piece of issue content is a standalone file in the workspace: `intro.md` (Jamie writes), `currently.md` (Jamie writes), `haiku.md` (`compose-haiku`), `metadata.json` (`compose-meta`), `cta-*.md` (`compose-cta`). `update-draft` reads them all into `draft.md`; `build-publish` assembles the final `publish.md`.
- **Auto-chained compose phase.** `create-final` triggers `compose-haiku` + `compose-meta` + `compose-cta` in parallel; each runs its review loop with Jamie; `build-publish` auto-fires when everything's ready.
- **Required vs optional assets.** `build-publish` is the hard gate. `intro.md`, `haiku.md`, `metadata.json`, `cover.jpg` are required; `currently.md` and CTAs are optional.
- **Two real-time agents:** Eddy (job-triggered, no heartbeat; silent Sun/Mon, delta-aware reviews Tue–Fri) and Linky (Mon–Fri 6:30a/6:30p `pinboard-scan` for Pinboard only).
- **Two personas-as-job-voice:** Patty (`compose-cta`) writes the membership CTA in Thingy's voice; Marky (`promotion-prep`, `daily-metrics`) drafts syndication copy in Jamie's voice for him to edit.
- **Closed loops, no inter-agent inbox.** Each lane is independent; Jamie is the integrator.
- **Source systems remain canonical.** Pinboard owns bookmark blurbs (only tag: `_brief`, no `_featured`); micro.blog owns journal (pull everything, filter at `create-final`); `currently.md` and `intro.md` are static markdown Jamie writes via Drafts + Shortcut. `draft.md` is a regenerable pure projection.
- **Storage discipline.** Public bucket for what ships; private bucket for *operational state only* (year goal, campaign ledger — no journals or notes); SQLite for runtime state including job locks and draft digests.
- **Build incrementally.** Nine steps — decommission pass → active-window awareness → start-issue + draft + update-draft → real fills + Eddy + dynamic context → Linky + Pinboard verbs → create-final + full compose chain → promotion-prep + RSS → daily-metrics + remaining tool refactors → retire iOS Shortcuts. Each shippable on its own.
