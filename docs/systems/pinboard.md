# Pinboard

Bookmark queue. Used by the workshop bot's Linky as the working set for newsletter curation: Jamie saves to Pinboard during the week, marks promising items as "to read", and Linky drains the queue Friday afternoon.

Reference: <https://www.pinboard.in/api>.

## Auth + identifiers

Single env var:

```
PINBOARD_API_TOKEN=<username>:<HEX>
```

Token format is `username:HEX` — both pieces are needed because:
- Auth is `?auth_token=<full_token>` on every request (Pinboard doesn't use Bearer headers).
- The username is parsed out for building per-user bookmark permalinks (`https://pinboard.in/u:<user>/b:<md5(url)>/`).

If only the HEX part is present (no `username:` prefix), `bookmark_url()` returns empty and Linky's "open in Pinboard" links break.

## Endpoints we use

Base URL: `https://api.pinboard.in/v1`.

### `GET /posts/recent`
Most recent N bookmarks (regardless of read state). Params: `count` (max 100), `tag` (optional filter), `format=json`.

### `GET /posts/all`
The full bookmark archive. We always pass `toread=yes` to scope to the unread queue. Params: `results` (max 1000), `tag`, `fromdt`, `format=json`.

### Popular feed (RSS, not REST)

```
https://feeds.pinboard.in/rss/popular/
```

No auth. Public discovery surface — Pinboard's site-wide popular bookmarks. We parse it with BeautifulSoup (XML mode) and extract `title, link, description, dc:creator`.

## Tool surface (workshop bot)

| Tool | Endpoint | Side effect |
|---|---|---|
| `pinboard.recent(count)` | `/posts/recent` | Upserts each into SQLite `link_candidates` |
| `pinboard.unread(limit, tag)` | `/posts/all?toread=yes` | Same |
| `pinboard.popular(limit)` | RSS feed | None — public surface |
| `pinboard.stored_recent(limit)` | SQLite `link_candidates` | None — read-only, no API call |
| `pinboard.tag_summary(limit, top)` | `/posts/all?toread=yes` | Aggregates space-separated tag field; returns `{total_items, top_tags: [{tag, count}, …]}` |

## Quirks + dead ends

### Pinboard rate limits are conservative
Public docs say 1 req/sec on `/posts/all`. We don't currently throttle, but we cap `linky-heartbeat` at every 6 hours partly for this reason. If we ever shorten to 3h, add caching to `pinboard.popular` (the popular RSS isn't rate-limited but we'd want the cache anyway).

### Field names are quirky
Pinboard's API uses non-obvious field names that we normalize:
- `description` (Pinboard) → `title` (us). The bookmark's title.
- `extended` (Pinboard) → `description` (us). The longer body text.
- `time` → `added`. ISO timestamp.
- `toread` → `toread` boolean.

The mapping happens in `normalize_post()` in `systems/pinboard/client.py`.

### `tags` is a single space-separated string
Not an array. `pinboard.tag_summary` splits on whitespace.

### Popular feed has no auth
Means anyone can poll it. We fetch it with a custom User-Agent (`WeeklyThing-WorkshopBot/1.0`) so the maintainer can identify the traffic if needed.

## Limits

- **Rate limit:** 1 req/sec on `/posts/all`; 1 req/min on lookup-style endpoints. We don't enforce client-side throttling — be conservative with concurrency.
- **`/posts/recent` count cap:** 100.
- **`/posts/all` results cap:** 1000.

## Site-side usage

None. Pinboard is purely a bot-side integration.
