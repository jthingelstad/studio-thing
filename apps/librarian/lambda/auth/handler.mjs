import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { BatchWriteItemCommand, GetItemCommand, PutItemCommand, QueryCommand, ScanCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { bedrock, dynamodb, agentModel, fastModel } from '../shared/aws-clients.mjs';
import { createSubscriber, ensureThingyTag, fetchSubscriber, sanitizeAttribution, sendSubscriberReminder, subscriberStatus } from '../shared/buttondown.mjs';
import { eventSummary, jsonResponse, methodAndPath, parseBody, clientSourceIp, userAgent } from '../shared/http.mjs';
import { buildMagicLink, createMagicToken, magicLinkTtlSeconds, magicTokenHash, validMagicToken } from '../shared/magic-link.mjs';
import { sendMagicLinkEmail } from '../shared/jmap-mail.mjs';
import { checkRateLimit } from '../shared/rate-limit.mjs';
import { createSessionToken, createSessionTokenForSub, emailHash, extractBearer, normalizeEmail, stableHash, verifyToken } from '../shared/session.mjs';
import { authProfile, getUserMemory, recordUserPreferredName } from '../shared/user-memory.mjs';
import {
  availableConversationModes,
  canUseConversationMode,
  entitlementsForSubscriber,
  isOwnerSubscriberHash,
  normalizeConversationMode
} from '../shared/conversation-modes.mjs';
import crypto from 'node:crypto';
import { errorFields, logEvent } from '../shared/logging.mjs';
import { premiumThankYouSystemPrompt } from '../shared/prompts.mjs';
import {
  USER_CONVERSATION_LIMIT,
  conversationSk,
  conversationSummaryFromItem,
  conversationTurnFromItem,
  dynamoString as conversationDynamoString,
  turnSkPrefix,
  userConversationPk,
  validConversationId
} from '../shared/user-conversations.mjs';
import {
  createUserConversation,
  getUserConversation,
  getUserConversationMetadata,
  loadUserConversationSummaries,
  renameUserConversation
} from '../shared/conversation-store.mjs';
import {
  createQueuedDispatch,
  deleteUserDispatch,
  dispatchForClient,
  dispatchAvailability,
  getUserDispatch,
  listUserDispatches,
  queueDraftDispatch,
  upsertDispatchDraft
} from '../shared/dispatch-store.mjs';

const AUTH_RATE_LIMIT_MAX = 30;
const MAGIC_LINK_RATE_LIMIT_MAX = 6;
const DISCORD_BRIDGE_RATE_LIMIT_MAX = 60;
const CONVERSATIONS_DEFAULT_LIMIT = 100;
const CONVERSATIONS_MAX_LIMIT = 300;
const CONVERSATIONS_DEFAULT_LOOKBACK_HOURS = 24;
const CONVERSATIONS_MAX_SCAN_PAGES = 25;
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

export function magicLinkBaseWithReturnPath(returnPath = '') {
  const raw = String(returnPath || '').trim();
  const safeReturnPath = raw && raw.startsWith('/') && !raw.startsWith('//')
    ? raw.slice(0, 500)
    : '/chat/';
  try {
    const base = new URL(process.env.THINGY_MAGIC_LINK_BASE_URL || 'https://thingy.thingelstad.com/');
    base.pathname = '/signin/';
    base.search = '';
    base.searchParams.set('return', safeReturnPath);
    base.hash = '';
    return base.toString();
  } catch {
    return undefined;
  }
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

async function recordSessionForSub(sessionId, sub, expiresAt) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return;
  const start = performance.now();
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      pk: dynamoString(`session#${sessionId}`),
      sk: dynamoString('session'),
      email_hash: dynamoString(String(sub || '')),
      expires_at: dynamoNumber(expiresAt),
      ttl: dynamoNumber(expiresAt)
    }
  }));
  logEvent('info', 'session_refreshed_recorded', {
    subscriber_hash: sub,
    duration_ms: Math.round(performance.now() - start)
  });
}

function bedrockMessageText(message) {
  return (message?.content || []).map((part) => part.text || '').filter(Boolean).join('\n').trim();
}

async function generatePremiumThankYou() {
  const start = performance.now();
  const model = fastModel();
  const response = await bedrock.send(new ConverseCommand({
    modelId: model,
    system: [{ text: premiumThankYouSystemPrompt() }, { cachePoint: { type: 'default' } }],
    messages: [{ role: 'user', content: [{ text: 'Generate a fresh thank-you under 28 words.' }] }],
    inferenceConfig: { maxTokens: 120, temperature: 0.7 }
  }));
  const text = bedrockMessageText(response.output?.message || {}).replace(/\s+/g, ' ').trim();
  if (!text || text.length > 220) throw new Error('Bedrock returned invalid premium thank-you');
  logEvent('info', 'premium_thank_you_generated', {
    model,
    duration_ms: Math.round(performance.now() - start),
    message_chars: text.length
  });
  return text;
}

