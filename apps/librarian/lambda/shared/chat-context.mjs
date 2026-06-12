import { entitlementContext, isOwnerSubscriberHash } from './conversation-modes.mjs';

const MAX_HISTORY_MESSAGES = 8;
const MAX_HISTORY_CHARS = 4000;

export function sanitizeHistory(history) {
  if (!Array.isArray(history)) return [];
  const cleaned = [];
  let chars = 0;
  for (const item of history.slice(-MAX_HISTORY_MESSAGES)) {
    const role = item?.role === 'assistant' ? 'assistant' : item?.role === 'user' ? 'user' : '';
    const content = String(item?.content || '').trim().replace(/\s+/g, ' ');
    if (!role || !content) continue;
    const clipped = content.slice(0, 700);
    chars += clipped.length;
    if (chars > MAX_HISTORY_CHARS) break;
    cleaned.push({ role, content: clipped });
  }
  return cleaned;
}

export function conversationContext(history) {
  if (!history.length) return 'No earlier conversation in this session.';
  return history.map((item) => `${item.role === 'user' ? 'User' : 'Thingy'}: ${item.content}`).join('\n');
}

function cleanContextString(value, maxLength = 120) {
  return String(value || '').trim().replace(/\s+/g, ' ').slice(0, maxLength);
}

export function normalizeClientContext(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const dayPeriod = cleanContextString(value.day_period, 20).toLowerCase();
  const offsetMinutes = Number(value.utc_offset_minutes);
  return {
    locale: cleanContextString(value.locale, 40),
    time_zone: cleanContextString(value.time_zone, 80),
    utc_offset_minutes: Number.isFinite(offsetMinutes) && Math.abs(offsetMinutes) <= 14 * 60 ? Math.trunc(offsetMinutes) : null,
    local_iso: cleanContextString(value.local_iso, 40),
    local_date: cleanContextString(value.local_date, 80),
    local_time: cleanContextString(value.local_time, 60),
    day_period: ['morning', 'afternoon', 'evening', 'night'].includes(dayPeriod) ? dayPeriod : ''
  };
}

export function normalizeUserProfile(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const status = cleanContextString(value.status, 30).toLowerCase();
  const turnCount = Number(value.turn_count);
  return {
    status: cleanContextString(status, 30),
    supporting_member: value.supporting_member === true || status === 'premium',
    returning: value.returning === true,
    preferred_name: cleanContextString(value.preferred_name, 80),
    awaiting_name: value.awaiting_name === true,
    first_seen_at: cleanContextString(value.first_seen_at, 40),
    last_seen_at: cleanContextString(value.last_seen_at, 40),
    turn_count: Number.isFinite(turnCount) && turnCount >= 0 ? Math.trunc(turnCount) : null
  };
}

function titleCasePreferredName(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .slice(0, 4)
    .map((word) => (/^[A-Z]{2,}$/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(' ')
    .slice(0, 80);
}

export function extractPreferredNameFromMessage(message) {
  const text = String(message || '').trim();
  if (!text || text.length > 160 || /[?]/.test(text)) return '';
  const match = text.match(/^(?:my (?:preferred )?name is|i am|i'm|call me|please call me)\s+([a-z][a-z .'’-]{0,60})[.!]?$/i);
  if (!match) return '';
  const candidate = match[1].trim().replace(/[.!]+$/, '');
  if (!/^[a-z][a-z .'’-]{0,60}$/i.test(candidate)) return '';
  return titleCasePreferredName(candidate);
}

export function readerContextPrompt(clientContext, userProfile) {
  const context = normalizeClientContext(clientContext);
  const profile = normalizeUserProfile(userProfile);
  const lines = [];
  if (context.local_date || context.local_time) {
    lines.push(`Reader local time: ${[context.local_date, context.local_time].filter(Boolean).join(' at ')}`);
  }
  if (context.time_zone) lines.push(`Reader time zone: ${context.time_zone}`);
  if (context.utc_offset_minutes !== null) lines.push(`Reader UTC offset minutes: ${context.utc_offset_minutes}`);
  if (context.locale) lines.push(`Reader locale: ${context.locale}`);
  if (context.day_period) lines.push(`Reader day period: ${context.day_period}`);
  if (context.local_iso) lines.push(`Reader local timestamp: ${context.local_iso}`);
  if (profile.status) lines.push(`Subscriber status: ${profile.status}`);
  if (profile.supporting_member) lines.push('Subscriber is a Weekly Thing Supporting Member.');
  if (profile.preferred_name) lines.push(`Reader preferred name: ${profile.preferred_name}`);
  if (profile.awaiting_name && !profile.preferred_name) lines.push('Thingy recently asked what to call the reader; their next short response may be a name.');
  if (profile.turn_count !== null) lines.push(`Prior Thingy turns known to client: ${profile.turn_count}`);
  if (profile.returning) lines.push('Client profile says this is a returning Thingy reader.');
  if (profile.first_seen_at) lines.push(`First seen by Thingy: ${profile.first_seen_at}`);
  if (profile.last_seen_at) lines.push(`Last seen by Thingy: ${profile.last_seen_at}`);
  return lines.length ? lines.join('\n') : 'No reader-local context supplied.';
}

export function tokenEntitlements(payload) {
  const entitlements = new Set(Array.isArray(payload?.entitlements) ? payload.entitlements : ['reader']);
  if (isOwnerSubscriberHash(payload?.sub)) {
    entitlements.add('owner');
    entitlements.add('supporting_member');
    entitlements.add('trusted_circle');
  }
  return entitlementContext([...entitlements]);
}
