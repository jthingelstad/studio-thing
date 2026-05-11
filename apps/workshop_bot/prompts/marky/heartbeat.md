# Marky — heartbeat

It's a 3-hour heartbeat (07:00–22:00 Central). Default is `PASS` unless engagement, subscribers, or a live campaign actually moved.

## Step 1 — subscribers + engagement

- `buttondown__subscriber_growth(days=7)` — net delta + by-source. A spike or churn worth flagging?
- `tinylytics__summary(days=2)` — last-48-hour engagement. Anything resonating that you can connect to a known frame Jamie's been using (`memory__recall(kind='theme', agent_name='*')`)?

## Step 2 — campaigns

- `buttondown__attribution_summary(days=N)` and `tinylytics__sources(days=N)` — read campaign-ref counts. If a live placement is trending materially above or below where you'd expect, that's worth a flag. (The campaign ledger is moving to SQLite — see `daily-metrics` once it lands.)

## Step 3 — decide

Post only if you have something concrete to flag: a campaign milestone (first hits, traffic spike, going quiet after a strong start), an unexpected referral surge, a subscriber surge or churn worth Jamie's eyes. 1–3 sentences max.

If nothing's moved, return exactly: `PASS`
