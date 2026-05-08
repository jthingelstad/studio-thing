# Tinylytics

Privacy-friendly site analytics for `weekly.thingelstad.com`. Used by the workshop bot (`apps/workshop_bot/systems/tinylytics/`) for Marky's engagement reporting and on the published site for click/event tracking.

Reference docs: <https://tinylytics.app/docs/api.md> · OpenAPI: <https://tinylytics.app/api/v1/openapi.json> · llms.txt index: <https://tinylytics.app/llms.txt>

## Auth + identifiers

```
Authorization: Bearer tly-fa-...    (full access)
Authorization: Bearer tly-ro-...    (read-only)
```

Three env vars, each used for a different thing — **don't mix them up**:

| Env var | Example | Used for |
|---|---|---|
| `TINYLYTICS_API_KEY` | `tly-fa-…` / `tly-ro-…` | Bearer token for the REST API |
| `TINYLYTICS_SITE_ID` | `3063` (numeric) | Path segment in `/api/v1/sites/<id>/...` — the API access ID |
| `TINYLYTICS_SITE_UID` | `a2YQr3ZMqkySNYSwz4uF` (hash) | The browser-script identifier (used by the pixel `<script>` tag on the site). **Not used by the workshop bot.** |

Passing the UID to the API path returns **HTTP 500** — that's the symptom we hit in May 2026. The two identifiers look interchangeable but aren't; the UID is a public hash for the browser pixel, the ID is the row PK for API access.

If auth is missing or wrong, the API redirects to the marketing HTML page (200 with `<!DOCTYPE html>`). It does **not** return a 401 — be ready for the response to look like a login page when the Bearer token is bad.

## Endpoints we use

Base URL: `https://tinylytics.app/api/v1`. (NOT `/api/v2` — the v2 surface in the original `tools/tinylytics.py` was a fabrication; nothing on tinylytics.app responds to it.)

### `GET /sites`
Lists every site this API key can read. Each entry: `id, uid, url, label, lifetime_hits, lifetime_unique_hits, lifetime_kudos, active, public, created_at, updated_at`. Useful for finding the right `id` if you only have a domain.

### `GET /sites/:id/hits`
The workhorse. Returns either individual hit rows or grouped aggregates depending on params.

Query params:
- `start_date`, `end_date` — `YYYY-MM-DD`. Window is **inclusive on both ends**. Hard limit: 730 days.
- `time_zone` — `utc` (default) or `user`.
- `country`, `path`, `referrer` — filters. **`path` is exact match, not partial** (despite docs claiming "partial"). `path=email` matches nothing; `path=/email/346/` matches the full path.
- `grouped=true` — switch to aggregated mode.
- `group_by` — `path | country | referrer | browser_name | platform_name`.
- `page`, `per_page` — pagination. `per_page` max 1000.

Response shape (ungrouped):
```json
{
  "hits": [
    {"id": ..., "url": ..., "path": "/", "referrer": "", "country": "US",
     "browser_name": "Safari", "platform_name": "macOS", "is_mobile": null,
     "source": null, "created_at": "..."}
  ],
  "pagination": {"current_page": 1, "per_page": 100, "total_count": 2059, "total_pages": 21},
  "filters": {...}
}
```

Response shape (grouped):
```json
{
  "grouped_hits": [
    {"path": "/email/346/", "views": 1384, "unique_views": 370}
  ],
  "pagination": {...},
  "filters": {...}
}
```

**Field shape varies by `group_by`:**
- `group_by=path` → entries have `path`, `views`, `unique_views`.
- everything else → entries have `<group_field>`, `hit_count`. (E.g. `group_by=referrer` returns `{referrer, hit_count}`.)

For a cheap total-count over a window: `?per_page=1` and read `pagination.total_count` from the response. Don't paginate just to count.

### `GET /sites/:id/leaderboard`
**All-time** path ranking with caching — does **not** accept `start_date`/`end_date`. Returns `{leaderboard: [{path, total_hits, unique_hits, percentage}], site, pagination, cache_info, filters}`.

