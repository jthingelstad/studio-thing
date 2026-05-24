# The Weekly Thing — Publishing Process (overview)

The canonical model for how an issue of *The Weekly Thing* comes into being and goes out into the
world. The whole monorepo — `apps/workshop_bot`, `pipeline/`, the site build, the per-app
`CLAUDE.md`s — designs against this. When a surface, job, or persona feels confusing, the test is:
*does it respect this model?*

This page is the **front door**: the shape, the concurrency, the phase machinery, and who owns
what. The detail lives in the per-phase and per-program docs linked below — keep this short.

---

## The shape at a glance

An issue moves through **three sequential phases**. Running **alongside** them — not inside them —
are **standing programs** that span many issues and touch a phase only at defined points.

```
   per issue:     BUILD  ──▶  PUBLISH  ──▶  SHARE
                  (write)     (send out)    (promote)
                    │             │            │
   touchpoints:     │         CTA slot     syndication
                    │             │            │
   standing:        │      ┌──────┴───────┐    │
   programs ········│······│  MEMBERSHIP  │····│······· (Patty: fundraise)
                    │      └──────────────┘    │
                    └───────────────────┌──────┴────────┐
                                        │  CAMPAIGNS    │  (Marky: grow + engage)
                                        └───────────────┘
```

Two truths fall out of this and explain most of the design:

1. **Phases are per-issue and run concurrently across issues.** While WT349 is in **Build**, WT348
   is in **Share**. Two pointers track this: the *active window* (`issue_windows.is_active = 1`,
   carrying `phase`) is the Build/Publish issue; the *last-published* issue is the Share issue.
2. **Programs are not phases.** Membership and Campaigns are standing initiatives with their own
   cadence, objectives, and tools. A phase only *draws on* a program at a touchpoint (Publish pulls
   a CTA from Membership; Share feeds Campaigns). Programs get **no per-issue card**.

---

## Read next

| You want… | Read |
|---|---|
| A phase in detail | [`phases/build.md`](phases/build.md) · [`phases/publish.md`](phases/publish.md) · [`phases/share.md`](phases/share.md) |
| What's in an issue + how it's formatted | [`sections.md`](sections.md) · [`journal-handling.md`](journal-handling.md) · [`featured-posts.md`](featured-posts.md) |
| Voice & tone | [`voice-and-style.md`](voice-and-style.md) |
| The Echoes archive note (a section) | [`echoes.md`](echoes.md) |
| A standing program | [`programs/membership.md`](programs/membership.md) · [`programs/campaigns.md`](programs/campaigns.md) |
| A persona's role | [`agents/`](agents/) (eddy · linky · marky · patty · thingy) |
| How issues are identified + titled | [`identifiers.md`](identifiers.md) |

---

## Concurrency — two pointers

- **Active window** (`issue_windows.is_active = 1`) — the issue in **Build or Publish** (its
  `phase` says which).
- **Last-published** — the most recent issue filed by `put-to-bed`; the issue in **Share**. (Marky
  reads its `buttondown.md` via RSS — "Marky operates on the last *published* issue" is exactly
  this.)

**Worked example:** WT349 is in Build. Marked built → Publish (still the active window). Put to bed
→ WT349 becomes last-published (Share), and `start-issue` makes WT350 the active window in Build.
So WT350 Build ‖ WT349 Share run concurrently, owned by different personas in different channels.

---

## Phase state + transitions

The active issue carries an explicit **`phase`** (`build` | `publish`) on `issue_windows` — a
state, not a frozen artifact (the healthy successor to the retired `final.md` lock).

| Transition | Trigger | Effect |
|---|---|---|
| → **build** | `start-issue` | Window opens (`phase=build`); Build card posts; editorial review runs on refreshes |
| **build → publish** | **`mark built`** (`/eddy issue built` or the Build-card button) | Build card finalizes; Eddy writes the **thesis** (`compose-thesis` over the now-frozen content — anchors every downstream Publish job); Publish card posts; CTA auto-requested from Patty; attention shifts from content-quality to send-readiness |
| **publish → build** | reopen (`/eddy issue reopen`) | Back to Build to fix content |
| **publish → (published)** | `put-to-bed` | Files the issue; `is_active = 0`; becomes the Share target |

This is what makes *"Build doesn't ask about Publish things"* enforceable: subject / description /
CTA only surface when `phase = publish`.

---

## Persona ⇄ phase / program map

| Persona | Phase(s) | Program | Channel | In one line |
|---|---|---|---|---|
| **Eddy** | Build + Publish | — | `#editorial` | Authors/reviews the issue and orchestrates the send |
| **Linky** | feeds Build | — | `#research` / `#discovery` | Researches candidate links into the curation queue |
| **Patty** | (touches Publish) | **Membership** | `#supporters` | Runs the annual fundraising drive; supplies the CTA |
| **Marky** | Share | **Campaigns** | `#promotion` | Syndicates published issues; runs growth/engagement campaigns |
| **Thingy** | — | — | `#ask-thingy` | Reader-facing Q&A + the voice of Echoes (orthogonal to the spine) |

**Repo ownership:** the Build/Publish/Share *orchestration* + persona surfaces live in
`apps/workshop_bot`. The per-channel *rendering* + the deterministic publish/site path live in
`pipeline/` + `apps/site`. The reader-facing Q&A + retrieval (and Echoes' archive retrieval) run
through `apps/thingy_bridge` + the Librarian Lambda ([`reference/librarian.md`](../reference/librarian.md)).
This doc is the shared contract those pieces design against.

> **Status note:** the podcast (audio) CTA slot is the one piece of this model not yet built — see
> [`programs/membership.md`](programs/membership.md). Everything else here is live.