async function authSuccessResponse(email, subscriber, source, event, start) {
  const status = subscriberStatus(subscriber);
  const entitlements = entitlementsForSubscriber({ email, subscriber, status });
  const modes = availableConversationModes(entitlements);
  const { sessionId, expiresAt, token } = createSessionToken(email, undefined, { entitlements });
  await recordSession(sessionId, email, expiresAt);
  logEvent('info', 'auth_succeeded', {
    email_hash: emailHash(email),
    subscriber_status: status,
    entitlements,
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
    email: normalizeEmail(email),
    token,
    expires_at: expiresAt,
    entitlements,
    modes,
    profile: {
      ...authProfile(memory),
      entitlements,
      modes
    }
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

function entitlementsForSessionPayload(payload) {
  const entitlements = new Set(Array.isArray(payload?.entitlements) ? payload.entitlements : ['reader']);
  if (isOwnerSubscriberHash(payload?.sub)) {
    entitlements.add('owner');
    entitlements.add('supporting_member');
    entitlements.add('trusted_circle');
  }
  if (!entitlements.size) entitlements.add('reader');
  return Array.from(entitlements);
}

async function refreshSession(event, body, start) {
  const bearer = extractBearer(event, body);
  const payload = verifyToken(bearer);
  if (!payload?.sub) {
    logEvent('info', 'auth_refresh_rejected');
    return jsonResponse(401, { error: 'Sign in again to continue.' }, event);
  }
  const entitlements = entitlementsForSessionPayload(payload);
  const modes = availableConversationModes(entitlements);
  const { sessionId, expiresAt, token } = createSessionTokenForSub(payload.sub, undefined, { entitlements });
  await recordSessionForSub(sessionId, payload.sub, expiresAt);
  const memory = await getUserMemory(payload.sub);
  logEvent('info', 'auth_refreshed', {
    subscriber_hash: payload.sub,
    entitlements,
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'refreshed',
    token,
    expires_at: expiresAt,
    entitlements,
    modes,
    profile: {
      ...authProfile(memory),
      entitlements,
      modes
    }
  }, event);
}

async function updateProfile(event, body, start) {
  const payload = verifyToken(extractBearer(event, body));
  if (!payload?.sub) {
    logEvent('info', 'auth_update_profile_rejected');
    return jsonResponse(401, { error: 'Sign in again to continue.' }, event);
  }
  const preferredName = String(body.preferred_name || body.name || '')
    .trim()
    .replace(/\s+/g, ' ')
    .slice(0, 80);
  if (!/^[a-z][a-z .'’-]{0,78}$/i.test(preferredName)) {
    return jsonResponse(400, { error: 'Enter a name Thingy should use.' }, event);
  }
  const blocked = new Set(['hello', 'hi', 'hey', 'there', 'thingy', 'thanks', 'thank', 'yes', 'no', 'ok', 'okay']);
  if (preferredName.split(/\s+/).some((word) => blocked.has(word.toLowerCase()))) {
    return jsonResponse(400, { error: 'Enter a name Thingy should use.' }, event);
  }
  await recordUserPreferredName(payload.sub, preferredName);
  const memory = await getUserMemory(payload.sub);
  const entitlements = entitlementsForSessionPayload(payload);
  const modes = availableConversationModes(entitlements);
  logEvent('info', 'auth_profile_updated', {
    subscriber_hash: payload.sub,
    has_preferred_name: Boolean(preferredName),
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'updated',
    entitlements,
    modes,
    profile: {
      ...authProfile(memory),
      preferred_name: memory?.preferred_name || preferredName,
      entitlements,
      modes
    }
  }, event);
}

async function storeMagicLink({ token, email, source, event, subscriberStatusValue, nowSeconds, expiresAt }) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) throw new Error('TABLE_NAME is required');
  const tokenHash = magicTokenHash(token);
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      pk: dynamoString(`magic#${tokenHash}`),
      sk: dynamoString('magic'),
      email: dynamoString(normalizeEmail(email)),
      email_hash: dynamoString(emailHash(email)),
      source: dynamoString(source),
      subscriber_status: dynamoString(subscriberStatusValue),
      client_hash: dynamoString(clientIdentityHash(event)),
      created_at: dynamoNumber(nowSeconds),
      expires_at: dynamoNumber(expiresAt),
      ttl: dynamoNumber(expiresAt)
    }
  }));
}

