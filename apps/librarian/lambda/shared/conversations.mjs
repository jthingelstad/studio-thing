// Pure helpers for the operator-only conversation-log read (the
// `list_conversations` auth action). No AWS SDK imports here — the
// DynamoDB Scan itself lives in auth/handler.mjs; this module just shapes
// params and unmarshals logged conversation items into clean JSON rows so
// it stays trivially testable.

export const CONVERSATIONS_DEFAULT_LIMIT = 100;
export const CONVERSATIONS_MAX_LIMIT = 300;
export const CONVERSATIONS_DEFAULT_LOOKBACK_HOURS = 24;
export const CONVERSATIONS_MAX_SCAN_PAGES = 25; // hard bound on the table Scan

export function normalizeListConversationsParams(body = {}, now = Date.now()) {
  let since = String(body.since || '').trim();
  if (!since || Number.isNaN(Date.parse(since))) {
    since = new Date(now - CONVERSATIONS_DEFAULT_LOOKBACK_HOURS * 3600 * 1000).toISOString();
  }
  let limit = Number(body.limit || CONVERSATIONS_DEFAULT_LIMIT);
  if (!Number.isFinite(limit) || limit <= 0) limit = CONVERSATIONS_DEFAULT_LIMIT;
  limit = Math.min(Math.floor(limit), CONVERSATIONS_MAX_LIMIT);
  return { since, limit };
}

export function fromDynamoAttr(av) {
  if (av == null || typeof av !== 'object') return null;
  if ('S' in av) return av.S;
  if ('N' in av) return Number(av.N);
  if ('BOOL' in av) return Boolean(av.BOOL);
  if ('NULL' in av) return null;
  if ('L' in av) return (av.L || []).map(fromDynamoAttr);
  if ('M' in av) return Object.fromEntries(Object.entries(av.M || {}).map(([k, v]) => [k, fromDynamoAttr(v)]));
  return null;
}

// One logged conversation turn — the row written by the stream Lambda's
// recordConversation(), flattened. `ttl` and bookkeeping attrs are dropped.
export function conversationRow(item) {
  const o = Object.fromEntries(Object.entries(item || {}).map(([k, v]) => [k, fromDynamoAttr(v)]));
  const pk = typeof o.pk === 'string' ? o.pk : '';
  return {
    request_id: o.request_id || (pk.startsWith('conversation#') ? pk.slice('conversation#'.length) : ''),
    created_at: o.created_at || '',
    subscriber_hash: o.subscriber_hash || '',
    route: o.route || '',
    question: o.question || '',
    answer: o.answer || '',
    question_chars: Number(o.question_chars || 0),
    answer_chars: Number(o.answer_chars || 0),
    history_count: Number(o.history_count || 0),
    citation_count: Number(o.citation_count || 0),
    source_issues: Array.isArray(o.source_issues) ? o.source_issues : [],
    citations: Array.isArray(o.citations) ? o.citations : [],
    feedback_reaction: o.feedback_reaction || null,
    feedback_at: o.feedback_at || null,
    user_agent: o.user_agent || ''
  };
}

// Sort logged turns oldest→newest and keep the most recent `limit`.
export function sortAndTrim(rows, limit) {
  const sorted = [...rows].sort((a, b) => (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0));
  return sorted.slice(-limit);
}
