# Program — Membership

*Fundraise for a chosen non-profit via the Supporting Membership program.* A **standing program**,
not a phase — it spans many issues and touches the spine only at one point. Overview:
[`../publishing-process.md`](../publishing-process.md).

**Owner:** Patty · **Channel:** `#supporters`

## Objective + cadence

- Raise **members / dollars** for a non-profit beneficiary chosen each year.
- Runs on an **annual cycle** tied to the Weekly Thing year (since May 2017), *not* the calendar
  year. Current beneficiary: the **Signal Foundation** (Ninth Year); EFF and Creative Commons in
  past years.
- Progress is tracked in the `goals` table (`target_kind` ∈ `members` / `dollars`) via
  `/patty goal` · `progress` · `supporters` · `nonprofit`.

## Tools

- The per-issue **CTA slot(s)** — composed by `compose-cta` in **Thingy's voice** (Patty is
  invisible to readers; the CTA speaks as the librarian).
- The Stripe supporting-membership flow (the donate URL is reusable across years — see the
  `reference_stripe_donate_url` memory).

## Touchpoint: Publish

The CTA is a **Publish-phase input**. When an issue enters Publish (`mark built`), the ship flow
**auto-requests** framings from Patty (goal-aware); Jamie just **picks one** on the Publish card —
he never has to remember to trigger it. Today the CTA lands in the **email** body; a **podcast
audio CTA slot** is planned (the one piece of the model not yet built).

> Patty owns *only* this program. She does not own a phase. Her work shows up in the spine solely
> through the Publish CTA — there is **no per-issue "membership card."**