async function sendLoginMagicLink({ email, subscriber, source, event, start, returnPath = '' }) {
  const hashedEmail = emailHash(email);
  const magicLimit = Number(process.env.THINGY_MAGIC_LINK_RATE_LIMIT_MAX || MAGIC_LINK_RATE_LIMIT_MAX);
  if (!(await checkRateLimit(`auth#magic:${hashedEmail}`, magicLimit))) {
    logEvent('warning', 'auth_magic_link_rate_limited', { email_hash: hashedEmail });
    return jsonResponse(429, { error: 'Too many sign-in emails. Please wait a bit and try again.' }, event);
  }
  const nowSeconds = Math.floor(Date.now() / 1000);
  const ttlSeconds = magicLinkTtlSeconds();
  const expiresAt = nowSeconds + ttlSeconds;
  const token = createMagicToken();
  const link = buildMagicLink(token, magicLinkBaseWithReturnPath(returnPath));
  const status = subscriberStatus(subscriber);
  let memory = null;
  try {
    memory = await getUserMemory(hashedEmail);
  } catch (error) {
    logEvent('warning', 'auth_magic_link_memory_lookup_failed', errorFields(error, { email_hash: hashedEmail }));
  }
  const emailContext = {
    ...authProfile(memory),
    subscriber_status: status,
    source
  };
  await storeMagicLink({ token, email, source, event, subscriberStatusValue: status, nowSeconds, expiresAt });
  await sendMagicLinkEmail({
    to: normalizeEmail(email),
    magicLink: link,
    expiresMinutes: Math.max(1, Math.round(ttlSeconds / 60)),
    context: emailContext
  });
  logEvent('info', 'auth_magic_link_sent', {
    email_hash: hashedEmail,
    subscriber_status: status,
    returning: Boolean(emailContext.returning),
    has_preferred_name: Boolean(emailContext.preferred_name),
    expires_at: expiresAt,
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'magic_link_sent',
    email: normalizeEmail(email),
    expires_at: expiresAt,
    message: 'Check your email for a sign-in link to Thingy.'
  }, event);
}

async function completeMagicLink(event, body, start) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return jsonResponse(500, { error: 'Thingy sign-in is unavailable right now.' }, event);
  const token = validMagicToken(body.login_token || body.magic_token || body.token);
  if (!token) {
    logEvent('info', 'auth_magic_link_invalid_token');
    return jsonResponse(400, { status: 'magic_link_invalid', error: 'That sign-in link is invalid or expired.' }, event);
  }
  const tokenHash = magicTokenHash(token);
  const key = {
    pk: dynamoString(`magic#${tokenHash}`),
    sk: dynamoString('magic')
  };
  const loaded = await dynamodb.send(new GetItemCommand({ TableName: tableName, Key: key }));
  const item = loaded.Item || null;
  const email = normalizeEmail(item?.email?.S || '');
  const expiresAt = Number(item?.expires_at?.N || 0);
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (!item || !email || expiresAt < nowSeconds || item.used_at) {
    logEvent('info', 'auth_magic_link_rejected', {
      token_hash_prefix: tokenHash.slice(0, 10),
      reason: !item ? 'not_found' : expiresAt < nowSeconds ? 'expired' : 'used'
    });
    return jsonResponse(400, { status: 'magic_link_invalid', error: 'That sign-in link is invalid or expired.' }, event);
  }
  try {
    await dynamodb.send(new UpdateItemCommand({
      TableName: tableName,
      Key: key,
      UpdateExpression: 'SET #used_at = :used_at, #used_client_hash = :client_hash',
      ConditionExpression: 'attribute_exists(pk) AND attribute_not_exists(#used_at) AND #expires_at >= :now',
      ExpressionAttributeNames: {
        '#used_at': 'used_at',
        '#used_client_hash': 'used_client_hash',
        '#expires_at': 'expires_at'
      },
      ExpressionAttributeValues: {
        ':used_at': dynamoNumber(nowSeconds),
        ':client_hash': dynamoString(clientIdentityHash(event)),
        ':now': dynamoNumber(nowSeconds)
      }
    }));
  } catch (error) {
    logEvent('info', 'auth_magic_link_redeem_race', {
      token_hash_prefix: tokenHash.slice(0, 10),
      error_type: error.constructor?.name || 'Error'
    });
    return jsonResponse(400, { status: 'magic_link_invalid', error: 'That sign-in link is invalid or expired.' }, event);
  }

  let subscriber;
  try {
    subscriber = await fetchSubscriber(email);
  } catch (error) {
    logEvent('error', 'auth_magic_link_buttondown_lookup_failed', { email_hash: emailHash(email), error_type: error.constructor?.name || 'Error' });
    return jsonResponse(502, { error: 'Could not validate subscriber status right now.' }, event);
  }
  const status = subscriberStatus(subscriber);
  if (status !== 'active' && status !== 'premium') {
    logEvent('info', 'auth_magic_link_subscriber_not_active', { email_hash: emailHash(email), subscriber_status: status });
    return jsonResponse(403, { status, error: 'That subscription is not active.' }, event);
  }
  return authSuccessResponse(email, subscriber, 'thingy', event, start);
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

// --- operator-only: canonical Thingy conversation reads ---
// Gated by the same DISCORD_BRIDGE_SECRET as the bridge mint (operator
// secret, never a per-user token). Used by workshop_bot to surface what
// readers are asking Thingy. Conversation metadata and turns are the
// canonical server-side records under user#<subscriberHash>.

