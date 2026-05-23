# The Weekly Thing — Publishing Process (north star)

This is the canonical model for how an issue of *The Weekly Thing* comes into being and goes out
into the world. It exists so the rest of the monorepo — `apps/workshop_bot`, the `pipeline/`, the
site build, and every per-app `CLAUDE.md` — has one shared mental model to design against. When a
surface, a job, or a persona feels confusing, the test is: *does it respect this model?*

> **Status (2026-05):** the *model* below is the target we build to. Some of it is live today
> (the per-channel renderers, the personas, Marky-on-last-published, the goals/campaigns ledgers);
> some is in flight (the explicit `phase` state, the per-phase cards, the auto-requested CTA, a
> podcast CTA slot). Inline **Today** notes mark the gaps. The model is the destination.

---

## The shape at a glance

An issue moves through **three sequential phases**. Running **alongside** them — not inside them
— are **standing programs** that span many issues and touch a phase only at defined points.

```
   per issue:     BUILD  ──▶  PUBLISH  ──▶  SHARE
                  (write)     (send out)    (promote)
                    │             │            │
   touchpoints:     │         CTA slot     syndication
                    │             │            │
   standing:        │      ┌──────┴───────┐    │
   programs ········│······│  MEMBERSHIP  │····│······· (Patty: fundraise)
                    │      └──────────────┘    │
                    └───────────────────┌──────┴───────┐
                                        │  CAMPAIGNS    │  (Marky: grow + engage)
                                        └───────────────┘
```

Two truths fall out of this and explain most of the design:

1. **Phases are per-issue and run concurrently across issues.** While WT349 is in **Build**,
   WT348 is in **Share**. The system tracks this with two pointers: the *active window*
   (`issue_windows.is_active = 1`) is the Build/Publish issue; the *last-published* issue is the
   Share issue.
2. **Programs are not phases.** Patty's Membership drive and Marky's Campaigns are standing
   initiatives with their own annual/ongoing cadence, objectives, and tools. A phase merely
   *draws on* a program at a touchpoint (Publish pulls a CTA from Membership; Share feeds
   Campaigns). Programs get **no per-issue card** — they have their own surfaces.

---

## Phase 1 — Build  ·  *create the issue*

**Owner:** Eddy (editor), with Linky feeding curated links. **Channel:** `#editorial`.
**Question:** *"Is the issue written, and is it good?"* Build fills in gradually all week.

The issue is **one uniform, channel-agnostic content artifact** with a fixed anatomy in **reading
order** (`tools/renderers.py:_compose_published_body` is the authoritative assembly — every
channel composes from this same shape):

| # | Section | Reader-facing heading | Source | Who writes it | Required to ship? |
|---|---------|----------------------|--------|---------------|-------------------|
| 1 | Intro | (none — opening prose) | `intro.md` atom | Jamie (Drafts → Shortcut) | ✅ |
| 2 | Currently | `## Currently` | `currently_entries` DB | Jamie (`/eddy currently`) | optional |
| 3 | Cover | (image + caption) | `cover.json` + `cover.jpg` | Jamie (Shortcut) | ✅ |
| 4 | Notable | `## Notable` | `issue_items` (Pinboard, untagged-in-window) | Jamie curates; Linky researches | ✅ (≥1 section) |
| 5 | Journal | `## Journal` | `issue_items` (micro.blog window) | Jamie (writes on micro.blog) | ✅ (≥1 section) |
| 6 | Briefly | `## Briefly` | `issue_items` (Pinboard `_brief`) | Jamie curates | ✅ (≥1 section) |
| 7 | Outro | (none — closing prose) | `outro.md` atom | Jamie (Drafts → Shortcut) | optional |
| 8 | Haiku | (bold tercet) | `haiku.md` atom | `compose-haiku` (Jamie picks) | ✅ |
| 9 | **Echoes** | `## Echoes` | `closer.md` atom | `compose-closer` (Thingy's voice) | optional (SKIP allowed) |

*Featured* sections (micro.blog `Featured` category) splice in around Notable/Journal/Briefly.
**Echoes** (renamed from "The Closer") is Thingy's archive note — a 2–5 sentence connection to the
nine-year archive (thematic resonance or anniversary echo), in the librarian's voice.

**Editorial review lives here.** On each draft refresh, Eddy runs a single substantive **Opus**
pass (`prompts/eddy/draft-review.md`) — anchored, suggestions-only — surfaced in the `draft.html`
"Show review" drawer and counted on the Build surface. It re-runs only when the draft actually
changed.

- **Entry gate:** `/eddy issue start <n> <pub-date> <days>` opens the window.
- **Exit gate:** **`mark built`** — Jamie (or Eddy, when content is complete) declares the issue
  written. This is the single most important transition: it's what moves the issue to Publish and
  re-scopes everyone's attention. *Build never asks about Publish things* (subject, description,
  CTA) — surfacing those during Build is a phase violation and the original source of operator
  friction.

