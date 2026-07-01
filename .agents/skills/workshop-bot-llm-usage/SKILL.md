---
name: workshop-bot-llm-usage
description: Analyze workshop_bot LLM token usage and cost from the agent_runs SQLite table. Use when Jamie wants to review spend, see cost-by-persona/job/model breakdowns, find expensive jobs, or optimize prompts. Reads apps/workshop_bot/data/workshop.db directly.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# /workshop-bot-llm-usage — Analyze workshop_bot LLM spend

Every workshop_bot agent invocation records its token usage to the `agent_runs` SQLite table (commit `93815f1` and forward). This skill turns those rows into actionable cost analysis.

## What the data looks like

**Database:** `apps/workshop_bot/data/workshop.db`
**Table:** `agent_runs`
**Columns:**

| column | type | meaning |
|---|---|---|
| `id` | INTEGER | autoincrement primary key |
| `agent_name` | TEXT | `eddy`, `linky`, `marky`, `patty`, or `scheduler` |
| `trigger` | TEXT | what kicked it off — `compose-meta:subject`, `pinboard-scan`, `mention`, `scheduled:<job-id>`, etc. See `tools/db.py:AgentRun` docstring for the convention. |
| `status` | TEXT | `success`, `error`, or `pending` (in-flight) |
| `duration_ms` | INTEGER | wall-clock for the run |
| `error` | TEXT | exception summary on failure |
| `records_written` | INTEGER | semantic outcome — 1 = real reply, 0 = PASS / empty |
| `model` | TEXT | e.g., `claude-sonnet-5`, `claude-opus-4-7`, `claude-haiku-4-5-20251001`. NULL when no LLM call ran. |
| `input_tokens` | INTEGER | sum of input tokens across all LLM calls in this run |
| `output_tokens` | INTEGER | sum of output tokens |
| `cache_read_tokens` | INTEGER | prompt-cache hits (90% cheaper) |
| `cache_create_tokens` | INTEGER | prompt-cache writes (25% more expensive than input) |
| `started_at` | TEXT | ISO timestamp |
| `ended_at` | TEXT | ISO timestamp |

Rows where `model IS NULL` are *not* LLM calls — they're the scheduler's outer cron-fire row, or ops jobs (e.g., `goal-achieved`) that don't hit the model. Filter them out of cost analysis with `WHERE model IS NOT NULL`.

## Anthropic pricing (per million tokens, USD)

