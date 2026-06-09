import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { BatchWriteItemCommand, GetItemCommand, PutItemCommand, QueryCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
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
  dynamoString as conversationDynamoString,
  turnSkPrefix,
  userConversationPk,
  validConversationId
} from '../shared/user-conversations.mjs';
import {
  createUserConversation,
  getUserConversation,
  loadUserConversationSummaries,
  renameUserConversation
} from '../shared/conversation-store.mjs';
import { handleDispatch } from './dispatch-routes.mjs';

const AUTH_RATE_LIMIT_MAX = 30;
const MAGIC_LINK_RATE_LIMIT_MAX = 6;
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function batchDeleteKeys(tableName, keys, maxAttempts = 5) {
  let deleted = 0;
  for (let index = 0; index < keys.length; index += 25) {
    let requests = keys.slice(index, index + 25).map((Key) => ({ DeleteRequest: { Key } }));
    for (let attempt = 1; requests.length && attempt <= maxAttempts; attempt += 1) {
      const response = await dynamodb.send(new BatchWriteItemCommand({
        RequestItems: {
          [tableName]: requests
        }
      }));
      const unprocessed = response.UnprocessedItems?.[tableName] || [];
      deleted += requests.length - unprocessed.length;
      requests = unprocessed;
      if (requests.length && attempt < maxAttempts) {
        await sleep(50 * (2 ** (attempt - 1)));
      }
    }
    if (requests.length) {
      throw new Error(`DynamoDB left ${requests.length} delete request(s) unprocessed`);
    }
  }
  return deleted;
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

export function entitlementsForSessionPayload(payload, nowSeconds = Math.floor(Date.now() / 1000)) {
  const entitlementsFresh = Number(payload?.entitlements_verified_until || 0) > nowSeconds;
  const entitlements = new Set(entitlementsFresh && Array.isArray(payload?.entitlements) ? payload.entitlements : ['reader']);
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
  const verifiedUntil = Number(payload.entitlements_verified_until || 0);
  const claims = verifiedUntil > Math.floor(Date.now() / 1000)
    ? { entitlements, entitlements_verified_until: verifiedUntil }
    : { entitlements };
  const { sessionId, expiresAt, token } = createSessionTokenForSub(payload.sub, undefined, claims);
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
  const write = await recordUserPreferredName(payload.sub, preferredName);
  if (!write?.ok) {
    logEvent('warning', 'auth_profile_update_failed', {
      subscriber_hash: payload.sub,
      error: write?.error || 'unknown',
      duration_ms: Math.round(performance.now() - start)
    });
    return jsonResponse(500, { error: 'Thingy could not save that name right now. Please try again.' }, event);
  }
  const memory = write.memory || await getUserMemory(payload.sub);
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

      const deletedItems = await batchDeleteKeys(tableName, keys);
      logEvent('info', 'user_conversation_deleted', {
        subscriber_hash: subscriberHash,
        conversation_id: conversationId,
        deleted_items: deletedItems,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, { ok: true, conversation_id: conversationId, deleted_items: deletedItems }, event);
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
    'discord_bridge'
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
