import { clientSourceIp } from './http.mjs';
import { emailHash, normalizeEmail } from './session.mjs';
import { logEvent } from './logging.mjs';

const BUTTONDOWN_BASE = 'https://api.buttondown.com/v1';

const SOURCE_TAG_IDS = {
  thingy: 'sub_tag_3ts444xst99y08j8bqfnwt1g4h',
  site: 'sub_tag_4x4hy3d3ff9epa6ebx9k7rae51'
};

const PLACEMENT_TO_SOURCE = {
  hero: 'site',
  mid1: 'site',
  mid2: 'site',
  footer: 'site',
  about: 'site',
  issue: 'site'
};

export function resolveSourceTag(source) {
  const key = String(source || '').trim().toLowerCase();
  if (SOURCE_TAG_IDS[key]) return SOURCE_TAG_IDS[key];
  if (PLACEMENT_TO_SOURCE[key]) return SOURCE_TAG_IDS[PLACEMENT_TO_SOURCE[key]];
  return SOURCE_TAG_IDS.site;
}

function buttondownHeaders(extra = {}) {
  const apiKey = process.env.BUTTONDOWN_API_KEY;
  if (!apiKey) throw new Error('BUTTONDOWN_API_KEY is required');
  return { authorization: `Token ${apiKey}`, accept: 'application/json', ...extra };
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function fetchSubscriber(email) {
  const normalized = normalizeEmail(email);
  const start = performance.now();
  const response = await fetch(`${BUTTONDOWN_BASE}/subscribers/${encodeURIComponent(normalized)}`, {
    headers: buttondownHeaders()
  });
  logEvent('info', 'buttondown_subscriber_lookup', {
    email_hash: emailHash(email),
    status_code: response.status,
    duration_ms: Math.round(performance.now() - start)
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Buttondown lookup failed with ${response.status}`);
  return readJsonResponse(response);
}

export async function createSubscriber(email, event, source) {
  const tagId = resolveSourceTag(source);
  const body = {
    email_address: normalizeEmail(email),
    tags: [tagId]
  };
  const ip = clientSourceIp(event);
  if (ip) body.ip_address = ip;
  const start = performance.now();
  const response = await fetch(`${BUTTONDOWN_BASE}/subscribers`, {
    method: 'POST',
    headers: buttondownHeaders({ 'content-type': 'application/json' }),
    body: JSON.stringify(body)
  });
  logEvent('info', 'buttondown_subscriber_create', {
    email_hash: emailHash(email),
    status_code: response.status,
    duration_ms: Math.round(performance.now() - start)
  });
  if (!response.ok) throw new Error(`Buttondown create failed with ${response.status}`);
  return readJsonResponse(response);
}

export async function sendSubscriberReminder(email) {
  const start = performance.now();
  const response = await fetch(`${BUTTONDOWN_BASE}/subscribers/${encodeURIComponent(normalizeEmail(email))}/send-reminder`, {
    method: 'POST',
    headers: buttondownHeaders()
  });
  logEvent('info', 'buttondown_subscriber_reminder', {
    email_hash: emailHash(email),
    status_code: response.status,
    duration_ms: Math.round(performance.now() - start)
  });
  if (!response.ok) throw new Error(`Buttondown reminder failed with ${response.status}`);
}

export function subscriberStatus(subscriber) {
  if (!subscriber) return 'not_found';
  const type = String(subscriber.type || '').toLowerCase();
  if (type === 'unactivated') return 'unconfirmed';
  if (subscriber.unsubscription_date || subscriber.churn_date) return 'inactive';
  if (['unsubscribed', 'churned', 'disabled'].includes(type)) return 'inactive';
  if (type === 'premium') return 'premium';
  return 'active';
}
