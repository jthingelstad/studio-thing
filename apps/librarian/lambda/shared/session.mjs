import crypto from 'node:crypto';
import { normalizeHeaders } from './http.mjs';

const SESSION_TTL_SECONDS = 60 * 60 * 24 * 10;
const PRIVILEGED_ENTITLEMENTS = new Set(['supporting_member', 'trusted_circle', 'owner']);

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

export function createSessionToken(email, sessionId = crypto.randomBytes(18).toString('base64url'), claims = {}) {
  const issuedAtMs = Date.now();
  const issuedAt = Math.floor(issuedAtMs / 1000);
  const expiresAt = issuedAt + SESSION_TTL_SECONDS;
  const safeClaims = claims && typeof claims === 'object' && !Array.isArray(claims) ? claims : {};
  const payloadClaims = { ...safeClaims };
  const entitlements = Array.isArray(payloadClaims.entitlements) ? payloadClaims.entitlements : [];
  if (entitlements.some((entitlement) => PRIVILEGED_ENTITLEMENTS.has(entitlement))
      && !Number(payloadClaims.entitlements_verified_until || 0)) {
    payloadClaims.entitlements_verified_until = expiresAt;
  }
  return {
    sessionId,
    expiresAt,
    token: signPayload({ ...payloadClaims, sid: sessionId, sub: emailHash(email), exp: expiresAt, iat: issuedAt, iat_ms: issuedAtMs })
  };
}

// Mint a session token for a non-email subject — used by the Discord
// bridge, which identifies users by Discord user id rather than email.
// `sub` should be a stable, namespaced string like "discord:<hash>".
export function createSessionTokenForSub(sub, sessionId = crypto.randomBytes(18).toString('base64url'), claims = {}) {
  if (!sub || typeof sub !== 'string') {
    throw new Error('createSessionTokenForSub: sub must be a non-empty string');
  }
  const issuedAtMs = Date.now();
  const issuedAt = Math.floor(issuedAtMs / 1000);
  const expiresAt = issuedAt + SESSION_TTL_SECONDS;
  const safeClaims = claims && typeof claims === 'object' && !Array.isArray(claims) ? claims : {};
  const payloadClaims = { ...safeClaims };
  const entitlements = Array.isArray(payloadClaims.entitlements) ? payloadClaims.entitlements : [];
  if (entitlements.some((entitlement) => PRIVILEGED_ENTITLEMENTS.has(entitlement))
      && !Number(payloadClaims.entitlements_verified_until || 0)) {
    payloadClaims.entitlements_verified_until = expiresAt;
  }
  return {
    sessionId,
    expiresAt,
    token: signPayload({ ...payloadClaims, sid: sessionId, sub, exp: expiresAt, iat: issuedAt, iat_ms: issuedAtMs })
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
