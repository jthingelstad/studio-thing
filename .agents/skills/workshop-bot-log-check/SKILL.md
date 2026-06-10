---
name: workshop-bot-log-check
description: Read the workshop_bot log (`apps/workshop_bot/logs/workshop.log`) for the last N hours and report a concise health snapshot — persona presence, scheduler activity, anomalies (errors/warnings worth attention). Replaces the persistent Monitor task; designed to run on a schedule every couple hours but also useful ad-hoc when something looks off.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# /workshop-bot-log-check — Periodic workshop_bot health snapshot

Look at the workshop_bot log file and report on what's been happening. The default window is **the last 2 hours** (matching the scheduled cadence) — if Jamie asks for a different window ("today", "since 12:00", "last 6h") interpret it and adjust.

The log lives at `/Users/otto/Projects/studio-thing/apps/workshop_bot/logs/workshop.log`. It's a `tail`-friendly text file — never load the whole thing; always grep / awk a window.

## Procedure

### 1. Bound the window

Default window = last 2 hours. Compute the cutoff timestamp as `YYYY-MM-DD HH:MM` (one cron interval back from now). Filter log lines whose leading timestamp is ≥ cutoff. A simple `awk` recipe:

```bash
CUTOFF=$(date -v-2H +"%Y-%m-%d %H:%M")
LOG=/Users/otto/Projects/studio-thing/apps/workshop_bot/logs/workshop.log
awk -v c="$CUTOFF" '$0 >= c' "$LOG" > /tmp/wb_window.log
```

(On Linux, `date -d "2 hours ago"` instead of `date -v-2H`.)

All subsequent greps run against `/tmp/wb_window.log`.

### 2. Bot lifecycle + git SHA

Find the most recent startup audit. The shape is one line like:

```
INFO workshop.bot | startup audit:
**workshop-bot online** — `<sha>` (dirty?)
✓ **Eddy** — #editorial · #workshop · #chatter
✓ **Linky** — #research · #workshop · #chatter
✓ **Marky** — #promotion · #workshop · #chatter
✓ **Patty** — #supporters · #workshop · #chatter
```

If there's a startup audit in the window, note the SHA + when. If there are multiple restarts, note the count.

If you see `stop requested; closing clients...` *without* a matching `startup audit` later, that's an anomaly — the bot is down. Surface it.

```bash
grep -E "startup audit|stop requested" /tmp/wb_window.log
```

### 3. Persona presence

Each persona logs `<Name> online as ...` when it joins Discord. Count one per persona in the window. If all four (Eddy, Linky, Marky, Patty) have an online line *and* the most-recent activity matches each persona's expected cadence, presence is healthy.

```bash
grep -E "INFO    workshop.persona \| (Eddy|Linky|Marky|Patty) online" /tmp/wb_window.log
```

### 4. Scheduler activity

The scheduler logs `firing <job>` then `<job> ok` (or error). Five recurring jobs to expect:

| job | expected cadence |
|---|---|
| `update-draft-daily` | daily 17:00 CT (one fire/day) |
| `linky-pinboard-scan` | every 3h 07:00–22:00 CT (so 1–2 fires per 2-hour window during the day) |
| `linky-feedbin-ingest` | hourly at :35 (2 fires per 2-hour window) |
| `marky-daily-metrics` | daily 19:00 CT (one fire/day) |
| `follow-up-sweep` | hourly at :23 (2 fires per 2-hour window) |

Pull the fire→ok pairs and a one-line job-result for each:

```bash
grep -E "workshop\.scheduler(\.handlers)? \|" /tmp/wb_window.log
```

Look for:
- A job that fired but never logged `ok` → it's stuck or it crashed (check for tracebacks after the firing).
- An hourly-cadence job that didn't fire at all in a 2-hour window → scheduler isn't pumping.

### 5. Job results worth noting

The handler-line message often carries useful information:

- `content_job pinboard-scan -> ok=True: Linky: posted N card(s)` — note the card count
- `content_job feedbin-ingest -> ok=True: feedbin-ingest: <N> new toread bookmark(s)` — flag when N > 0
- `content_job daily-metrics -> ok=True: Marky posted a daily-metrics report` — confirms Marky ran
- `content_job promotion-prep -> ok=True: …` — Marky's promotion drafts (only after `put-to-bed`)
- `content_job follow-up-sweep -> ok=True: (nothing due)` — typical; only surface when something fired

### 6. Anomalies — what to look for

These warrant explicit callout in the report:

- **Any `ERROR` line** — workshop.* errors are real bugs.
- **`WARNING` lines worth surfacing** — cadence violations (`pinboard: standard/all/recent called X.Xs after previous call`), feed-pull failures (`popular feed pull failed`), shard drops (`gateway dropped; will re-login`), `couldn't pin` warnings.
- **Tracebacks** — any line starting with `Traceback (most recent call last):` and the immediately-following frames.
- **Repeated warnings** — if `popular feed pull failed` shows up 2+ times in the window, that's an outage, not a blip.
- **A `couldn't pin <kind> card`** — the bot doesn't have Pin Messages permission in some channel.

```bash
grep -E "ERROR|WARNING|Traceback|^  File " /tmp/wb_window.log
```

Group identical warnings (same logger + same suffix) so the report doesn't repeat the same message ten times — say "popular feed pull failed (4×)" instead.

### 7. Format the report

Output a tight markdown block. Lead with the verdict — ✅ if clean, ⚠️ if something needs attention. Skip empty sections.

```
## workshop_bot · last <window>

**<✅ All clear | ⚠️ N items worth attention>** · <git sha> · personas: <eddy / linky / marky / patty all online | X offline>

### Schedule
- <jobs fired with outcomes; ok→one-liner each>

### Activity
- pinboard-scan: <total cards posted across firings>
- feedbin-ingest: <total new items filed>
- <anything else worth a single line>

### Anomalies  (only if any)
- ⚠️ <one line per anomaly, with timestamp + log excerpt if useful>
```

Keep it to 10-20 lines max. If everything is clean, the whole report should be 5-8 lines: a one-line verdict + the schedule + activity counts.

### 8. When to recommend action

The report is observational by default. Recommend action only when:

- The bot is **down** (most recent `stop requested` with no subsequent `startup audit`) → suggest checking `apps/workshop_bot/scripts/admin.sh status`.
- An **error keeps recurring** (the same Python exception 3+ times in the window) → suggest looking at the traceback.
- The **`feeds.pinboard.in` outage has gone on >12h** (popular feed pull failed across 4+ consecutive scans) → Pinboard is broken on their end, but worth being aware.

Otherwise, just report the snapshot and stop. Periodic noise (intermittent shard reconnects, occasional WARNING from third-party libraries) shouldn't drive recommendations — those are normal weather.

## When invoked ad-hoc

If Jamie types `/workshop-bot-log-check` without args, default 2-hour window. If he asks for a different window in natural language ("check the last 6 hours", "what happened today"), use that window instead.
