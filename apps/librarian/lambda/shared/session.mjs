import crypto from 'node:crypto';
import { normalizeHeaders } from './http.mjs';

const SESSION_TTL_SECONDS = 60 * 60 * 12;

function b64url(value) {
  return Buffer.from(value).toString('base64url');
}

function b64urlDecode(value) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  return Buffer.from(value + padding, 'base64url');
}

export function sessionSecret() {
  const value = process.env.SESSION_SECRET || process.env.LIBRARIAN_SIGNING_SECRET;
  if (!value) throw new Error('SESSION_SECRET is required');
  return value;
}

export function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase();
}

export function emailHash(email) {
  return crypto.createHash('sha256').update(normalizeEmail(email)).digest('hex');
}

export function stableHash(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest('hex');
}

export function signPayload(payload) {
  const encoded = b64url(JSON.stringify(payload, Object.keys(payload).sort()));
  const signature = crypto.createHmac('sha256', sessionSecret()).update(encoded).digest('base64url');
  return `${encoded}.${signature}`;
}

export function createSessionToken(email, sessionId = crypto.randomBytes(18).toString('base64url')) {
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  return {
    sessionId,
    expiresAt,
    token: signPayload({ sid: sessionId, sub: emailHash(email), exp: expiresAt })
  };
}

// Mint a session token for a non-email subject — used by the Discord
// bridge, which identifies users by Discord user id rather than email.
// `sub` should be a stable, namespaced string like "discord:<hash>".
export function createSessionTokenForSub(sub, sessionId = crypto.randomBytes(18).toString('base64url')) {
  if (!sub || typeof sub !== 'string') {
    throw new Error('createSessionTokenForSub: sub must be a non-empty string');
  }
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  return {
    sessionId,
    expiresAt,
    token: signPayload({ sid: sessionId, sub, exp: expiresAt })
  };
}

export function verifyToken(token) {
  try {
    const [encoded, signature] = String(token || '').split('.', 2);
    if (!encoded || !signature) return null;
    const expected = crypto.createHmac('sha256', sessionSecret()).update(encoded).digest();
    const supplied = b64urlDecode(signature);
    if (expected.length !== supplied.length || !crypto.timingSafeEqual(expected, supplied)) return null;
    const payload = JSON.parse(b64urlDecode(encoded).toString('utf8'));
    if (Number(payload.exp || 0) < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

export function extractBearer(event, body = {}) {
  const auth = String(normalizeHeaders(event?.headers || {}).authorization || '');
  if (auth.toLowerCase().startsWith('bearer ')) return auth.slice(7).trim();
  return String(body.token || '');
}
