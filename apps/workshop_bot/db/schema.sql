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

-- URLs Linky has already shown to Jamie from any discovery feed
-- (Pinboard popular, Lobste.rs, Hacker News, Tildes ~tech, IndieWeb
-- News, …). Records the *first* sighting + Linky's verdict on that
-- sighting. The companion `popular_seen_sightings` table records
-- *every* (url, source) sighting across all feeds and all scans, so
-- cross-source signal (a URL bouncing between communities over time)
-- can drive an "uplift" re-evaluation card.
CREATE TABLE IF NOT EXISTS pinboard_popular_seen (
  url TEXT PRIMARY KEY,
  title TEXT,
  posted_by TEXT,
  judged_interesting INTEGER,                  -- 1 / 0 / NULL (not judged yet)
  judgment_note TEXT,
  verdict_source TEXT,                         -- which feed produced the verdict (uplift-block label)
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-(url, source) sighting log — every time a discovery feed shows
-- Linky a URL, we record it here. `pinboard_popular_seen` carries the
-- *first* sighting + verdict (insert-or-ignore); this table carries
-- the full timeline. The job uses it to answer: "has THIS feed seen
-- this URL before?" If no — and `pinboard_popular_seen` already has
-- the URL — it's a cross-source uplift candidate: Linky writes a
-- re-evaluation card with the prior sightings + verdict as context.
CREATE TABLE IF NOT EXISTS popular_seen_sightings (
  url TEXT NOT NULL,
  source TEXT NOT NULL,                        -- 'popular' / 'lobsters' / ...
  seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (url, source)
);

CREATE INDEX IF NOT EXISTS idx_popular_seen_sightings_url
  ON popular_seen_sightings(url);

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
--   thingy_tokens / thingy_requests / thingy_conversations — Thingy moved
--                    to its own process (apps/thingy_bridge/); these
--                    tables now live in apps/thingy_bridge/db/schema.sql.
DROP INDEX IF EXISTS idx_agent_inbox_recipient;
DROP TABLE IF EXISTS agent_inbox;
DROP TABLE IF EXISTS analytics;
DROP TABLE IF EXISTS supporter_events;
DROP TABLE IF EXISTS channel_routes;
DROP INDEX IF EXISTS idx_thingy_requests_bot_msg;
DROP INDEX IF EXISTS idx_thingy_conversations_ended;
DROP TABLE IF EXISTS thingy_tokens;
DROP TABLE IF EXISTS thingy_requests;
DROP TABLE IF EXISTS thingy_conversations;

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

-- Thingy conversations — workshop_bot's local mirror of what readers ask
-- the public archive agent. The hourly `thingy-watch` job fetches logged
-- turns from the Lambda (/auth?action=list_conversations), groups them
-- into conversations (same subscriber, turns within ~30 min / a fresh
-- browser history), has Eddy write a two-sided assessment, stores the
-- whole thing here (so it outlives the Lambda's ~60-day DynamoDB TTL and
-- gets a stable local id), and posts a card to #chatter. `/workshop thingy
-- recent` and `/workshop thingy show <id>` read straight from this table.
CREATE TABLE IF NOT EXISTS thingy_conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subscriber_hash TEXT NOT NULL,               -- SHA256 of the reader's email; never the email itself
  started_at TEXT NOT NULL,                    -- ISO; created_at of the first turn
  ended_at TEXT NOT NULL,                      -- ISO; created_at of the last turn (also the watch watermark)
  turn_count INTEGER NOT NULL,
  -- the conversation as JSON: [{request_id, created_at, question, answer,
  --   citations:[{issue_number,subject,publish_date,section,url}],
  --   source_issues:[...], feedback_reaction, feedback_at}]
  transcript_json TEXT NOT NULL,
  -- JSON array of the turn request_ids in this conversation — the dedup key
  -- (a turn already mirrored here is never re-formed into a new conversation)
  turn_request_ids_json TEXT NOT NULL,
  source_issues_json TEXT,                     -- JSON array of issue numbers cited across the conversation
  feedback TEXT,                               -- 'up' / 'down' / 'mixed' / NULL — rolled up from the turns
  topic TEXT,                                  -- one-line topic, from Eddy's assessment pass
  assessment_md TEXT,                          -- Eddy's two-sided assessment (markdown)
  posted_to_chatter_at TEXT,                   -- when thingy-watch posted the card; NULL until then
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_thingy_conversations_ended
  ON thingy_conversations(ended_at DESC, id DESC);

-- Follow-ups — an agent (or Jamie) commits to revisiting something at a
-- future time or when the in-flight issue reaches a number. The hourly
-- `follow-up-sweep` job fires the due ones: runs the named persona's agent
-- loop with the note + current context and posts a check-in. There are no
-- per-persona heartbeats — this is the deliberate, targeted exception, and
-- it only does anything when a real commitment comes due.
CREATE TABLE IF NOT EXISTS follow_ups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  persona TEXT NOT NULL,                          -- who follows up: 'eddy' / 'linky' / 'marky' / 'patty'
  channel_env TEXT,                               -- env var of the channel to post to; NULL = persona's home channel
  trigger_kind TEXT NOT NULL,                     -- 'time' | 'issue'
  due_at TEXT,                                    -- ISO datetime (YYYY-MM-DDTHH:MM:SS) — set when trigger_kind='time'
  trigger_issue INTEGER,                          -- issue number — fires once the active in-flight issue >= this; set when trigger_kind='issue'
  note TEXT NOT NULL,                             -- what was committed to (fed back to the agent verbatim)
  created_by TEXT,                                -- who set it: a Discord user, or the persona itself
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  fired_at TEXT,                                  -- when the sweep fired it; NULL = still open
  cancelled_at TEXT                               -- NULL unless cancelled
);

CREATE INDEX IF NOT EXISTS idx_follow_ups_open
  ON follow_ups(fired_at, cancelled_at, trigger_kind);

-- Per-link research cards Linky has posted to #research. Lets the reply
-- listener resolve a Discord reply back to the URL it's commenting on,
-- so Jamie's reply can be written straight to that Pinboard bookmark's
-- description. One row per posted card; never updated (each card is its
-- own immutable post). `source` is one of:
--   - 'popular'       — Pinboard's popular feed   (URL may not yet be bookmarked)
--   - 'lobsters'      — Lobste.rs hottest feed    (URL may not yet be bookmarked)
--   - 'hackernews'    — HN front page via Algolia (URL may not yet be bookmarked)
--   - 'tildes'        — Tildes ~tech atom feed    (URL may not yet be bookmarked)
--   - 'indieweb_news' — IndieWeb News h-feed       (URL may not yet be bookmarked)
--   - 'toread'        — Jamie's own toread + public Pinboard bookmarks
-- Source names are declared in apps/workshop_bot/jobs/pinboard_scan.py's
-- `DISCOVERY_FEEDS` registry (one entry per discovery feed) plus the
-- separate `toread` lane.
-- `title` is the source-side title we captured at post time, used as
-- the fallback title when a discovery-feed reply / reaction creates a
-- new bookmark.
CREATE TABLE IF NOT EXISTS linky_research_messages (
  discord_message_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  source TEXT NOT NULL,                           -- see comment above
  title TEXT,
  posted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_linky_research_messages_posted
  ON linky_research_messages(posted_at DESC);

-- Image alt-text cache — generated via vision LLM on first sight, then
-- cached forever. `image_key` is a stable, content-addressed identifier:
-- the rehosted filename's basename for journal images (e.g.
-- ``428e3db12e.jpg`` — micro.blog uploads are already content-hashed), or
-- ``cover-<N>`` for an issue's cover. ``source`` is 'vision' (Claude
-- vision generated) or 'manual' (operator-supplied — e.g.
-- ``cover.json.alt``); cached vision rows can be overwritten by a manual
-- one without going back through the vision call.
CREATE TABLE IF NOT EXISTS image_alt_cache (
  image_key TEXT PRIMARY KEY,
  alt TEXT NOT NULL,
  source TEXT NOT NULL,                           -- 'vision' | 'manual'
  generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
