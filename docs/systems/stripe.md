# Stripe

Donations for the supporter program. The site pipeline reads the balance for the published "amount raised" stat (`pipeline/content/fetch_emails.py:fetch_stripe_balance`); the workshop bot's Patty + Marky read individual charges + aggregates for CTAs and campaign tracking (`apps/workshop_bot/systems/stripe/`).

Reference: <https://docs.stripe.com/api>.

## Auth + identifiers

Single env var:

```
STRIPE_API_KEY=rk_live_...     (restricted, scoped — recommended)
STRIPE_API_KEY=sk_live_...     (full access — overkill for our reads)
```

Stripe's Python SDK reads `stripe.api_key`; `_configure()` in our client sets it from env on every call. Auth is HTTP Basic with the key as the username and an empty password — but the SDK handles that.

The current `STRIPE_API_KEY` is a **restricted live key** (`rk_live_*`) with read-only scope on charges + balance. It is shared with the site build pipeline; both consumers tolerate the read-only ceiling.

## Endpoints we use

Base URL: `https://api.stripe.com/v1`. We use the official `stripe` Python SDK.

### `Balance.retrieve()` → `GET /v1/balance`
Returns `{available: [...], pending: [...]}` — both lists with `{amount, currency}` entries. We sum across all `currency == "usd"` entries.

### `Charge.list(...)` → `GET /v1/charges`
Paginated list of charges. Params we use: `limit` (max 100), `created={"gte": <unix>}`, `starting_after` (cursor pagination). Each charge: `id, amount, currency, created, status, paid, billing_details, metadata, payment_intent`.

We filter to `status == "succeeded" && paid == True` for "donations" — drops voids/refunds/holds.

## Tool surface (workshop bot)

| Tool | Endpoint | Notes |
|---|---|---|
| `stripe.balance` | `Balance.retrieve` | `{available_usd, pending_usd, total_usd}` in dollars. |
| `stripe.recent_donations(limit)` | `Charge.list` (succeeded only) | Each record: `id, amount_usd, created_at, donor_hash, donor_domain, ref_tag, payment_intent`. Donor name + email hashed. |
| `stripe.donations_by_month(months)` | `Charge.list` over trailing-N-month window | Buckets by `YYYY-MM`. |
| `stripe.donations_by_ref(days)` | `Charge.list` over trailing window | Buckets by `metadata.ref` (or `ref_tag` fallback). Charges without a ref bucket as `(no-ref)`. |
| `stripe.year_to_date` | `Charge.list` since Jan 1 | `{year, count, total_usd, average_usd, current_nonprofit}`. Reads `apps/site/_data/support.json` for the nonprofit short name so callers don't need a second tool round-trip. |

## Quirks + dead ends

### `stripe.donations_by_ref` returns mostly `(no-ref)` today
The Stripe Payment Link (`https://buy.stripe.com/00waEEcOp5Ip2PubvFeIw04`, from `apps/site/_data/support.json`'s `current.stripe_donate_url`) does **not** currently set `metadata.ref` on Checkout Sessions, so the resulting charges don't carry a ref tag. Until the donate flow is configured to set metadata (a Stripe Dashboard setting on the Payment Link, plus a server-side hook), this tool returns `(no-ref)` for everything.

The tool ships anyway — Marky's heartbeat description names the limitation explicitly so the model interprets empty buckets correctly.

### Restricted-key permissions are surface-by-surface
The current key allows `/v1/charges` + `/v1/balance` reads but **not** `/v1/checkout/sessions` reads (returns 403 with `Having the 'rak_payment_intent_read', 'rak_checkout_session_read' permissions would allow this request to continue.`). We work entirely from `/v1/charges` because of this.

### Donor PII is hashed at the system boundary
`_normalize_charge()` replaces `billing_details.email` and `.name` with a 32-char sha256 prefix in `donor_hash`, plus an `email_domain` hint for cohort analysis. Raw addresses + names must not propagate. Same rule for any future Stripe tool here.

### Currency: USD only
Every aggregate filters/sums on `currency == "usd"`. The Weekly Thing supporter program is USD-only; if that ever changes, every dollar figure here needs revisiting.

### `Charge.metadata` vs `PaymentIntent.metadata` vs `Checkout.Session.metadata`
Metadata can live on any of three objects in the same flow. Charges inherit from PaymentIntents which inherit from Checkout Sessions. If a Payment Link sets metadata, it propagates down, but only after the Stripe Dashboard configuration is in place (see above). We read `Charge.metadata` directly; if it's empty, no parent traversal happens.

## Limits

- **Rate limit:** Stripe's published global limit is 100 read req/sec; in practice you'll hit account-level smaller caps. We're nowhere close.
- **Cursor pagination:** `Charge.list` returns at most 100 per page; we cap at `max_pages=20` per call to bound runaway iteration on a wide window.

## Site-side usage

`pipeline/content/fetch_emails.py:fetch_stripe_balance()` runs at site build time to populate `apps/site/_data/stats.json`'s `amount_raised` field. Same env var (`STRIPE_API_KEY`) — both consumers share the key.

If the build runs without `STRIPE_API_KEY` set, the site falls back to whatever is already in `stats.json`. The bot, by contrast, raises `RuntimeError` if the key is missing — bot tools are expected to surface errors to the model rather than silently degrade.
