# External systems

Operator-facing notes on the third-party APIs the Weekly Thing site and workshop bot integrate with. The runtime code lives at `apps/workshop_bot/systems/<name>/`; this directory captures the **non-obvious** things — auth quirks, identifier confusions, endpoints that look right but aren't, hard limits, and what each tool we ship actually maps to.

If you find yourself debugging an integration and re-deriving facts from cURL probes, that's a sign the relevant page here needs an update.

## Systems

| System | Purpose | Doc |
|---|---|---|
| Buttondown | Newsletter publishing — subscribers, sent emails, engagement | [buttondown.md](buttondown.md) |
| Pinboard | Bookmark queue — Linky's curation surface | [pinboard.md](pinboard.md) |
| Stripe | Donations for the supporter program | [stripe.md](stripe.md) |
| Tinylytics | Privacy-friendly site analytics | [tinylytics.md](tinylytics.md) |

## Convention

Each page captures, in order:
1. **Auth + identifiers** — env-var names, the auth header shape, and any "looks like an ID but isn't" gotchas.
2. **Endpoints we use** — the exact `GET /...` paths and what each one returns. Verbatim where helpful.
3. **What our tool surface maps to** — every dotted tool name (`<system>.<action>`) and which endpoint(s) it calls.
4. **Quirks + dead ends** — things that returned 404/500 even though they looked plausible, or response fields that aren't what their name suggests.
5. **Limits** — rate caps, date-range caps, page-size caps.

Keep entries short. If a section gets long, it usually means a tool description in the system module deserves the same nuance.