Path filter on this endpoint **is** partial (case-insensitive prefix-ish), unlike `/hits`'s exact match. `path=email` returns all `/email/*` paths.

We don't ship a tool for this surface today — the windowed `tinylytics.top_pages` covers the more common need.

### `GET /sites/:id/kudos`
Reads the kudos heart-button records (per-path, with date filters). Not currently exposed as a workshop-bot tool.

## Tool surface (workshop bot)

What the dotted tools in `apps/workshop_bot/systems/tinylytics/server.py` actually call:

| Tool | Endpoint | Notes |
|---|---|---|
| `tinylytics.summary(days)` | three calls: ungrouped `/hits` (for `total_count`), grouped-by-path `/hits`, grouped-by-referrer `/hits` | Returns `{days, total_hits, top_pages, referrers}`. Each sub-call is wrapped so a single upstream failure doesn't blank the whole report. |
| `tinylytics.top_pages(days, limit)` | `/hits?grouped=true&group_by=path&start_date=...&end_date=...` | Returns the raw `grouped_hits` list. |
| `tinylytics.referrers(days, limit)` | `/hits?grouped=true&group_by=referrer&start_date=...&end_date=...` | Same. `referrer` may be `null` (direct visit) or `""` (header stripped). |

## Quirks + dead ends

### Tinylytics does not capture query strings
The `path` field on a hit is the URL path component **only**. A landing-page hit at `https://weekly.thingelstad.com/?ref=dd-2026-05-15` is recorded as `path = "/"` — the `?ref=…` part is dropped before storage. **Implication:** ref-campaign attribution can't run through Tinylytics. Use `stripe.donations_by_ref` and Buttondown subscriber `metadata.ref` instead.

(There's no per-link click breakdown either: clicks register as ordinary hits on the destination page, with the `referrer` field set to the source page. Aggregating "clicks on link X from page Y" requires walking individual hits.)

### `path` filter on `/hits` is exact, not partial
Docs say partial. Live behavior: `path=email` returns 0 hits even when there are thousands of `/email/*` paths. `path=/email/346/` works. If you need partial matching, fall back to `/leaderboard?path=…` (which IS partial) and accept the "all-time" scope, or fetch grouped and filter client-side.

### Custom events have no read endpoint
The site uses Tinylytics events extensively (`data-tinylytics-event="support.donate"` etc.). These are **POST-only** into the system; the API exposes no way to read aggregated event counts back out. We initially shipped a `tinylytics.events` tool that was a fabrication; it was dropped in May 2026.

### Bad auth returns the marketing site, not 401
A wrong/expired Bearer token causes the request to redirect to the marketing landing page — you get 200 + `<!DOCTYPE html>` + a CSRF meta tag instead of the JSON 401 you'd expect. If `resp.json()` is throwing "Expecting value: line 1 column 1", check the auth before debugging the endpoint.

### `tinylytics.app` vs `tinylytics.app/api/v1`
`/api/v2/...` paths return the marketing HTML (effectively a 404-via-redirect). The current API is `/api/v1`. The `v2` URL pattern in the original `tools/tinylytics.py` was a fabrication; it never worked.

## Limits

- **Rate limit:** 1000 requests / hour / API key. Each `tinylytics.summary` call burns 3 requests.
- **Date range:** 730 days max on `/hits` (analytics window cap).
- **Pagination:** `per_page` max 1000.

## Site-side usage

The published site uses Tinylytics for browser-side hits + custom events:
- Pixel script tag, identified by `TINYLYTICS_SITE_UID` (the hash, not the numeric ID).
- `data-tinylytics-event="<category>.<action>"` attributes on links/buttons fire events. See `apps/site/librarian.njk` and `apps/site/support.njk` for the conventions.
- Currently tracked event categories (non-exhaustive): `librarian.*`, `search.*`, `support.*`.

Reading those events back from the bot side is **not possible** via the current API — events are write-only from the SDK's perspective.