Keep this in sync with [Anthropic's pricing page](https://www.anthropic.com/pricing) **and** with `apps/workshop_bot/tools/llm/anthropic_client.py` — the in-process source of truth is `anthropic_client.RATES_USD_PER_MTOK` and `anthropic_client.cost_usd(...)`. When rates change, update both.

| model | input | output | cache_read | cache_create |
|---|---|---|---|---|
| `claude-sonnet-5` | $3.00 | $15.00 | $0.30 | $3.75 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | $0.30 | $3.75 |
| `claude-opus-4-7` | $15.00 | $75.00 | $1.50 | $18.75 |
| `claude-haiku-4-5-20251001` | $1.00 | $5.00 | $0.10 | $1.25 |

Costs for a single row:
```
cost_usd = (input * input_rate + output * output_rate
          + cache_read * cache_read_rate + cache_create * cache_create_rate)
          / 1_000_000
```

## How to answer common questions

Use `sqlite3 apps/workshop_bot/data/workshop.db` from the repo root. SELECT into a CTE that joins each row to its model rate, then aggregate.

A reusable rate-table snippet (paste as the leading CTE):

```sql
WITH rates(model, in_rate, out_rate, cr_rate, cc_rate) AS (
  VALUES
    ('claude-sonnet-5',          3.00, 15.00, 0.30, 3.75),
    ('claude-sonnet-4-6',        3.00, 15.00, 0.30, 3.75),
    ('claude-opus-4-7',         15.00, 75.00, 1.50, 18.75),
    ('claude-haiku-4-5-20251001', 1.00,  5.00, 0.10, 1.25)
),
priced AS (
  SELECT
    a.*,
    (COALESCE(a.input_tokens,0)        * r.in_rate
   + COALESCE(a.output_tokens,0)       * r.out_rate
   + COALESCE(a.cache_read_tokens,0)   * r.cr_rate
   + COALESCE(a.cache_create_tokens,0) * r.cc_rate) / 1000000.0 AS cost_usd
  FROM agent_runs a
  LEFT JOIN rates r ON a.model = r.model
  WHERE a.model IS NOT NULL
)
SELECT ...
```

### "How much did we spend this week?"

```sql
-- [prepend the CTE above]
SELECT
  ROUND(SUM(cost_usd), 2) AS total_usd,
  COUNT(*) AS runs,
  SUM(input_tokens) AS in_tok,
  SUM(output_tokens) AS out_tok
FROM priced
WHERE started_at >= datetime('now', '-7 days');
```

### "Cost by persona this week"

```sql
SELECT
  agent_name,
  COUNT(*) AS runs,
  ROUND(SUM(cost_usd), 2) AS usd,
  ROUND(AVG(cost_usd), 4) AS avg_usd
FROM priced
WHERE started_at >= datetime('now', '-7 days')
GROUP BY agent_name
ORDER BY SUM(cost_usd) DESC;
```

### "Cost by job/trigger"

```sql
SELECT
  trigger,
  COUNT(*) AS runs,
  ROUND(SUM(cost_usd), 2) AS usd,
  ROUND(AVG(cost_usd), 4) AS avg_usd,
  ROUND(AVG(input_tokens)) AS avg_in_tok,
  ROUND(AVG(output_tokens)) AS avg_out_tok
FROM priced
WHERE started_at >= datetime('now', '-7 days')
GROUP BY trigger
ORDER BY SUM(cost_usd) DESC;
```

### "Cost by model"

```sql
SELECT
  model,
  COUNT(*) AS runs,
  ROUND(SUM(cost_usd), 2) AS usd,
  SUM(input_tokens) AS in_tok,
  SUM(output_tokens) AS out_tok
FROM priced
WHERE started_at >= datetime('now', '-7 days')
GROUP BY model;
```

### "What were the most expensive single runs?"

```sql
SELECT
  id, agent_name, trigger, model,
  input_tokens, output_tokens,
  ROUND(cost_usd, 4) AS usd,
  started_at
FROM priced
WHERE started_at >= datetime('now', '-7 days')
ORDER BY cost_usd DESC
LIMIT 10;
```

### "How effective is prompt caching?"

```sql
SELECT
  trigger,
  COUNT(*) AS runs,
  SUM(input_tokens) AS in_tok,
  SUM(cache_read_tokens) AS cache_read,
  ROUND(
    100.0 * SUM(cache_read_tokens)
    / NULLIF(SUM(input_tokens) + SUM(cache_read_tokens), 0),
    1
  ) AS cache_hit_pct
FROM priced
WHERE started_at >= datetime('now', '-7 days')
  AND model IS NOT NULL
GROUP BY trigger
HAVING runs >= 3
ORDER BY cache_hit_pct DESC;
```

A high cache_hit_pct on a trigger means we're paying $0.30/M tokens instead of $3/M — prompt is being reused across runs (great). A low pct on a frequent trigger is a tuning opportunity (system prompt restructure, or the LLM call's input isn't stable enough for the cache to fire).

### "Show me PASS vs real-reply cost split"

Useful for jobs that PASS often. A high cost-on-PASS rate means we're paying to *not* post — worth seeing if the gate can be moved earlier.

```sql
SELECT
  trigger,
  SUM(CASE WHEN records_written = 0 THEN 1 ELSE 0 END) AS pass_runs,
  SUM(CASE WHEN records_written > 0 THEN 1 ELSE 0 END) AS post_runs,
  ROUND(SUM(CASE WHEN records_written = 0 THEN cost_usd ELSE 0 END), 2) AS pass_usd,
  ROUND(SUM(CASE WHEN records_written > 0 THEN cost_usd ELSE 0 END), 2) AS post_usd
FROM priced
WHERE started_at >= datetime('now', '-7 days')
GROUP BY trigger
ORDER BY pass_usd DESC;
```

## Surfacing the data

When Jamie invokes this skill:

1. **Default behavior:** run the "spend this week" query first — gives a single dollar number to anchor. Then surface the by-persona, by-trigger, and most-expensive-runs breakdowns. Lead with what *changed* if you can see the prior week's data too.

2. **If he asks something specific** ("what did Marky cost?", "how expensive is pinboard-scan?"), pick the right query above (or compose a new one) and run it.

3. **Format the output as a markdown table** when there are >1 row and >2 columns. Single-number answers go inline. Don't paste raw SQL output without parsing.

4. **Always note the time window.** "Last 7 days" or "since 2026-05-13" — be explicit so Jamie knows what's covered.

5. **Suggest optimizations when you spot them.** Examples worth flagging without being asked:
   - A trigger with high `pass_usd` (paying for PASSes) — maybe move the gate earlier.
   - A trigger using opus where sonnet would do — check the model selection logic.
   - A trigger with low cache_hit_pct on >10 runs/week — restructure the prompt so the leading content is stable.
   - A trigger that's >50% of weekly cost — biggest single optimization target.

## Cost-of-running ballparks

Useful intuition (per model, per typical run):

- **Haiku** for a 3,000-token input + 500-token output: ~$0.005 ($5 per 1,000 runs).
- **Sonnet** for the same: ~$0.017 (~$17 per 1,000 runs).
- **Opus** for the same: ~$0.083 (~$83 per 1,000 runs).

With prompt caching at 90% on the system prompt (likely the steady state for personas with stable identity prompts): Sonnet drops to ~$0.008 per run.

## Gaps in coverage (worth knowing)

These LLM calls *aren't* tracked in agent_runs and won't show in this analysis:

- **`tools/alt_text.py`** — direct vision-model calls for image alt-text during `update-draft`. Caps at 15 calls per draft refresh, Sonnet, ~3kB images. Rough estimate: ~$0.03 per draft refresh, so ~$0.20/wk during the issue window.
- **`apps/thingy_bridge/jobs/watch.py`** — the conversation-assessment LLM call in the separate `thingy_bridge` process. Different SQLite (`apps/thingy_bridge/data/thingy_bridge.db`), no `agent_runs` table there today. Roughly: one Sonnet call per new reader conversation, hourly cron.

If the analysis suggests these are material, flag them as a follow-up — the same `AgentRun.record_meta` pattern can extend.
