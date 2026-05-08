import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { PutItemCommand } from '@aws-sdk/client-dynamodb';
import { bedrock, dynamodb, agentModel } from '../shared/aws-clients.mjs';
import { createSubscriber, ensureThingyTag, fetchSubscriber, sanitizeAttribution, sendSubscriberReminder, subscriberStatus } from '../shared/buttondown.mjs';
import { eventSummary, jsonResponse, methodAndPath, parseBody, clientSourceIp, userAgent } from '../shared/http.mjs';
import { checkRateLimit } from '../shared/rate-limit.mjs';
import { createSessionToken, createSessionTokenForSub, emailHash, normalizeEmail, stableHash } from '../shared/session.mjs';
import { authProfile, getUserMemory } from '../shared/user-memory.mjs';
import crypto from 'node:crypto';
import { logEvent } from '../shared/logging.mjs';
import { premiumThankYouSystemPrompt } from '../shared/prompts.mjs';

const AUTH_RATE_LIMIT_MAX = 30;
const DISCORD_BRIDGE_RATE_LIMIT_MAX = 60;
const DISCORD_USER_ID_RE = /^[A-Za-z0-9_:.-]{1,64}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const ALLOWED_SOURCES = new Set([
  'thingy',
  'site',
  'hero',
  'mid1',
  'mid2',
  'footer',
  'about',
  'issue'
]);
function normalizeSource(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return 'site';
  return ALLOWED_SOURCES.has(raw) ? raw : 'site';
}

function clientIdentityHash(event) {
  return stableHash(`${clientSourceIp(event) || 'unknown'}\0${userAgent(event) || ''}`);
}

function dynamoString(value) {
  return { S: String(value || '') };
}

function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

async function recordSession(sessionId, email, expiresAt) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return;
  const start = performance.now();
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      pk: dynamoString(`session#${sessionId}`),
      sk: dynamoString('session'),
      email_hash: dynamoString(emailHash(email)),
      expires_at: dynamoNumber(expiresAt),
      ttl: dynamoNumber(expiresAt)
    }
  }));
  logEvent('info', 'session_recorded', {
    email_hash: emailHash(email),
    duration_ms: Math.round(performance.now() - start)
  });
}

function bedrockMessageText(message) {
  return (message?.content || []).map((part) => part.text || '').filter(Boolean).join('\n').trim();
}

async function generatePremiumThankYou() {
  const start = performance.now();
  const response = await bedrock.send(new ConverseCommand({
    modelId: agentModel(),
    system: [{ text: premiumThankYouSystemPrompt() }, { cachePoint: { type: 'default' } }],
    messages: [{ role: 'user', content: [{ text: 'Generate a fresh thank-you under 28 words.' }] }],
    inferenceConfig: { maxTokens: 120, temperature: 0.7 }
  }));
  const text = bedrockMessageText(response.output?.message || {}).replace(/\s+/g, ' ').trim();
  if (!text || text.length > 220) throw new Error('Bedrock returned invalid premium thank-you');
  logEvent('info', 'premium_thank_you_generated', {
    model: agentModel(),
    duration_ms: Math.round(performance.now() - start),
    message_chars: text.length
  });
  return text;
}

async function authSuccessResponse(email, subscriber, source, event, start) {
  const { sessionId, expiresAt, token } = createSessionToken(email);
  await recordSession(sessionId, email, expiresAt);
  const status = subscriberStatus(subscriber);
  logEvent('info', 'auth_succeeded', {
    email_hash: emailHash(email),
    subscriber_status: status,
    duration_ms: Math.round(performance.now() - start)
  });
  if (source === 'thingy') {
    // Best-effort: ensure the wt-thingy user tag is on this subscriber. Don't
    // block the auth response — a transient Buttondown error must not break login.
    ensureThingyTag(subscriber).catch(() => { /* swallowed; ensureThingyTag logs internally */ });
  }
  const memory = await getUserMemory(emailHash(email));
  const payload = {
    status,
    token,
    expires_at: expiresAt,
    profile: authProfile(memory)
  };
  if (status === 'premium') {
    try {
      payload.message = await generatePremiumThankYou();
    } catch (error) {
      logEvent('warning', 'premium_thank_you_generation_failed', {
        email_hash: emailHash(email),
        error_type: error.constructor?.name || 'Error'
      });
      payload.message = 'Thanks for being a Weekly Thing Supporting Member!';
    }
  }
  return jsonResponse(200, payload, event);
}