function bridgeSecretOk(body) {
  const expected = process.env.DISCORD_BRIDGE_SECRET || '';
  if (!expected) return null; // bridge disabled
  const expectedBuf = Buffer.from(expected, 'utf8');
  const suppliedBuf = Buffer.from(String(body.bridge_secret || ''), 'utf8');
  return expectedBuf.length === suppliedBuf.length && crypto.timingSafeEqual(expectedBuf, suppliedBuf);
}

function normalizeListConversationsParams(body = {}, now = Date.now()) {
  let since = String(body.since || '').trim();
  if (!since || Number.isNaN(Date.parse(since))) {
    since = new Date(now - CONVERSATIONS_DEFAULT_LOOKBACK_HOURS * 3600 * 1000).toISOString();
  }
  let limit = Number(body.limit || CONVERSATIONS_DEFAULT_LIMIT);
  if (!Number.isFinite(limit) || limit <= 0) limit = CONVERSATIONS_DEFAULT_LIMIT;
  limit = Math.min(Math.floor(limit), CONVERSATIONS_MAX_LIMIT);
  return { since, limit };
}

function subscriberHashFromUserPk(pk) {
  const text = String(pk || '');
  return text.startsWith('user#') ? text.slice('user#'.length) : '';
}

async function handleListOperatorConversations(event, body, start) {
  const secretState = bridgeSecretOk(body);
  if (secretState === null) {
    logEvent('warning', 'auth_operator_conversations_bridge_disabled');
    return jsonResponse(503, { error: 'Discord bridge is not enabled.' }, event);
  }
  if (!secretState) {
    logEvent('warning', 'auth_operator_conversations_bad_secret');
    return jsonResponse(401, { error: 'Bridge secret rejected.' }, event);
  }
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return jsonResponse(500, { error: 'Conversation history is unavailable right now.' }, event);

  const { since: sinceIso, limit } = normalizeListConversationsParams(body);
  const evalStatus = String(body.eval_status || '').trim();
  const rows = [];
  let exclusiveStartKey;
  let pages = 0;
  try {
    do {
      const resp = await dynamodb.send(new ScanCommand({
        TableName: tableName,
        FilterExpression: 'begins_with(#pk, :user_prefix) AND begins_with(#sk, :conversation_prefix) AND #updated_at >= :since',
        ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk', '#updated_at': 'updated_at' },
        ExpressionAttributeValues: {
          ':user_prefix': { S: 'user#' },
          ':conversation_prefix': { S: 'conversation#' },
          ':since': { S: sinceIso }
        },
        ExclusiveStartKey: exclusiveStartKey
      }));
      for (const item of resp.Items || []) {
        const conversation = conversationSummaryFromItem(item);
        if (evalStatus && conversation.eval_status !== evalStatus) continue;
        rows.push({
          ...conversation,
          subscriber_hash: subscriberHashFromUserPk(item.pk?.S)
        });
      }
      exclusiveStartKey = resp.LastEvaluatedKey;
      pages += 1;
    } while (exclusiveStartKey && pages < CONVERSATIONS_MAX_SCAN_PAGES);
  } catch (error) {
    logEvent('error', 'auth_operator_conversations_scan_failed', { error_type: error.constructor?.name || 'Error' });
    return jsonResponse(502, { error: 'Could not read canonical conversations right now.' }, event);
  }

  const sorted = rows
    .sort((a, b) => String(a.updated_at || '').localeCompare(String(b.updated_at || '')))
    .slice(-limit);
  const truncated = Boolean(exclusiveStartKey) || sorted.length < rows.length;
  logEvent('info', 'auth_operator_conversations_listed', {
    since: sinceIso,
    returned: sorted.length,
    scanned_pages: pages,
    truncated,
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    since: sinceIso,
    count: sorted.length,
    truncated,
    eval_status: evalStatus || null,
    conversations: sorted
  }, event);
}

async function findOperatorConversationMetadata(tableName, conversationId, subscriberHash = '') {
  if (subscriberHash) {
    const conversation = await getUserConversationMetadata({ dynamodb, tableName, subscriberHash, conversationId });
    return conversation ? { conversation: { ...conversation, subscriber_hash: subscriberHash }, subscriberHash } : null;
  }
  let exclusiveStartKey;
  let pages = 0;
  do {
    const response = await dynamodb.send(new ScanCommand({
      TableName: tableName,
      FilterExpression: 'begins_with(#pk, :user_prefix) AND #sk = :conversation_sk',
      ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
      ExpressionAttributeValues: {
        ':user_prefix': { S: 'user#' },
        ':conversation_sk': conversationDynamoString(conversationSk(conversationId))
      },
      ExclusiveStartKey: exclusiveStartKey
    }));
    const item = (response.Items || [])[0];
    if (item) {
      const foundSubscriberHash = subscriberHashFromUserPk(item.pk?.S);
      return {
        conversation: { ...conversationSummaryFromItem(item), subscriber_hash: foundSubscriberHash },
        subscriberHash: foundSubscriberHash
      };
    }
    exclusiveStartKey = response.LastEvaluatedKey;
    pages += 1;
  } while (exclusiveStartKey && pages < CONVERSATIONS_MAX_SCAN_PAGES);
  return null;
}

