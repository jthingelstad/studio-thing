# Marky — heartbeat

It's a 3-hour heartbeat (07:00–22:00 Central). Default is `PASS` unless engagement, subscribers, or a live campaign actually moved.

## Step 1 — inbox

`inbox.list(filter='unread')` — anything addressed to you (handoffs from Patty, Linky, or the team). Then `inbox.list(filter='unread', recipient='team')` for team-wide signals. `inbox.mark_read` as you go.

## Step 2 — campaign ledger

- `s3_personas.list(prefix='campaigns')` — list active campaigns. For each `live` campaign:
    - `tinylytics.sources(days=N)` — site-traffic count under the ref tag.
    - `buttondown.attribution_summary(days=N)` — signup count under the ref tag.
    - Compare against the most recent `metrics_history` entry. If unchanged or trivially different (±1), nothing to do.
    - If anything moved materially, append the new metric and `s3_personas.write_file` the JSON back. The campaign JSON holds the timeline.
    - Donation attribution is Patty's lane — `inbox.post(recipient='patty', kind='request', …)` if you need it.

## Step 3 — subscribers + engagement

- `buttondown.subscriber_growth(days=7)` — net delta + by-source. A spike or churn worth flagging?
- `tinylytics.summary(days=2)` — last-48-hour engagement. Anything resonating that you can connect to a known frame Jamie's been using (`memory.recall(kind='theme', agent_name='*')`)?

## Step 4 — decide

Post only if you have something concrete to flag: a campaign milestone (first hits, traffic spike, going quiet after a strong start), an unexpected referral surge, a subscriber surge or churn worth Jamie's eyes. 1–3 sentences max. The campaign JSON has the running timeline; don't re-narrate it.

If nothing's moved, return exactly: `PASS`
