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

CREATE TABLE IF NOT EXISTS analytics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_date TEXT NOT NULL,
  metric_type TEXT NOT NULL,
  value INTEGER,
  details TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

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

CREATE TABLE IF NOT EXISTS supporter_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email_hash TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_date TEXT NOT NULL,
  details TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

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

CREATE TABLE IF NOT EXISTS channel_routes (
  channel_name TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  primary_agent TEXT,
  category TEXT
);