async function handleGetOperatorConversation(event, body, start) {
  const secretState = bridgeSecretOk(body);
  if (secretState === null) {
    logEvent('warning', 'auth_operator_conversation_bridge_disabled');
    return jsonResponse(503, { error: 'Discord bridge is not enabled.' }, event);
  }
  if (!secretState) {
    logEvent('warning', 'auth_operator_conversation_bad_secret');
    return jsonResponse(401, { error: 'Bridge secret rejected.' }, event);
  }
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return jsonResponse(500, { error: 'Conversation history is unavailable right now.' }, event);

  const conversationId = validConversationId(body.conversation_id || body.id);
  if (!conversationId) return jsonResponse(400, { error: 'conversation_id is required.' }, event);
  const subscriberHash = String(body.subscriber_hash || '').trim();
  try {
    const found = await findOperatorConversationMetadata(tableName, conversationId, subscriberHash);
    if (!found) return jsonResponse(404, { error: 'Conversation not found.' }, event);
    const limit = Math.max(1, Math.min(Number(body.limit || 80) || 80, 120));
    const response = await dynamodb.send(new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
      ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
      ExpressionAttributeValues: {
        ':pk': conversationDynamoString(userConversationPk(found.subscriberHash)),
        ':prefix': conversationDynamoString(turnSkPrefix(conversationId))
      },
      ScanIndexForward: false,
      Limit: limit
    }));
    const turns = (response.Items || [])
      .map(conversationTurnFromItem)
      .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    logEvent('info', 'auth_operator_conversation_loaded', {
      subscriber_hash: found.subscriberHash,
      conversation_id: conversationId,
      turn_count: turns.length,
      duration_ms: Math.round(performance.now() - start)
    });
    return jsonResponse(200, { conversation: found.conversation, turns }, event);
  } catch (error) {
    logEvent('error', 'auth_operator_conversation_load_failed', {
      conversation_id: conversationId,
      error_type: error.constructor?.name || 'Error'
    });
    return jsonResponse(502, { error: 'Could not read the conversation right now.' }, event);
  }
}

function conversationAuth(event, body) {
  const payload = verifyToken(extractBearer(event, body));
  return payload || null;
}

function conversationTableUnavailable(event) {
  return jsonResponse(500, { error: 'Thingy conversation history is unavailable right now.' }, event);
}

