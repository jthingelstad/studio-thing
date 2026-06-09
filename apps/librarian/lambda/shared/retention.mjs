const SECONDS_PER_DAY = 24 * 60 * 60;

export const DEFAULT_CONVERSATION_RETENTION_DAYS = 45;
export const DEFAULT_DISPATCH_DRAFT_RETENTION_DAYS = 7;
export const DEFAULT_DISPATCH_HISTORY_RETENTION_DAYS = 90;

function retentionDays(envName, fallback) {
  const value = Number(process.env[envName] || fallback);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function epochSeconds(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const milliseconds = date.getTime();
  return Number.isFinite(milliseconds)
    ? Math.floor(milliseconds / 1000)
    : Math.floor(Date.now() / 1000);
}

export function ttlSecondsFrom(value, days) {
  return epochSeconds(value) + Math.ceil(Number(days) * SECONDS_PER_DAY);
}

export function conversationTtlSeconds(now = new Date()) {
  return ttlSecondsFrom(
    now,
    retentionDays('THINGY_CONVERSATION_RETENTION_DAYS', DEFAULT_CONVERSATION_RETENTION_DAYS)
  );
}

export function dispatchDraftTtlSeconds(now = new Date()) {
  return ttlSecondsFrom(
    now,
    retentionDays('THINGY_DISPATCH_DRAFT_RETENTION_DAYS', DEFAULT_DISPATCH_DRAFT_RETENTION_DAYS)
  );
}

export function dispatchHistoryTtlSeconds(now = new Date()) {
  return ttlSecondsFrom(
    now,
    retentionDays('THINGY_DISPATCH_HISTORY_RETENTION_DAYS', DEFAULT_DISPATCH_HISTORY_RETENTION_DAYS)
  );
}