---

## Phase 2 — Publish  ·  *send it out*

**Owner:** Eddy + the `pipeline/`. **Channel:** `#editorial`. **Question:** *"Is it out the door,
per channel?"*

Build is uniform; **Publish fans out per channel, and that divergence is the feature.** Each
channel renders the same body its own way and ships its own way. Some inputs are shared across all
channels; some are unique to one.

| Channel | Render artifact | Shared inputs | Channel-unique | Ship mechanic | Gate |
|---------|----------------|---------------|----------------|---------------|------|
| **Email** (Buttondown) | `buttondown.md` (`render_email_for_issue`) | subject, description, body | membership **CTA** (Liquid, audience-aware); tinylytics pixel | POST/PATCH Buttondown API | `REQUIRED_FOR_BUTTONDOWN` = haiku + metadata + intro + cover |
| **Website** (archive) | `archive.md` (`render_archive_for_issue`) | subject, description, body | YAML front matter; no CTA, no pixel | atomic GitHub commit to `data/issues/{N}/` | Email shipped (so `absolute_url` is stamped) |
| **Podcast** (audio) | `transcript/*.txt` (`render_transcript_for_issue`) + MP3 | body | per-block transcript (uniquely shaped); a **CTA audio slot soon** | per-block TTS + concat + S3 upload + manifest | transcripts present (always, post-Build) |

**Shared envelope inputs** — *subject* (one line, all channels) and *description* (comma-separated
topic line; email preview + website front-matter) — are set in Publish, not Build. They live in
`metadata.json` alongside the deterministic `number`/`slug`/`image`/`publish_date` and the
publish-stamped `buttondown_id`/`absolute_url`.

- **Entry gate:** `mark built`. On entry, the ship flow **auto-requests the CTA from Patty** (see
  Membership) so a framing is waiting — Jamie only *picks* it, never triggers it.
- **Exit gate:** `put-to-bed` — files the issue into the `issues` table and closes the window
  (`is_active = 0`). The issue is now *published* and becomes the Share target.

---

## Phase 3 — Share  ·  *promote it*

**Owner:** Marky. **Channel:** `#promotion`. **Question:** *"Is the published issue out in the
world?"* Share operates on the **last-published** issue — one behind Build/Publish.

Per-issue syndication of the just-published issue: a LinkedIn post, the r/WeeklyThing megathread +
per-link discussion threads (drafted by `promotion-prep`, never auto-posted), with current
campaign performance + subscriber/engagement metrics shown as context. There is no hard "done" —
metrics keep accruing.

