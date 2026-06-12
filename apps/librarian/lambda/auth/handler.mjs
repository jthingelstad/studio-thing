import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { GetItemCommand, PutItemCommand, TransactWriteItemsCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { bedrock, dynamodb, agentModel, fastModel } from '../shared/aws-clients.mjs';
import { createSubscriber, ensureThingyTag, fetchSubscriber, sanitizeAttribution, sendSubscriberReminder, subscriberStatus } from '../shared/buttondown.mjs';
import { eventSummary, jsonResponse, methodAndPath, parseBody, clientSourceIp, userAgent } from '../shared/http.mjs';
import { buildMagicLink, createMagicToken, magicLinkTtlSeconds, magicTokenHash, validMagicToken } from '../shared/magic-link.mjs';
import { sendMagicLinkEmail } from '../shared/jmap-mail.mjs';
import { checkRateLimit } from '../shared/rate-limit.mjs';
import { createSessionToken, createSessionTokenForSub, emailHash, extractBearer, normalizeEmail, stableHash, verifyToken } from '../shared/session.mjs';
import {
  authProfile,
  discordConnectionMemoryUpdate,
  getUserMemory,
  recordUserPreferredName
} from '../shared/user-memory.mjs';
import {
  deleteThingyProfile,
  sessionAllowedForThingyProfile
} from '../shared/profile-deletion.mjs';
import {
  DISCORD_LINK_TTL_SECONDS,
  createLinkCode,
  createLinkState,
  currentEntitlementsForEmail,
  discordCodeKey,
  discordConnectionPut,
  discordStateKey,
  discordUserHash,
  dynamoNumber,
  dynamoString,
  isSupportingEntitlement,
  linkHash,
  normalizeDiscordIdentity,
  nowSeconds
} from '../shared/discord-link.mjs';
import {
  availableConversationModes,
  entitlementsForSubscriber,
  isOwnerSubscriberHash
} from '../shared/conversation-modes.mjs';
import crypto from 'node:crypto';
import { errorFields, logEvent } from '../shared/logging.mjs';
import { premiumThankYouSystemPrompt } from '../shared/prompts.mjs';
import { handleUserConversations } from './conversation-routes.mjs';
import { handleDispatch } from './dispatch-routes.mjs';
import { loadUserConversationSummaries } from '../shared/conversation-store.mjs';

const AUTH_RATE_LIMIT_MAX = 30;
const MAGIC_LINK_RATE_LIMIT_MAX = 6;
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

function entitlementsWithOwner(subscriberHash, entitlements = []) {
  const values = new Set(Array.isArray(entitlements) ? entitlements : []);
  if (isOwnerSubscriberHash(subscriberHash)) {
    values.add('owner');
    values.add('supporting_member');
    values.add('trusted_circle');
  }
  if (!values.size) values.add('reader');
  return Array.from(values);
}

async function refreshSession(event, body, start) {
  const bearer = extractBearer(event, body);
  const payload = verifyToken(bearer);
  if (!payload?.sub || !(await sessionAllowedForThingyProfile(payload))) {
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
  if (!payload?.sub || !(await sessionAllowedForThingyProfile(payload))) {
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

async function memoryAccountConversations(sub) {
  return await loadUserConversationSummaries({
    dynamodb,
    tableName: process.env.TABLE_NAME,
    subscriberHash: sub,
    limit: 50,
    logEvent
  });
}

async function memoryProfileResponse(sub, event, extra = {}) {
  const memory = await getUserMemory(sub, { consistent: true });
  const conversations = await memoryAccountConversations(sub);
  const conversationDates = conversations
    .flatMap((conversation) => [conversation.created_at, conversation.updated_at, conversation.last_message_at])
    .filter(Boolean)
    .sort();
  const profile = authProfile(memory);
  const account = {
    first_seen_at: memory?.first_seen_at || '',
    last_seen_at: memory?.last_seen_at || '',
    memory_turn_count: Number(memory?.turn_count || 0),
    conversation_count: conversations.length,
    conversation_turn_count: conversations.reduce((sum, conversation) => sum + Number(conversation.turn_count || 0), 0),
    activity_summary: {
      memory_turn_count: Number(memory?.turn_count || 0),
      conversation_count: conversations.length,
      conversation_turn_count: conversations.reduce((sum, conversation) => sum + Number(conversation.turn_count || 0), 0)
    },
    oldest_conversation_at: conversationDates[0] || '',
    newest_conversation_at: conversationDates.at(-1) || ''
  };
  return jsonResponse(200, { status: 'ok', profile, account, ...extra }, event);
}

async function handleMemory(event, body, start) {
  const payload = verifyToken(extractBearer(event, body));
  if (!payload?.sub || !(await sessionAllowedForThingyProfile(payload))) {
    logEvent('info', 'memory_action_rejected');
    return jsonResponse(401, { error: 'Sign in again to continue.' }, event);
  }
  const action = String(body.action || 'get').trim().toLowerCase();
  if (action === 'get') {
    return await memoryProfileResponse(payload.sub, event);
  }
  if (action === 'refresh_profile') {
    // No-op kept so web clients deployed before the synthesized-memory
    // removal get a normal profile back instead of an error.
    return await memoryProfileResponse(payload.sub, event, { refreshed: false });
  }
  if (action === 'delete_profile') {
    const result = await deleteThingyProfile(payload.sub);
    if (!result.ok) return jsonResponse(500, { error: result.error || 'Thingy could not delete this profile right now.' }, event);
    logEvent('info', 'thingy_profile_delete_requested', {
      subscriber_hash: payload.sub,
      duration_ms: Math.round(performance.now() - start)
    });
    return jsonResponse(200, { status: 'deleted', ok: true, deleted_at: result.deleted_at }, event);
  }
  return jsonResponse(400, { error: 'Unsupported memory action.' }, event);
}

function bridgeSecretOk(body) {
  const expected = process.env.DISCORD_BRIDGE_SECRET || '';
  if (!expected) return null;
  const supplied = String(body.bridge_secret || body.secret || '');
  const expectedBuf = Buffer.from(expected, 'utf8');
  const suppliedBuf = Buffer.from(supplied, 'utf8');
  return expectedBuf.length === suppliedBuf.length && crypto.timingSafeEqual(expectedBuf, suppliedBuf);
}

function discordLinkBaseWithState(state) {
  try {
    const base = new URL(process.env.THINGY_MAGIC_LINK_BASE_URL || 'https://thingy.thingelstad.com/');
    base.pathname = '/discord/';
    base.search = '';
    base.searchParams.set('state', state);
    base.hash = '';
    return base.toString();
  } catch {
    return `https://thingy.thingelstad.com/discord/?state=${encodeURIComponent(state)}`;
  }
}

async function getDynamoItem(key, consistent = true) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) throw new Error('TABLE_NAME is required');
  const response = await dynamodb.send(new GetItemCommand({
    TableName: tableName,
    Key: key,
    ConsistentRead: consistent
  }));
  return response?.Item || null;
}

async function handleDiscordLinkStart(event, body, start) {
  const secretState = bridgeSecretOk(body);
  if (secretState === null) {
    logEvent('warning', 'discord_link_start_disabled');
    return jsonResponse(503, { error: 'Discord linking is not enabled.' }, event);
  }
  if (!secretState) {
    logEvent('warning', 'discord_link_start_bad_secret');
    return jsonResponse(401, { error: 'Bridge secret rejected.' }, event);
  }
  const userHash = discordUserHash(body.discord_user_id);
  if (!userHash) return jsonResponse(400, { error: 'discord_user_id is required.' }, event);
  const identity = normalizeDiscordIdentity(body);
  const state = createLinkState();
  const now = nowSeconds();
  const expiresAt = now + DISCORD_LINK_TTL_SECONDS;
  await dynamodb.send(new PutItemCommand({
    TableName: process.env.TABLE_NAME,
    Item: {
      ...discordStateKey(state),
      discord_user_hash: dynamoString(userHash),
      username: dynamoString(identity.username),
      global_name: dynamoString(identity.global_name),
      display_name: dynamoString(identity.display_name),
      guild_id: dynamoString(identity.guild_id),
      created_at: dynamoNumber(now),
      expires_at: dynamoNumber(expiresAt),
      ttl: dynamoNumber(expiresAt)
    }
  }));
  logEvent('info', 'discord_link_started', {
    discord_user_hash: userHash.slice(0, 12),
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'discord_link_started',
    state,
    link: discordLinkBaseWithState(state),
    expires_at: expiresAt
  }, event);
}

async function handleDiscordLinkCode(event, body, start) {
  const payload = verifyToken(extractBearer(event, body));
  if (!payload?.sub || !(await sessionAllowedForThingyProfile(payload))) {
    logEvent('info', 'discord_link_code_rejected_auth');
    return jsonResponse(401, { error: 'Sign in again to connect Discord.' }, event);
  }
  const email = normalizeEmail(body.email);
  if (!EMAIL_RE.test(email) || emailHash(email) !== payload.sub) {
    return jsonResponse(400, { error: 'Thingy needs your signed-in email to verify Discord access.' }, event);
  }
  const entitlement = await currentEntitlementsForEmail(email);
  const entitlements = entitlementsWithOwner(payload.sub, entitlement.entitlements);
  if (!isSupportingEntitlement(entitlements)) {
    logEvent('info', 'discord_link_code_not_supporting', { subscriber_hash: payload.sub, status: entitlement.status });
    return jsonResponse(403, {
      status: 'supporting_member_required',
      error: 'Discord is available to Weekly Thing Supporting Members.'
    }, event);
  }
  const state = String(body.state || '').trim();
  if (!state) return jsonResponse(400, { error: 'Start in Discord with /thingy verify first.' }, event);
  const stateItem = await getDynamoItem(discordStateKey(state));
  const expiresAt = Number(stateItem?.expires_at?.N || 0);
  const now = nowSeconds();
  if (!stateItem || expiresAt < now) {
    return jsonResponse(400, { status: 'discord_link_expired', error: 'That Discord verification link expired. Run /thingy verify again.' }, event);
  }
  const code = createLinkCode();
  const codeExpiresAt = now + DISCORD_LINK_TTL_SECONDS;
  const stateHash = linkHash(state);
  const identity = normalizeDiscordIdentity({
    username: stateItem.username?.S,
    global_name: stateItem.global_name?.S,
    display_name: stateItem.display_name?.S,
    guild_id: stateItem.guild_id?.S
  });
  await dynamodb.send(new PutItemCommand({
    TableName: process.env.TABLE_NAME,
    Item: {
      ...discordCodeKey(code),
      state_hash: dynamoString(stateHash),
      subscriber_hash: dynamoString(payload.sub),
      email: dynamoString(email),
      email_hash: dynamoString(emailHash(email)),
      discord_user_hash: dynamoString(stateItem.discord_user_hash?.S || ''),
      username: dynamoString(identity.username),
      global_name: dynamoString(identity.global_name),
      display_name: dynamoString(identity.display_name),
      guild_id: dynamoString(identity.guild_id),
      entitlements_json: dynamoString(JSON.stringify(entitlements)),
      created_at: dynamoNumber(now),
      expires_at: dynamoNumber(codeExpiresAt),
      ttl: dynamoNumber(codeExpiresAt)
    }
  }));
  await dynamodb.send(new UpdateItemCommand({
    TableName: process.env.TABLE_NAME,
    Key: discordStateKey(state),
    UpdateExpression: 'SET #subscriber_hash = :subscriber_hash, #email_hash = :email_hash, #code_hash = :code_hash',
    ExpressionAttributeNames: {
      '#subscriber_hash': 'subscriber_hash',
      '#email_hash': 'email_hash',
      '#code_hash': 'code_hash'
    },
    ExpressionAttributeValues: {
      ':subscriber_hash': dynamoString(payload.sub),
      ':email_hash': dynamoString(emailHash(email)),
      ':code_hash': dynamoString(linkHash(code))
    }
  }));
  logEvent('info', 'discord_link_code_created', {
    subscriber_hash: payload.sub,
    discord_user_hash: String(stateItem.discord_user_hash?.S || '').slice(0, 12),
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'discord_link_code_created',
    code,
    expires_at: codeExpiresAt,
    discord_user: identity,
    entitlements
  }, event);
}

async function handleDiscordLinkConfirm(event, body, start) {
  const secretState = bridgeSecretOk(body);
  if (secretState === null) return jsonResponse(503, { error: 'Discord linking is not enabled.' }, event);
  if (!secretState) return jsonResponse(401, { error: 'Bridge secret rejected.' }, event);
  const code = String(body.code || '').trim().toUpperCase().replace(/\s+/g, '');
  if (!code) return jsonResponse(400, { error: 'code is required.' }, event);
  const suppliedUserHash = discordUserHash(body.discord_user_id);
  if (!suppliedUserHash) return jsonResponse(400, { error: 'discord_user_id is required.' }, event);
  const codeKey = discordCodeKey(code);
  const codeItem = await getDynamoItem(codeKey);
  const expiresAt = Number(codeItem?.expires_at?.N || 0);
  const now = nowSeconds();
  const codeUserHash = codeItem?.discord_user_hash?.S || '';
  if (!codeItem || expiresAt < now || codeItem.used_at || codeUserHash !== suppliedUserHash) {
    logEvent('info', 'discord_link_confirm_rejected', {
      reason: !codeItem ? 'not_found' : expiresAt < now ? 'expired' : codeItem.used_at ? 'used' : 'wrong_user',
      discord_user_hash: suppliedUserHash.slice(0, 12)
    });
    return jsonResponse(400, { status: 'discord_link_invalid', error: 'That Discord verification code is invalid or expired.' }, event);
  }
  const email = normalizeEmail(codeItem.email?.S || '');
  const subscriberHash = codeItem.subscriber_hash?.S || '';
  let entitlement;
  try {
    entitlement = await currentEntitlementsForEmail(email);
  } catch (error) {
    logEvent('warning', 'discord_link_confirm_entitlement_lookup_failed', {
      subscriber_hash: subscriberHash,
      error_type: error.constructor?.name || 'Error'
    });
    return jsonResponse(502, { error: 'Could not verify supporting membership right now.' }, event);
  }
  const entitlements = entitlementsWithOwner(subscriberHash, entitlement.entitlements);
  if (!isSupportingEntitlement(entitlements) || emailHash(email) !== subscriberHash) {
    logEvent('info', 'discord_link_confirm_not_supporting', { subscriber_hash: subscriberHash, status: entitlement.status });
    return jsonResponse(403, {
      status: 'supporting_member_required',
      error: 'Discord is available to Weekly Thing Supporting Members.'
    }, event);
  }
  const identity = normalizeDiscordIdentity({
    username: body.username || codeItem.username?.S,
    global_name: body.global_name || codeItem.global_name?.S,
    display_name: body.display_name || codeItem.display_name?.S,
    guild_id: body.guild_id || codeItem.guild_id?.S
  });
  const connectedAt = new Date().toISOString();
  const discordConnection = {
    ...identity,
    connected: true,
    guild_id: identity.guild_id,
    connected_at: connectedAt,
    last_verified_at: connectedAt
  };
  const tableName = process.env.TABLE_NAME;
  const connectionRecord = {
    ...discordConnection,
    discord_user_hash: suppliedUserHash,
    subscriber_hash: subscriberHash,
    email,
    entitlements
  };
  const memoryUpdate = discordConnectionMemoryUpdate(tableName, subscriberHash, discordConnection, connectedAt);
  if (!tableName || !memoryUpdate) {
    logEvent('warning', 'discord_link_confirm_memory_unavailable', { subscriber_hash: subscriberHash });
    return jsonResponse(500, { error: 'Thingy could not save that Discord link right now. Please try again.' }, event);
  }
  try {
    await dynamodb.send(new TransactWriteItemsCommand({
      TransactItems: [
        {
          Update: {
            TableName: tableName,
            Key: codeKey,
            UpdateExpression: 'SET #used_at = :used_at',
            ConditionExpression: 'attribute_exists(pk) AND attribute_not_exists(#used_at) AND #expires_at >= :now',
            ExpressionAttributeNames: {
              '#used_at': 'used_at',
              '#expires_at': 'expires_at'
            },
            ExpressionAttributeValues: {
              ':used_at': dynamoNumber(now),
              ':now': dynamoNumber(now)
            }
          }
        },
        { Put: discordConnectionPut(tableName, connectionRecord) },
        { Update: memoryUpdate }
      ]
    }));
  } catch (error) {
    const errorType = error.constructor?.name || 'Error';
    logEvent('warning', 'discord_link_confirm_persist_failed', {
      subscriber_hash: subscriberHash,
      error_type: errorType
    });
    if (errorType === 'TransactionCanceledException') {
      return jsonResponse(400, { status: 'discord_link_invalid', error: 'That Discord verification code is invalid or expired.' }, event);
    }
    return jsonResponse(500, { error: 'Thingy could not save that Discord link right now. Please try again.' }, event);
  }
  const memory = await getUserMemory(subscriberHash, { consistent: true });
  if (!memory?.discord_connection) {
    logEvent('warning', 'discord_link_confirm_profile_missing', { subscriber_hash: subscriberHash });
    return jsonResponse(500, { error: 'Thingy could not save that Discord link right now. Please try again.' }, event);
  }
  logEvent('info', 'discord_link_confirmed', {
    subscriber_hash: subscriberHash,
    discord_user_hash: suppliedUserHash.slice(0, 12),
    duration_ms: Math.round(performance.now() - start)
  });
  return jsonResponse(200, {
    status: 'discord_linked',
    ok: true,
    supporting_member: true,
    entitlements,
    profile: {
      ...authProfile(memory),
      entitlements,
      modes: availableConversationModes(entitlements)
    },
    discord_connection: discordConnection
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
    'discord_link_start',
    'discord_link_code',
    'discord_link_confirm'
  ].includes(action)) {
    logEvent('info', 'auth_rejected_invalid_action', { email_hash: hashedEmail, action });
    return jsonResponse(400, { error: 'Unsupported subscriber action.' }, event);
  }

  if (action === 'discord_link_start') {
    return await handleDiscordLinkStart(event, body, start);
  }

  if (action === 'discord_link_code') {
    return await handleDiscordLinkCode(event, body, start);
  }

  if (action === 'discord_link_confirm') {
    return await handleDiscordLinkConfirm(event, body, start);
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
    } else if (method === 'POST' && path.endsWith('/memory')) {
      response = await handleMemory(event, parseBody(event), start);
    } else if (method === 'POST' && path.endsWith('/conversations')) {
      response = await handleUserConversations(event, parseBody(event), { start, entitlementsForSessionPayload });
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