function bridgeUserSub(discordUserId) {
  // Stable, namespaced subject id. Hashed so the Lambda's logs and rate-limit
  // bucket key never carry the raw Discord user id.
  return 'discord:' + stableHash(discordUserId).slice(0, 32);
}

async function handleDiscordBridge(event, body, start) {
  const expected = process.env.DISCORD_BRIDGE_SECRET || '';
  if (!expected) {
    logEvent('warning', 'auth_discord_bridge_disabled');
    return jsonResponse(503, { error: 'Discord bridge is not enabled.' }, event);
  }
  const supplied = String(body.bridge_secret || '');
  const expectedBuf = Buffer.from(expected, 'utf8');
  const suppliedBuf = Buffer.from(supplied, 'utf8');
  const secretsMatch =
    expectedBuf.length === suppliedBuf.length &&
    crypto.timingSafeEqual(expectedBuf, suppliedBuf);
  if (!secretsMatch) {
    logEvent('warning', 'auth_discord_bridge_bad_secret');
    return jsonResponse(401, { error: 'Bridge secret rejected.' }, event);
  }
  const discordUserId = String(body.discord_user_id || '').trim();
  if (!DISCORD_USER_ID_RE.test(discordUserId)) {
    logEvent('info', 'auth_discord_bridge_invalid_user_id');
    return jsonResponse(400, { error: 'discord_user_id is required.' }, event);
  }
  // Per-Discord-user rate limit on bridge minting (separate from the IP-based
  // auth limit checked above).
  const sub = bridgeUserSub(discordUserId);
  const bridgeLimit = Number(
    process.env.DISCORD_BRIDGE_RATE_LIMIT_MAX || DISCORD_BRIDGE_RATE_LIMIT_MAX
  );
  if (!(await checkRateLimit(`auth#bridge:${sub}`, bridgeLimit))) {
    logEvent('warning', 'auth_discord_bridge_rate_limited', { discord_sub: sub });
    return jsonResponse(429, { error: 'Bridge token requests rate-limited.' }, event);
  }
  const session = createSessionTokenForSub(sub);
  const memory = await getUserMemory(sub);
  logEvent('info', 'auth_discord_bridge_issued', {
    discord_sub: sub,
    subscriber_source: 'discord',
    returning: Boolean(memory && (memory.turn_count || 0) > 0),
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'active',
    source: 'discord',
    token: session.token,
    expires_at: session.expiresAt,
    profile: authProfile(memory)
  }, event);
}