Share is the per-issue *touchpoint* of the Campaigns program; it is **not** where campaigns are
managed (that's the standing program — see below).

---

## Programs (standing, alongside the phases)

Programs span many issues, have their own cadence and objectives, and **get no per-issue card.**
They surface through their own tools and touch a phase only at defined points. There are **two,
and they are different in kind:**

### Membership  ·  Patty  ·  `#supporters`

*Fundraise for a chosen non-profit via the Supporting Membership program.* Runs on an **annual
cycle** tied to the Weekly Thing year (since May 2017), with a beneficiary chosen each year
(currently the Signal Foundation; EFF and Creative Commons in past years). Objective: members /
dollars (the `goals` table, `target_kind` ∈ members/dollars). Tools: the per-issue **CTA slot(s)**
(composed in Thingy's voice by `compose-cta`), supporter framings, the Stripe supporting-membership
flow, `/patty goal` / `progress` / `supporters` / `nonprofit`.

**Touchpoint: Publish.** The CTA is a Publish input, auto-requested when an issue enters Publish.
Patty composes goal-aware framings; Jamie picks one. Patty is invisible to readers — the CTA
speaks in Thingy's voice.

### Campaigns  ·  Marky  ·  `#promotion`

*Grow and engage the audience.* Two objectives: **engagement** (getting readers to share /
discuss) and **acquisition** (new readers via paid placements — e.g., Dense Discovery ad slots).
Ongoing, not annual. Tools: syndication copy, `?ref=` tracking (Tinylytics + Buttondown ref
signups), the `campaigns` ledger (`/marky campaign add|edit|report|copy|sunset`), `daily-metrics`.

**Touchpoints: Share** (per-issue syndication) **+ standalone placements** (ad buys that aren't
tied to any one issue and run on their own cadence).

> **Marky spans both layers:** he owns the per-issue **Share phase** *and* runs the standing
> **Campaigns program**. Patty owns *only* the Membership program (touching Publish via the CTA).
> Eddy owns Build + Publish and no program.

---

## Concurrency — two pointers

At any moment multiple issues are in flight at different phases. The system needs only two
pointers:

- **Active window** (`issue_windows.is_active = 1`) — the issue currently in **Build or Publish**.
- **Last-published** — the most recent issue filed by `put-to-bed`; the issue currently in
  **Share**. (Marky already reads this issue's `buttondown.md` via RSS — "Marky operates on the
  last *published* issue, not the in-flight one" is exactly this.)

**Worked example:** WT349 is in Build (active window). The moment it's marked built it enters
Publish (still the active window). When it's put to bed, WT349 becomes last-published and enters
Share — and the next start-issue makes WT350 the active window in Build. So WT350 Build ‖ WT349
Share run concurrently, owned by different personas in different channels.

---

## Phase state + transitions

The active issue carries an explicit **`phase`** (`build` | `publish`) on `issue_windows`. It is a
state, not a frozen artifact — the healthy successor to the retired `final.md` lock.

| Transition | Trigger | Effect |
|------------|---------|--------|
| → **build** | `start-issue` | Window opens; Build card posts; editorial review runs on refreshes |
| **build → publish** | **`mark built`** (`/eddy issue built` or the Build card button) | Build card finalizes; Publish card posts; CTA auto-requested from Patty; Eddy stops surfacing content-quality nags and starts surfacing send-readiness |
| **publish → build** | "Reopen for edits" | Back to Build to fix content |
| **publish → (published)** | `put-to-bed` | Files the issue; `is_active = 0`; becomes the Share target |

The phase is what makes "Build doesn't ask about Publish things" enforceable: subject / description
/ CTA only ever surface when `phase = publish`.

> **Today:** the active window conflates Build and Publish (no `phase` column yet); the explicit
> state + the per-phase cards are introduced by the work this doc anchors.

---

## Persona ⇄ phase / program map

| Persona | Phase(s) | Program | Channel | In one line |
|---------|----------|---------|---------|-------------|
| **Eddy** | Build + Publish | — | `#editorial` | Authors/reviews the issue and orchestrates the send |
| **Linky** | feeds Build | — | `#research` / `#discovery` | Researches candidate links into the curation queue |
| **Patty** | (touches Publish) | **Membership** | `#supporters` | Runs the annual fundraising drive; supplies the CTA |
| **Marky** | Share | **Campaigns** | `#promotion` | Syndicates published issues; runs growth/engagement campaigns |
| **Thingy** | — | — | `#ask-thingy` | Reader-facing Q&A + the voice of Echoes (orthogonal to the spine) |

**Repo ownership:** the Build/Publish/Share *orchestration* + the persona surfaces live in
`apps/workshop_bot` (see its `CLAUDE.md`). The per-channel *rendering* + the deterministic
publish/site path live in `pipeline/` and `apps/site`. The reader-facing Q&A + retrieval (and
Echoes' archive retrieval) run through `apps/thingy_bridge` + the Librarian Lambda. This doc is the
shared contract those pieces design against.
