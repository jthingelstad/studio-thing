# Pinboard

Bookmark queue. Used by the workshop bot's Linky as the working set for newsletter curation: Jamie saves to Pinboard during the week, marks promising items as "to read", and Linky drains the queue Friday afternoon.

References: <https://www.pinboard.in/api/> (v1, stable, what we use) and <https://www.pinboard.in/api/v2/overview> (v2, still DRAFT — see "v2 status" below).

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

Base URL: `https://api.pinboard.in/v1`. All requests include `format=json`.

### `GET /posts/recent`
Most recent N bookmarks (regardless of read state). Params: `count` (default 15, max 100), `tag` (optional filter, up to 3).

### `GET /posts/all`
The full bookmark archive. We always pass `toread=yes` to scope to the unread queue. Params: `results` (max 1000), `tag` (up to 3), `fromdt`, `todt`, `start`, `meta`.

### `GET /posts/update`
Returns the ISO timestamp of the user's most recent bookmark mutation. Cheap freshness gate — call this before paying the 5-min toll on `/posts/all`.

### `GET /posts/get`
Lookup-by-URL (or by tag/date). We pass `url=...&meta=yes` for "did Jamie already save this?" checks. Returns `{date, user, posts: [...]}` — empty `posts` means not saved.

### `GET /posts/suggest`
Tag suggestions for a URL — site-wide popular + Jamie's personal recommended. Pinboard returns a list of two single-key dicts (`[{popular: [...]}, {recommended: [...]}]`); we flatten to `{popular, recommended}`.

### `GET /posts/dates`
Bookmark counts per day across the whole archive. Optional `tag` filter.

### `GET /tags/get`
Full tag inventory across every bookmark — `{tag: count, ...}`. Distinct from our `tag_summary`, which only scans the unread pile.

### `GET /posts/add`
Create or update a bookmark. **Yes, it's `GET` even though it mutates** — Pinboard never adopted REST verbs. Params: `url`, `description` (= title), `extended` (= body), `tags` (space-separated, max 100), `toread` (yes/no), `shared` (yes/no), `replace` (yes/no). We always send `replace=no` from the bot so we can never silently overwrite Jamie's existing entry.

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
| `pinboard.update_check()` | `/posts/update` | None — returns ISO timestamp. Cheap freshness gate. |
| `pinboard.lookup_url(url)` | `/posts/get?url=…&meta=yes` | None — returns `{date, user, posts: […]}`; empty posts means not saved |
| `pinboard.suggest_tags(url)` | `/posts/suggest?url=…` | None — returns `{popular: […], recommended: […]}` |
| `pinboard.archive_tags(top)` | `/tags/get` | None — full tag inventory across whole archive (not unread slice). Returns top N by count. |
| `pinboard.bookmark_dates(tag?)` | `/posts/dates` | None — `{YYYY-MM-DD: count, …}`, optionally tag-filtered |
| `pinboard.save(url, title, …)` | `/posts/add` (`replace=no`, `toread=true` defaults) | **Mutating** — saves to Jamie's Pinboard. Linky should `lookup_url` first to dodge duplicate-save errors. |

## Quirks + dead ends

### `/posts/add` is `GET`, not `POST`
Pinboard's whole API is GET-based. Mutations go through query strings. Our `posts_add()` ships `replace=no` by default so the bot can never silently overwrite — duplicate URLs return `result_code="item already exists"` and the existing bookmark is untouched.

### Tag string format
Tags are space-separated in a single string (not an array). Per-tag rules: max 255 chars, no commas or whitespace inside a tag, periods prefix private tags. Max 100 tags per bookmark. `pinboard.tag_summary` and `pinboard.archive_tags` split on whitespace.

### Field names are quirky
Pinboard's API uses non-obvious field names that we normalize:
- `description` (Pinboard) → `title` (us). The bookmark's title.
- `extended` (Pinboard) → `description` (us). The longer body text.
- `time` → `added`. ISO timestamp.
- `toread` → `toread` boolean.
- We also surface `shared`, `hash` (change-detection signature), and `meta` from the Pinboard payload when present.

The mapping happens in `normalize_post()` in `systems/pinboard/client.py`.

### `posts/suggest` shape oddity
Pinboard returns a list of two single-key dicts (`[{popular: [...]}, {recommended: [...]}]`) instead of a single object. Client flattens this — callers always get `{popular, recommended}`.

### `posts/get` quirk
The response omits the per-post `tag` attribute that Delicious had — tags come through in the per-post `tags` field instead. Don't be confused if you're reading the v1 docs and looking for `tag`.

### Popular feed has no auth
Means anyone can poll it. We fetch it with a custom User-Agent (`WeeklyThing-WorkshopBot/1.0`) so the maintainer can identify the traffic if needed.

## Limits

Pinboard's documented per-endpoint cadence caps (v1 docs, "Rate Limits"):

- **Standard endpoints** (`/posts/update`, `/posts/get`, `/posts/suggest`, `/posts/dates`, `/posts/add`, `/tags/get`, `/notes/*`): **1 request / 3 seconds**.
- **`/posts/recent`**: **1 request / minute**.
- **`/posts/all`**: **1 request / 5 minutes**.
- **`/posts/recent` `count` cap**: 100 (default 15).
- **`/posts/all` `results` cap**: 1000.

Pinboard returns `429 Too Many Requests` with a `Retry-After` header when you push past these. The client logs both before re-raising — easy to grep in workshop_bot logs.

We don't enforce client-side blocking — heartbeat cadences (every 6 h) sit comfortably below all the caps. The client does emit a warning log line if it sees a back-to-back call faster than the documented cadence (caught by `_note_cadence` in `client.py`); useful for spotting accidental tight loops in agent code.

## v2 status

The v2 overview page itself is marked **DRAFT**. v2 promises nicer affordances (header-based auth via `X-Auth-Token`, JSON everywhere, true REST verbs, account-level 400 req / 15 min budget with `X-Requests-Remaining` headers, structured search, delta sync, batch ops). Until the spec exits draft we stay on v1.

The v1 tool surface above already covers most v2-only conveniences: `lookup_url` ≈ v2 `bookmarks/?url=`, `suggest_tags` ≈ v2 `url/suggest`, `archive_tags` ≈ v2 `tags/`, `update_check` ≈ v2 `last_update/`. A future v2 migration would mostly be re-targeting URLs and unwrapping a `status: ok` envelope, not rebuilding our mental model.

## Site-side usage

None. Pinboard is purely a bot-side integration.