async function authHandler(event) {
  const start = performance.now();
  const body = parseBody(event);
  const email = normalizeEmail(body.email);
  const action = String(body.action || 'check').trim().toLowerCase();
  const source = normalizeSource(body.source);
  const attribution = sanitizeAttribution(body.attribution);
  const hashedEmail = email ? emailHash(email) : undefined;

  const authLimit = Number(process.env.AUTH_RATE_LIMIT_MAX || AUTH_RATE_LIMIT_MAX);
  if (!(await checkRateLimit(`auth#${clientIdentityHash(event)}`, authLimit))) {
    logEvent('warning', 'auth_rate_limited', { email_hash: hashedEmail });
    return jsonResponse(429, { error: 'Too many access attempts. Please try again later.' }, event);
  }
  if (!['check', 'subscribe', 'resend_confirmation', 'discord_bridge'].includes(action)) {
    logEvent('info', 'auth_rejected_invalid_action', { email_hash: hashedEmail, action });
    return jsonResponse(400, { error: 'Unsupported subscriber action.' }, event);
  }

  // Discord bridge mints tokens without an email address — Discord membership
  // is the auth boundary. Runs before EMAIL_RE so the email check doesn't
  // reject the request. Gated by a shared secret in DISCORD_BRIDGE_SECRET;
  // if the secret isn't configured the action returns 503 so the bridge
  // surfaces "not enabled" rather than silently passing.
  if (action === 'discord_bridge') {
    return await handleDiscordBridge(event, body, start);
  }

  if (!EMAIL_RE.test(email)) {
    logEvent('info', 'auth_rejected_invalid_email', { email_hash: hashedEmail });
    return jsonResponse(400, { error: 'Enter a valid email address.' }, event);
  }

  if (action === 'subscribe') {
    try {
      const subscriber = await createSubscriber(email, event, source, attribution);
      const status = subscriberStatus(subscriber);
      logEvent('info', 'auth_subscribe_completed', {
        email_hash: hashedEmail,
        subscriber_status: status,
        subscriber_source: source,
        campaign_ref: attribution?.ref || null
      });
      return jsonResponse(200, {
        status: 'subscribed',
        subscriber_status: status,
        message: 'Check your inbox to confirm your subscription.'
      }, event);
    } catch (error) {
      logEvent('error', 'buttondown_subscriber_create_failed', { email_hash: hashedEmail, subscriber_source: source, error_type: error.constructor?.name || 'Error' });
      return jsonResponse(502, { error: 'Could not add that email right now.' }, event);
    }
  }

  if (action === 'resend_confirmation') {
    try {
      await sendSubscriberReminder(email);
      return jsonResponse(200, { status: 'reminder_sent', message: 'Confirmation email sent. Check your inbox.' }, event);
    } catch (error) {
      logEvent('error', 'buttondown_subscriber_reminder_failed', { email_hash: hashedEmail, error_type: error.constructor?.name || 'Error' });
      return jsonResponse(502, {
        status: 'reminder_unavailable',
        error: 'Could not resend the confirmation email right now. Please look for the original confirmation email.'
      }, event);
    }
  }

  let subscriber;
  try {
    subscriber = await fetchSubscriber(email);
  } catch (error) {
    logEvent('error', 'buttondown_lookup_failed', { email_hash: hashedEmail, error_type: error.constructor?.name || 'Error' });
    return jsonResponse(502, { error: 'Could not validate subscriber status right now.' }, event);
  }

  const status = subscriberStatus(subscriber);
  if (status === 'not_found') {
    logEvent('info', 'auth_subscriber_not_found', { email_hash: hashedEmail });
    return jsonResponse(200, { status, message: 'That email is not subscribed. Would you like to be added?' }, event);
  }
  if (status === 'unconfirmed') {
    logEvent('info', 'auth_subscriber_unconfirmed', { email_hash: hashedEmail });
    return jsonResponse(200, { status, message: 'Please confirm your email before using Thingy.' }, event);
  }
  if (status === 'inactive') {
    logEvent('info', 'auth_subscriber_inactive', { email_hash: hashedEmail });
    return jsonResponse(403, { status, error: 'That subscription is not active.' }, event);
  }
  return authSuccessResponse(email, subscriber, source, event, start);
}

function healthHandler(event) {
  return jsonResponse(200, {
    ok: true,
    service: 'weekly-thing-librarian-auth',
    model: agentModel()
  }, event);
}

export async function handler(event, context) {
  const start = performance.now();
  const summary = eventSummary(event, context);
  logEvent('info', 'request_started', summary, 'weekly-thing-librarian-auth');
  let response;
  try {
    const { method, path } = methodAndPath(event);
    if (method === 'OPTIONS') {
      response = jsonResponse(204, {}, event);
    } else if (method === 'GET' && path.endsWith('/health')) {
      response = healthHandler(event);
    } else if (method === 'POST' && path.endsWith('/auth')) {
      response = await authHandler(event);
    } else {
      response = jsonResponse(404, { error: 'Not found.' }, event);
    }
  } catch (error) {
    logEvent('error', 'request_failed', { ...summary, error_type: error.constructor?.name || 'Error' }, 'weekly-thing-librarian-auth');
    response = jsonResponse(500, { error: 'Thingy is unavailable right now.' }, event);
  }
  response.headers = { ...(response.headers || {}), 'x-request-id': summary.request_id || '' };
  logEvent('info', 'request_completed', {
    ...summary,
    status_code: response.statusCode,
    duration_ms: Math.round(performance.now() - start)
  }, 'weekly-thing-librarian-auth');
  return response;
}
