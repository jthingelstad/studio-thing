-- Workshop Bot SQLite schema. Idempotent — safe to re-run.

CREATE TABLE IF NOT EXISTS agent_outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_name TEXT NOT NULL,
  output_type TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata TEXT,
  status TEXT DEFAULT 'ready',
  created_at TEXT DEFAULT (datetime('now')),
  related_issue INTEGER
);

CREATE INDEX IF NOT EXISTS idx_agent_outputs_agent_created
  ON agent_outputs(agent_name, created_at DESC);

CREATE TABLE IF NOT EXISTS link_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  title TEXT,
  description TEXT,
  pinboard_tags TEXT,
  linky_summary TEXT,
  linky_themes TEXT,
  archive_resonance TEXT,
  status TEXT DEFAULT 'unpublished',
  pinboard_added TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  used_in_issue INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_link_candidates_url
  ON link_candidates(url);

CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_name TEXT NOT NULL,
  trigger TEXT NOT NULL,
  status TEXT NOT NULL,
  duration_ms INTEGER,
  error TEXT,
  records_written INTEGER,
  started_at TEXT DEFAULT (datetime('now')),
  ended_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_started
  ON agent_runs(agent_name, started_at DESC);

-- Agent memory — notes a persona wants to carry forward beyond the
-- conversation in any one Discord thread. Shared across personas (by
-- design — Eddy can read what Patty observed, Marky can see what Linky
-- noticed) and attributed via agent_name.
CREATE TABLE IF NOT EXISTS agent_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_name TEXT NOT NULL,
  kind TEXT NOT NULL,                          -- 'preference', 'observation',
                                               -- 'todo', 'context', 'theme'
  key TEXT,                                    -- short label, optional
  content TEXT NOT NULL,
  related_issue INTEGER,
  status TEXT NOT NULL DEFAULT 'active',       -- 'active', 'resolved', 'stale'
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT,
  metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_notes_agent_status_created
  ON agent_notes(agent_name, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_notes_kind_status
  ON agent_notes(kind, status);

-- Subscriber activity Marky surfaces — populated either by webhook (later)
-- or by a periodic Buttondown poll. Email is hashed before storage so we
-- never persist raw email addresses for the supporter program tracking.
CREATE TABLE IF NOT EXISTS subscriber_events_seen (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL,                   -- Buttondown subscriber id
  email_hash TEXT NOT NULL,
  event_type TEXT NOT NULL,                    -- 'created', 'unsubscribed',
                                               -- 'churned'
  event_date TEXT NOT NULL,
  metadata TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriber_events_external
  ON subscriber_events_seen(external_id, event_type);

-- URLs Linky has already shown to Jamie from Pinboard's popular feed.
-- The popular handler runs every 6 hours; we dedup against this table so
-- Jamie only sees each item once regardless of how long it stays popular.
CREATE TABLE IF NOT EXISTS pinboard_popular_seen (
  url TEXT PRIMARY KEY,
  title TEXT,
  posted_by TEXT,
  judged_interesting INTEGER,                  -- 1 / 0 / NULL (not judged yet)
  judgment_note TEXT,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Items from Jamie's Pinboard "to read" pile that Linky has already
-- researched (URL fetched, summary written). Lets the research handler
-- pick up where it left off across runs.
CREATE TABLE IF NOT EXISTS pinboard_research_done (
  url TEXT PRIMARY KEY,
  title TEXT,
  summary TEXT,
  confidence TEXT,                             -- ✦ / · / ⊘
  fit_note TEXT,
  researched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Thingy bridge — cached Lambda session tokens, one per Discord user.
-- The bridge mints a token via /auth?action=discord_bridge, stores it
-- here, and reuses it until expires_at approaches.
CREATE TABLE IF NOT EXISTS thingy_tokens (
  discord_user_id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  expires_at INTEGER NOT NULL,                 -- epoch seconds (matches Lambda payload.exp)
  issued_at TEXT NOT NULL DEFAULT (datetime('now')),
  -- Profile snapshot returned by the Lambda's /auth response. JSON of
  -- { returning, last_seen_at, turn_count, prior_session_summaries,
  --   current_session_questions }. Updated whenever a new token is minted.
  profile TEXT,
  -- When we last greeted this user with a "welcome back" blurb. Lets
  -- the bridge avoid re-greeting on every fresh-token mint.
  last_welcomed_at TEXT
);

-- Thingy bridge — one row per question forwarded to the Lambda. Lets
-- the reaction handler look up which Lambda request_id corresponds to
-- a given Discord bot reply when Jamie reacts 👍/👎 to it.
CREATE TABLE IF NOT EXISTS thingy_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_user_id TEXT NOT NULL,
  discord_message_id TEXT NOT NULL,
  bot_response_message_id TEXT,
  request_id TEXT,
  question TEXT NOT NULL,
  status TEXT NOT NULL,                        -- 'pending' / 'ok' / 'error'
  error TEXT,
  duration_ms INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_thingy_requests_bot_msg
  ON thingy_requests(bot_response_message_id);

-- Decommissioned tables — dropped here so a long-lived DB converges with
-- a fresh install. (Idempotent: no-op if they never existed.)
--   agent_inbox    — typed inter-agent handoffs; the content-loop redesign
--                    is closed-loop with no agent-to-agent messaging
--                    (Jamie is the integrator).
--   analytics      — superseded by campaign_metrics + the live tinylytics/
--                    buttondown surfaces; never populated.
--   supporter_events / channel_routes — reserved in the original sketch,
--                    never wired; the goals table + env-var channel ids
--                    cover the same ground.
DROP INDEX IF EXISTS idx_agent_inbox_recipient;
DROP TABLE IF EXISTS agent_inbox;
DROP TABLE IF EXISTS analytics;
DROP TABLE IF EXISTS supporter_events;
DROP TABLE IF EXISTS channel_routes;

-- Issue windows — operator-set publishing schedule. Replaces the prior
-- auto-derived in-flight resolver (which combined S3 folder names with
-- the latest published issue). Jamie sets the active window via the
-- ``/workshop issue start`` slash command; agents read it via
-- ``issue__current_window`` and historical metadata via
-- ``issue__list_windows``.
--
-- Date semantics:
--   - pub_date is the Saturday the issue is published (display).
--   - end_date = pub_date - 1 day (content cutoff).
--   - start_date = end_date - day_count days (previous issue's cutoff;
--     so day_count=7 captures the seven days strictly after start_date
--     up to and including end_date).
--   - day_count is usually 7; 14 for double issues.
--
-- Exactly one row may have is_active=1; enforced by the partial unique
-- index below.
CREATE TABLE IF NOT EXISTS issue_windows (
  issue_number INTEGER PRIMARY KEY,
  pub_date TEXT NOT NULL,                        -- YYYY-MM-DD, Saturday
  end_date TEXT NOT NULL,                        -- YYYY-MM-DD = pub_date - 1
  start_date TEXT NOT NULL,                      -- YYYY-MM-DD = end_date - day_count
  day_count INTEGER NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 0,
  set_at TEXT NOT NULL DEFAULT (datetime('now')),
  set_by TEXT
);

-- At most one active window at a time.
CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_windows_active_unique
  ON issue_windows(is_active) WHERE is_active = 1;

-- Job locks — single-asset serialization for the jobs pipeline. A job
-- acquires a row per file it intends to write before starting; another
-- job that wants the same file sees the row and bails with an "already
-- running" message. Released on completion (success or failure). A lock
-- whose pid is no longer a live process is treated as stale and stolen.
CREATE TABLE IF NOT EXISTS job_locks (
  asset TEXT PRIMARY KEY,                        -- e.g. '458/draft.md'
  job TEXT NOT NULL,                             -- job name holding the lock
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  pid INTEGER NOT NULL
);

-- Draft digests — one row per update-draft run, so Eddy's post-update
-- review can compute "since yesterday: +2 Notable, +380 words, intro now
-- present" rather than re-summarizing the whole draft.
CREATE TABLE IF NOT EXISTS draft_digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue INTEGER NOT NULL,
  ran_at TEXT NOT NULL DEFAULT (datetime('now')),
  word_count INTEGER,
  notable_count INTEGER,
  brief_count INTEGER,
  journal_count INTEGER,
  intro_present INTEGER,
  currently_present INTEGER,
  haiku_present INTEGER,
  cover_present INTEGER,
  source_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_draft_digests_issue
  ON draft_digests(issue, ran_at DESC, id DESC);

-- Goals — Patty's milestone progression. At most one row with
-- achieved_at IS NULL (the active goal). Jamie marks achieved_at when a
-- milestone hits and inserts the next. target_kind is 'members' (live
-- count from Buttondown) or 'dollars' (live total from Stripe).
CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_kind TEXT NOT NULL,
  target_value INTEGER NOT NULL,
  started_at TEXT NOT NULL DEFAULT (date('now')),
  achieved_at TEXT,
  notes TEXT
);

-- Seed Jamie's current active milestone if the table is empty (idempotent —
-- this whole file re-runs on every boot).
INSERT INTO goals (target_kind, target_value, started_at)
SELECT 'members', 50, '2026-05-11'
WHERE NOT EXISTS (SELECT 1 FROM goals);

-- Campaigns — Marky's ad-placement ledger. One row per `?ref=<tag>`
-- campaign, created by /workshop campaign add. Status: 'live' while
-- it's running, 'sunset' once it's over. `copy` holds the actual promo
-- text that ran in the placement, so performance can be read against the
-- creative — set at add-campaign time or later via campaign-copy.
CREATE TABLE IF NOT EXISTS campaigns (
  name TEXT PRIMARY KEY,
  ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'live',
  started_at TEXT NOT NULL DEFAULT (date('now')),
  ends_at TEXT,
  expected_signups INTEGER,
  expected_traffic INTEGER,
  copy TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_campaigns_ref ON campaigns(ref);

-- Campaign metrics — append-only per-poll history. daily-metrics inserts
-- one row per active campaign each run; a 90-day window is plenty, older
-- rows can age out.
CREATE TABLE IF NOT EXISTS campaign_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_name TEXT NOT NULL REFERENCES campaigns(name),
  ran_at TEXT NOT NULL DEFAULT (datetime('now')),
  signups INTEGER,
  traffic INTEGER
);

CREATE INDEX IF NOT EXISTS idx_campaign_metrics_name
  ON campaign_metrics(campaign_name, ran_at DESC, id DESC);