async function handleUserConversations(event, body, start) {
  const payload = conversationAuth(event, body);
  const subscriberHash = payload ? String(payload.sub || '') : '';
  if (!subscriberHash) {
    return jsonResponse(401, { error: 'Please validate your subscriber email to use Thingy.' }, event);
  }
  const entitlements = entitlementsForSessionPayload(payload);
  const modes = availableConversationModes(entitlements);
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return conversationTableUnavailable(event);

  const action = String(body.action || 'list').trim().toLowerCase();
  try {
    if (action === 'list') {
      const conversations = await loadUserConversationSummaries({
        dynamodb,
        tableName,
        subscriberHash,
        limit: body.limit || USER_CONVERSATION_LIMIT,
        logEvent
      });
      logEvent('info', 'user_conversations_listed', {
        subscriber_hash: subscriberHash,
        count: conversations.length,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, { conversations, entitlements, modes }, event);
    }

    if (action === 'get') {
      const conversationId = validConversationId(body.conversation_id || body.id);
      if (!conversationId) return jsonResponse(400, { error: 'conversation_id is required.' }, event);
      const result = await getUserConversation({ dynamodb, tableName, subscriberHash, conversationId, limit: body.limit });
      if (!result) return jsonResponse(404, { error: 'Conversation not found.' }, event);
      return jsonResponse(200, result, event);
    }

    if (action === 'create') {
      const mode = normalizeConversationMode(body.mode);
      if (!canUseConversationMode(mode, entitlements)) {
        return jsonResponse(403, { error: 'That Thingy mode is not available for this account.' }, event);
      }
      const conversationId = crypto.randomUUID();
      const conversation = await createUserConversation({
        dynamodb,
        tableName,
        subscriberHash,
        conversationId,
        title: body.title || body.message || '',
        preview: body.message || body.title || '',
        scope: body.scope || 'all',
        mode
      });
      return jsonResponse(200, { conversation }, event);
    }

    if (action === 'rename') {
      const conversationId = validConversationId(body.conversation_id || body.id);
      if (!conversationId) return jsonResponse(400, { error: 'conversation_id is required.' }, event);
      const conversation = await renameUserConversation({
        dynamodb,
        tableName,
        subscriberHash,
        conversationId,
        title: body.title
      });
      return jsonResponse(200, { conversation }, event);
    }

    if (action === 'delete' || action === 'trash') {
      const conversationId = validConversationId(body.conversation_id || body.id);
      if (!conversationId) return jsonResponse(400, { error: 'conversation_id is required.' }, event);
      const keys = [{
        pk: conversationDynamoString(userConversationPk(subscriberHash)),
        sk: conversationDynamoString(conversationSk(conversationId))
      }];
      let exclusiveStartKey;
      do {
        const response = await dynamodb.send(new QueryCommand({
          TableName: tableName,
          KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
          ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
          ExpressionAttributeValues: {
            ':pk': conversationDynamoString(userConversationPk(subscriberHash)),
            ':prefix': conversationDynamoString(turnSkPrefix(conversationId))
          },
          ExclusiveStartKey: exclusiveStartKey
        }));
        for (const item of response.Items || []) keys.push({ pk: item.pk, sk: item.sk });
        exclusiveStartKey = response.LastEvaluatedKey;
      } while (exclusiveStartKey);

      for (let index = 0; index < keys.length; index += 25) {
        await dynamodb.send(new BatchWriteItemCommand({
          RequestItems: {
            [tableName]: keys.slice(index, index + 25).map((Key) => ({ DeleteRequest: { Key } }))
          }
        }));
      }
      logEvent('info', 'user_conversation_deleted', {
        subscriber_hash: subscriberHash,
        conversation_id: conversationId,
        deleted_items: keys.length,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, { ok: true, conversation_id: conversationId, deleted_items: keys.length }, event);
    }
  } catch (error) {
    if (error.name === 'ConditionalCheckFailedException') {
      return jsonResponse(404, { error: 'Conversation not found.' }, event);
    }
    logEvent('error', 'user_conversations_action_failed', {
      subscriber_hash: subscriberHash,
      action,
      error_type: error.constructor?.name || 'Error'
    });
    return jsonResponse(502, { error: 'Thingy could not update conversations right now.' }, event);
  }

  return jsonResponse(400, { error: 'Unsupported conversation action.' }, event);
}

function dispatchAuth(event, body) {
  const payload = verifyToken(extractBearer(event, body));
  return payload || null;
}

function normalizeDispatchText(value, max = 1400) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function isMeaningfulDispatchPrompt(value) {
  const text = normalizeDispatchText(value, 1200);
  if (text.length >= 8) return true;
  return /[a-z0-9]{2,}/i.test(text);
}

function dispatchConversationLines(messages = []) {
  if (!Array.isArray(messages)) return [];
  return messages
    .slice(-10)
    .map((message) => {
      const role = message?.role === 'user' ? 'Reader' : 'Thingy';
      const text = normalizeDispatchText(message?.text, 500);
      return text ? `${role}: ${text}` : '';
    })
    .filter(Boolean);
}

function terseDispatchSeed(value) {
  const text = normalizeDispatchText(value, 1200);
  if (/[?!.]/.test(text)) return false;
  return text.length > 0 && text.length <= 28 && text.split(/\s+/).filter(Boolean).length <= 3;
}

function readyMessageClaimsStarted(value) {
  return /\b(?:generating now|generate now|drafting now|sending now|emailing now)\b/i.test(String(value || ''));
}

function dispatchProfile(payload) {
  const entitlements = entitlementsForSessionPayload(payload);
  const owner = entitlements.includes('owner') || isOwnerSubscriberHash(payload?.sub);
  return {
    subscriberHash: String(payload?.sub || ''),
    entitlements,
    supportingMember: entitlements.includes('supporting_member'),
    owner
  };
}

async function clarifyDispatch({ prompt, priorQuestion = '', priorAnswer = '', messages = [] }) {
  const model = fastModel();
  const transcript = dispatchConversationLines(messages);
  const response = await bedrock.send(new ConverseCommand({
    modelId: model,
    system: [{
      text: [
        'You are Thingy, Jamie Thingelstad\'s archive sidekick.',
        'A reader is shaping a one-off Thingy Dispatch from Jamie\'s published archive.',
        'This is a conversational drafting surface, not a form validator.',
        'Terse archive concepts like "RSS", "AI", "POSSE", or "IndieWeb" are valid Dispatch seeds.',
        'For a terse or broad first seed, ask one concrete clarification that offers useful archive angles.',
        'When the reader answers a prior clarification, fold that answer into the confirmed direction instead of asking the same thing again.',
        'When the reader adjusts a ready direction, revise the direction and briefly acknowledge the change.',
        'Ask at most one useful clarification question before expensive generation.',
        'If the request is already specific enough, do not ask a question.',
        'Return only compact JSON: {"needs_clarification":true|false,"question":"...","direction":"confirmed generation direction","message":"Thingy response to show the reader"}'
      ].join('\n')
    }],
    messages: [{
      role: 'user',
      content: [{
        text: [
          `Reader prompt: ${prompt}`,
          priorQuestion ? `Prior clarification question: ${priorQuestion}` : '',
          priorAnswer ? `Reader answer: ${priorAnswer}` : '',
          transcript.length ? `Recent Dispatch conversation:\n${transcript.join('\n')}` : ''
        ].filter(Boolean).join('\n')
      }]
    }],
    inferenceConfig: {
      maxTokens: 420,
      temperature: 0.2
    }
  }));
  const text = bedrockMessageText(response.output?.message || {});
  const raw = text.match(/\{[\s\S]*\}/)?.[0] || text;
  let parsed = {};
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = {};
  }
  const question = normalizeDispatchText(parsed.question, 260);
  const direction = normalizeDispatchText(parsed.direction || prompt, 1000);
  const alreadyAnswered = Boolean(priorQuestion && priorAnswer);
  const shouldClarifyTerseSeed = terseDispatchSeed(prompt) && !priorQuestion && !priorAnswer;
  const needsClarification = Boolean((parsed.needs_clarification || shouldClarifyTerseSeed) && !alreadyAnswered);
  const fallbackQuestion = question || `Good seed. What angle should this Dispatch take on ${normalizeDispatchText(prompt, 80)}?`;
  let message = normalizeDispatchText(parsed.message, 700) || (
    needsClarification
      ? fallbackQuestion
      : `I have enough to shape this Dispatch around: ${direction || prompt}`
  );
  if (!needsClarification && (message.includes('?') || readyMessageClaimsStarted(message))) {
    message = `I have enough to shape this Dispatch around: ${direction || prompt}`;
  }
  return {
    needs_clarification: needsClarification,
    question: needsClarification ? fallbackQuestion : '',
    direction: direction || prompt,
    message
  };
}

async function handleDispatch(event, body, start) {
  const payload = dispatchAuth(event, body);
  const profile = payload ? dispatchProfile(payload) : null;
  if (!profile?.subscriberHash) {
    return jsonResponse(401, { error: 'Please sign in to use Dispatch.' }, event);
  }
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return jsonResponse(500, { error: 'Dispatch is unavailable right now.' }, event);

  const action = String(body.action || 'list').trim().toLowerCase();
  try {
    if (action === 'clarify') {
      const prompt = normalizeDispatchText(body.prompt || body.topic, 1200);
      if (!isMeaningfulDispatchPrompt(prompt)) return jsonResponse(400, { error: 'Dispatch needs a topic or question.' }, event);
      const clarification = await clarifyDispatch({
        prompt,
        priorQuestion: body.clarification_question,
        priorAnswer: body.clarification_answer,
        messages: body.messages
      });
      logEvent('info', 'dispatch_clarified', {
        subscriber_hash: profile.subscriberHash,
        needs_clarification: clarification.needs_clarification,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, {
        ...clarification,
        entitlements: profile.entitlements,
        supporting_member: profile.supportingMember,
        owner: profile.owner
      }, event);
    }

    if (action === 'save_draft') {
      const prompt = normalizeDispatchText(body.prompt || body.topic, 1200);
      const direction = normalizeDispatchText(body.direction || prompt, 1600);
      const title = normalizeDispatchText(body.title || body.topic || prompt || 'Dispatch', 120);
      const dispatch = await upsertDispatchDraft({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        dispatchId: body.dispatch_id || body.id,
        status: body.status || body.stage || 'draft',
        topic: body.topic || prompt || title,
        prompt,
        direction,
        clarificationQuestion: body.clarification_question,
        clarificationAnswer: body.clarification_answer,
        title,
        messages: Array.isArray(body.messages) ? body.messages : []
      });
      logEvent('info', 'dispatch_draft_saved', {
        subscriber_hash: profile.subscriberHash,
        dispatch_id: dispatch.id,
        status: dispatch.status,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, {
        dispatch: dispatchForClient(dispatch),
        entitlements: profile.entitlements,
        supporting_member: profile.supportingMember,
        owner: profile.owner
      }, event);
    }

    if (action === 'list') {
      const dispatches = await listUserDispatches({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        limit: body.limit || 12
      });
      const availability = await dispatchAvailability({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        owner: profile.owner
      });
      return jsonResponse(200, {
        dispatches: dispatches.map(dispatchForClient),
        availability,
        entitlements: profile.entitlements,
        supporting_member: profile.supportingMember,
        owner: profile.owner
      }, event);
    }

    if (action === 'status') {
      const dispatch = await getUserDispatch({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        dispatchId: body.dispatch_id || body.id
      });
      if (!dispatch) return jsonResponse(404, { error: 'Dispatch not found.' }, event);
      return jsonResponse(200, {
        dispatch: dispatchForClient(dispatch)
      }, event);
    }

    if (action === 'delete') {
      const dispatch = await deleteUserDispatch({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        dispatchId: body.dispatch_id || body.id
      });
      if (!dispatch) return jsonResponse(404, { error: 'Dispatch not found.' }, event);
      logEvent('info', 'dispatch_deleted', {
        subscriber_hash: profile.subscriberHash,
        dispatch_id: dispatch.id,
        status: dispatch.status,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, {
        status: 'deleted',
        dispatch_id: dispatch.id
      }, event);
    }

    if (action === 'create') {
      if (!profile.supportingMember && !profile.owner) {
        return jsonResponse(403, {
          error: 'Dispatch is available to Weekly Thing Supporting Members.',
          status: 'supporting_member_required',
          message: 'You can shape the Dispatch here. Sending it requires a Supporting Membership.'
        }, event);
      }
      const prompt = normalizeDispatchText(body.prompt || body.topic, 1200);
      const direction = normalizeDispatchText(body.direction || prompt, 1600);
      const toEmail = normalizeEmail(body.email || body.to_email);
      const templateTest = Boolean(body.template_test || body.templateTest || body.test_mode === 'template');
      if (templateTest && !profile.owner) {
        return jsonResponse(403, { error: 'Dispatch template tests are owner-only.' }, event);
      }
      if (!prompt || !direction) return jsonResponse(400, { error: 'Dispatch needs a confirmed direction.' }, event);
      if (!EMAIL_RE.test(toEmail) || emailHash(toEmail) !== profile.subscriberHash) {
        return jsonResponse(403, { error: 'Dispatch can only be sent to your signed-in email address.' }, event);
      }
      const availability = await dispatchAvailability({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        owner: profile.owner
      });
      if (!availability.allowed) {
        return jsonResponse(429, { error: availability.message || 'Dispatch is rate limited.', availability }, event);
      }
      const existingDispatchId = body.dispatch_id || body.id;
      const dispatch = existingDispatchId
        ? await queueDraftDispatch({
          dynamodb,
          tableName,
          subscriberHash: profile.subscriberHash,
          dispatchId: existingDispatchId,
          emailHash: profile.subscriberHash,
          toEmail,
          topic: body.topic || prompt,
          prompt,
          direction,
          clarificationQuestion: body.clarification_question,
          clarificationAnswer: body.clarification_answer,
          templateTest
        })
        : await createQueuedDispatch({
          dynamodb,
          tableName,
          subscriberHash: profile.subscriberHash,
          emailHash: profile.subscriberHash,
          toEmail,
          topic: body.topic || prompt,
          prompt,
          direction,
          clarificationQuestion: body.clarification_question,
          clarificationAnswer: body.clarification_answer,
          templateTest
        });
      logEvent('info', 'dispatch_queued', {
        subscriber_hash: profile.subscriberHash,
        dispatch_id: dispatch.id,
        template_test: templateTest,
        owner: profile.owner,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(202, {
        dispatch: dispatchForClient(dispatch)
      }, event);
    }
  } catch (error) {
    logEvent('error', 'dispatch_action_failed', {
      subscriber_hash: profile.subscriberHash,
      action,
      error_type: error.constructor?.name || 'Error'
    });
    return jsonResponse(502, { error: 'Dispatch is unavailable right now.' }, event);
  }

  return jsonResponse(400, { error: 'Unsupported Dispatch action.' }, event);
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
  if (![
    'check',
    'subscribe',
    'resend_confirmation',
    'complete_magic_link',
    'refresh_session',
    'update_profile',
    'discord_bridge',
    'list_operator_conversations',
    'get_operator_conversation'
  ].includes(action)) {
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

  // Operator-only canonical conversation reads (thingy_bridge). Also email-less —
  // gated by the bridge secret, not a subscriber session.
  if (action === 'list_operator_conversations') {
    return await handleListOperatorConversations(event, body, start);
  }

  if (action === 'get_operator_conversation') {
    return await handleGetOperatorConversation(event, body, start);
  }

  if (action === 'complete_magic_link') {
    return await completeMagicLink(event, body, start);
  }

  if (action === 'refresh_session') {
    return await refreshSession(event, body, start);
  }

  if (action === 'update_profile') {
    return await updateProfile(event, body, start);
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
  try {
    return await sendLoginMagicLink({ email, subscriber, source, event, start, returnPath: body.return_path });
  } catch (error) {
    logEvent('error', 'auth_magic_link_send_failed', errorFields(error, { email_hash: hashedEmail }));
    return jsonResponse(502, { error: 'Could not send a sign-in email right now.' }, event);
  }
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
    } else if (method === 'POST' && path.endsWith('/conversations')) {
      response = await handleUserConversations(event, parseBody(event), start);
    } else if (method === 'POST' && path.endsWith('/dispatch')) {
      response = await handleDispatch(event, parseBody(event), start);
    } else {
      response = jsonResponse(404, { error: 'Not found.' }, event);
    }
  } catch (error) {
    logEvent('error', 'request_failed', errorFields(error, summary), 'weekly-thing-librarian-auth');
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
