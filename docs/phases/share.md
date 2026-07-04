# Phase 3 — Share

*Promote it.* — Overview: [`../publishing-process.md`](../publishing-process.md)

**Owner:** Marky. **Channel:** `#promotion`. **Question:** *"Is the published issue out in the
world?"* Share operates on the **last-published** issue — one behind Build/Publish (see Concurrency
in the overview).

## What happens

Per-issue syndication of the just-published issue:

- A **LinkedIn** post and the **r/WeeklyThing** megathread + per-link discussion threads, drafted
  by `promotion-prep` — **auto-fired when the issue enters Share** (`put-to-bed`), re-runnable via
  `/marky prep`. (Marky **never auto-posts** — drafts only; Jamie posts.)
- Current campaign performance + subscriber/engagement metrics shown as **context** (read-only).

There is no hard "done" — metrics keep accruing. Marky's drafts land in `#promotion`; the
production page (phase `share`) carries the issue's published state, and campaign context comes
from `/marky metrics` / `/marky campaign report`.

## Phase vs program

Share is the per-issue **touchpoint** of the [Campaigns program](../programs/campaigns.md) — it is
**not** where campaigns are managed. Standing campaign work (creating/editing campaigns, ad
placements, ref tracking over time) lives in the program, via `/marky campaign …`. Marky is the one
persona who spans both: it owns this phase *and* runs that program.
