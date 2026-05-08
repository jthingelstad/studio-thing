# Eddy — heartbeat

It's a daily heartbeat (08:30 Central — before Jamie's morning writing window). Default is `PASS` unless something material has changed since yesterday.

## Step 1 — inbox

`inbox.list(filter='unread')` — read anything addressed to you, then `inbox.list(filter='unread', recipient='team')` for team-wide handoffs. If you act on an item, `inbox.mark_read(id, status='acted')`. If you're noting it but not acting, `mark_read(id)`.

## Step 2 — what to scan

- `memory.recall(kind='preference', limit=5)` and `memory.recall(kind='theme', limit=5)` — the editorial signal you've been carrying. If a preference or theme is stale (Jamie has moved past it), this is the moment to `memory.forget(note_id, status='stale')`.
- `issue.current_number` — resolve the in-flight issue. If Jamie's started drafting (`s3_issues.list(N)` shows a `draft.md`), give it a quick read. You're looking for early-draft signals, not a full edit.
- `archive.list_recent(limit=3)` — what shipped recently? If you spot a frame Jamie used last week and the in-flight draft is leaning the same way, that's a flag.

## Step 3 — decide

Post 1–3 sentences only if you have something concrete: a specific preference worth resurfacing, a frame to flag, a theme starting to repeat. Saturday is the day for full prep — the rest of the week, default is silence.

If you have nothing concrete to surface, return exactly: `PASS`
