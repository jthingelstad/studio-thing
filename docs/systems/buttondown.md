# Buttondown

Newsletter publishing platform. The site pipeline uses it for content sync (`pipeline/content/`); the workshop bot's Marky uses it for subscriber + sent-email engagement reads (`apps/workshop_bot/systems/buttondown/`).

Reference: <https://docs.buttondown.com/api>.

## Auth + identifiers

```
Authorization: Token <BUTTONDOWN_API_KEY>
```

Single env var, simple. No "ID vs UID" trap like Tinylytics — there's just the API key and resource ids returned by the API itself (e.g. email ids `em_…`, subscriber ids `sub_…`).

## Endpoints we use

Base URL: `https://api.buttondown.com/v1`.

### `GET /subscribers`
Paginated list of subscribers. Query params: `page_size` (max 100), `type` (filter; values include `regular`, `premium`, `unsubscribed`), `ordering` (e.g. `-creation_date`). Response: `{count, next, previous, results: [...]}` — standard DRF shape.

Each subscriber record includes (among many other fields): `id`, `email_address`, `type`, `source`, `creation_date`, `unsubscription_date`, `churn_date`, `metadata`, `tags`, `referrer_url`, `utm_*`. **The site relays `?ref=<tag>` from URLs into `metadata.ref`** (via the c7dd173 commit) — that's the canonical place to read campaign attribution for new signups.

For a cheap count: `?page_size=1` and read `count`.

### `GET /emails`
Sent emails, paginated. Each row carries the `analytics` field **inline** with `recipients, deliveries, opens, clicks, unsubscriptions, subscriptions, replies, page_views_*, complaints, …`. No separate endpoint needed for engagement; just fetch the list.

### `GET /emails/{id}/analytics`
Returns the same dict that's already on the inline `analytics` field. Useful for cheap targeted queries.

## Tool surface (workshop bot)

| Tool | Endpoint | Notes |
|---|---|---|
| `buttondown.counts` | three `/subscribers?page_size=1` calls | Returns `{total, premium, unsubscribed}` — total / paid / lifetime-churn counts. |
| `buttondown.list_subscribers(limit, type)` | `/subscribers?ordering=-creation_date` | Newest first; emails hashed on the way out (see PII). |
| `buttondown.recent_unsubscribes(limit)` | `/subscribers?type=unsubscribed&ordering=-creation_date` | Same shape. |
| `buttondown.subscriber_sources(days)` | iterates `/subscribers?ordering=-creation_date`, stops at window boundary | Aggregates `source` field. |
| `buttondown.subscriber_growth(days)` | walks new + unsubscribed lists | Returns `{added, churned, net, by_source}`. |
| `buttondown.list_recent_emails(limit)` | `/emails?ordering=-publish_date` | Returns id, subject, send timestamps + inline engagement. No body. |
| `buttondown.email_engagement(email_id)` | `/emails/{id}` (which carries `analytics` inline) | Returns the engagement dict. |

## Quirks + dead ends

### No per-link click breakdown
`analytics.clicks` is a single integer over the whole email. The Buttondown API does not expose per-link click counts. We probed `/emails/{id}/clicks` and `/clicks?email_id=…` — both 404. If you need per-link, you'd have to set up redirect tracking yourself (or use a separate tool).

### PII never leaves `systems/buttondown/`
Every model-facing payload runs through `_normalize`, which replaces `email_address` with `email_hash` (sha256 prefix) + `email_domain` (cohort hint). Raw addresses must not propagate. Same rule for any future tool here.

### No webhook listener yet
`subscriber_events_seen` exists in SQLite for a future webhook integration; today subscriber telemetry is pull-based via the API.

## Limits

- **Rate limit:** 600 req/min (per the project config memory; see Buttondown docs for the authoritative figure).
- **Pagination:** `page_size` max 100; we cap our pages at 20 in `_iter_subscribers` so one runaway loop can't burn an account budget.
- **Image fields:** Buttondown auto-derives `image` from a number of inputs; you can set it via `metadata.image` or directly. Not relevant to read-only bot usage.

## Related

- Pipeline-side fetcher: `pipeline/content/fetch_emails.py` (uses `stripe.Balance.retrieve()` for the support-amount field, not Buttondown).
- Site stylesheet for the published email: `content/buttondown/newsletter/buttondown-email.css`. Paste into Buttondown's Custom CSS field; the site copy has system-font fallbacks since most email clients don't load remote fonts.
- The newsletter `domain` field in Buttondown settings **must stay empty**, not set to `weekly.thingelstad.com` — setting it confirms the custom domain and 404s the marketing flow at the same time. (See `project_buttondown_custom_domain` memory.)
