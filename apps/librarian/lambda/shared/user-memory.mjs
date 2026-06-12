// Per-user profile backed by the existing Librarian DynamoDB table.
//
// Each user (web subscriber or Discord member) gets one row keyed by
// the session token's `sub`. The row tracks basic account metadata only:
//
//   - first_seen_at / last_seen_at / turn_count
//   - preferred_name                 — what Thingy should call the reader
//   - discord_connection             — linked Discord identity, if any
//
// Conversations themselves are stored server-side per conversation
// (user-conversations.mjs); this row deliberately carries no AI-derived
// memory. The earlier synthesized "learned profile" feature was removed —
// Thingy answers from the archive, not from modeling the reader.

// AWS clients and command classes are imported lazily inside the
// functions that touch DynamoDB. Keeps the pure helpers (`authProfile`,
// the read/write item shapers) loadable in test environments that don't
// have the AWS SDK installed.

import { logEvent } from './logging.mjs';

const TTL_DAYS_DEFAULT = 365;

function dynamoString(value) {
  return { S: String(value ?? '') };
}

function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

function memoryKey(sub) {
  return { pk: dynamoString(`user#${sub}`), sk: dynamoString('memory') };
}

function readDiscordConnection(value) {
  const item = value?.M || null;
  if (!item) return null;
  const connectedAt = item.connected_at?.S || '';
  const username = item.username?.S || '';
  const globalName = item.global_name?.S || '';
  if (!connectedAt && !username && !globalName) return null;
  return {
    connected: item.connected?.BOOL !== false,
    username,
    global_name: globalName,
    display_name: item.display_name?.S || globalName || username,
    guild_id: item.guild_id?.S || '',
    connected_at: connectedAt,
    last_verified_at: item.last_verified_at?.S || connectedAt
  };
}

function writeDiscordConnection(connection = {}) {
  return {
    M: {
      connected: { BOOL: connection.connected !== false },
      username: dynamoString(connection.username || ''),
      global_name: dynamoString(connection.global_name || ''),
      display_name: dynamoString(connection.display_name || connection.global_name || connection.username || ''),
      guild_id: dynamoString(connection.guild_id || ''),
      connected_at: dynamoString(connection.connected_at || ''),
      last_verified_at: dynamoString(connection.last_verified_at || connection.connected_at || '')
    }
  };
}

function ttlFromNow() {
  const days = Number(process.env.LIBRARIAN_USER_MEMORY_TTL_DAYS || TTL_DAYS_DEFAULT);
  return Math.floor(Date.now() / 1000) + days * 86400;
}

export function memoryDynamoItem(sub, memory = {}, nowIso = new Date().toISOString(), overrides = {}) {
  const version = Number(overrides.version ?? memory.version ?? 0);
  const discordConnection = overrides.discord_connection ?? memory.discord_connection;
  const item = {
    pk: dynamoString(`user#${sub}`),
    sk: dynamoString('memory'),
    version: dynamoNumber(version),
    first_seen_at: dynamoString(memory.first_seen_at || nowIso),
    last_seen_at: dynamoString(overrides.last_seen_at || memory.last_seen_at || nowIso),
    preferred_name: dynamoString(overrides.preferred_name ?? memory.preferred_name ?? ''),
    turn_count: dynamoNumber(overrides.turn_count ?? memory.turn_count ?? 0),
    ttl: dynamoNumber(ttlFromNow())
  };
  if (discordConnection) item.discord_connection = writeDiscordConnection(discordConnection);
  return item;
}

// ---------- public API ----------

export async function getUserMemory(sub, options = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return null;
  try {
    const { GetItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    const response = await dynamodb.send(new GetItemCommand({
      TableName: tableName,
      Key: memoryKey(sub),
      ConsistentRead: Boolean(options.consistent)
    }));
    return memoryFromItem(response?.Item, sub);
  } catch (error) {
    logEvent('warning', 'user_memory_read_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return null;
  }
}

export function memoryFromItem(item, sub = '') {
  if (!item) return null;
  return {
    sub,
    version: Number(item.version?.N || 0),
    first_seen_at: item.first_seen_at?.S || '',
    last_seen_at: item.last_seen_at?.S || '',
    preferred_name: item.preferred_name?.S || '',
    turn_count: Number(item.turn_count?.N || 0),
    discord_connection: readDiscordConnection(item.discord_connection)
  };
}

// Record one chat turn. Best-effort — failures don't propagate.
export async function recordUserTurn(sub, { preferredName } = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return;
  const start = Date.now();
  try {
    const existing = await getUserMemory(sub);
    const nowIso = new Date().toISOString();
    const cleanPreferredName = String(preferredName || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const priorVersion = Number(existing?.version || 0);
    const nextVersion = priorVersion + 1;
    const item = memoryDynamoItem(sub, existing || {}, nowIso, {
      version: nextVersion,
      last_seen_at: nowIso,
      preferred_name: cleanPreferredName || existing?.preferred_name || '',
      turn_count: (existing?.turn_count || 0) + 1
    });
    const { PutItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    // Optimistic lock: only write if `version` is exactly what we read
    // (or absent for a brand-new row). On contention, log and skip —
    // one lost turn count is better than clobbering a concurrent write.
    try {
      await dynamodb.send(new PutItemCommand({
        TableName: tableName,
        Item: item,
        ConditionExpression: priorVersion === 0
          ? 'attribute_not_exists(version)'
          : 'version = :prior_version',
        ExpressionAttributeValues: priorVersion === 0
          ? undefined
          : { ':prior_version': dynamoNumber(priorVersion) }
      }));
    } catch (error) {
      if (error?.name === 'ConditionalCheckFailedException') {
        logEvent('info', 'user_memory_write_contended', {
          prior_version: priorVersion
        });
        return;
      }
      throw error;
    }
    logEvent('info', 'user_memory_recorded', {
      turn_count: (existing?.turn_count || 0) + 1,
      version: nextVersion,
      duration_ms: Date.now() - start
    });
  } catch (error) {
    logEvent('warning', 'user_memory_write_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
  }
}

export async function recordUserPreferredName(sub, name) {
  const tableName = process.env.TABLE_NAME;
  const cleanName = String(name || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  if (!tableName || !sub || !cleanName) return { ok: false, error: 'Missing memory write context.' };
  const nowIso = new Date().toISOString();
  try {
    const { UpdateItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    const response = await dynamodb.send(new UpdateItemCommand({
      TableName: tableName,
      Key: memoryKey(sub),
      UpdateExpression: [
        'SET #preferred_name = :preferred_name',
        '#first_seen_at = if_not_exists(#first_seen_at, :now)',
        '#last_seen_at = :now',
        '#ttl = :ttl',
        '#version = if_not_exists(#version, :zero) + :one'
      ].join(', '),
      ExpressionAttributeNames: {
        '#preferred_name': 'preferred_name',
        '#first_seen_at': 'first_seen_at',
        '#last_seen_at': 'last_seen_at',
        '#ttl': 'ttl',
        '#version': 'version'
      },
      ExpressionAttributeValues: {
        ':preferred_name': dynamoString(cleanName),
        ':now': dynamoString(nowIso),
        ':ttl': dynamoNumber(ttlFromNow()),
        ':zero': dynamoNumber(0),
        ':one': dynamoNumber(1)
      },
      ReturnValues: 'ALL_NEW'
    }));
    logEvent('info', 'user_preferred_name_recorded');
    return { ok: true, memory: memoryFromItem(response?.Attributes, sub) };
  } catch (error) {
    logEvent('warning', 'user_preferred_name_write_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return { ok: false, error: 'Memory write failed.' };
  }
}

function normalizedDiscordConnection(connection = {}, nowIso = new Date().toISOString()) {
  return {
    connected: true,
    username: String(connection.username || '').trim().slice(0, 80),
    global_name: String(connection.global_name || '').trim().slice(0, 80),
    display_name: String(connection.display_name || connection.global_name || connection.username || '').trim().slice(0, 80),
    guild_id: String(connection.guild_id || '').trim().slice(0, 80),
    connected_at: String(connection.connected_at || nowIso),
    last_verified_at: String(connection.last_verified_at || nowIso)
  };
}

export function discordConnectionMemoryUpdate(tableName, sub, connection = {}, nowIso = new Date().toISOString()) {
  if (!tableName || !sub) return null;
  const value = normalizedDiscordConnection(connection, nowIso);
  return {
    TableName: tableName,
    Key: memoryKey(sub),
    UpdateExpression: [
      'SET #discord_connection = :discord_connection',
      '#first_seen_at = if_not_exists(#first_seen_at, :now)',
      '#last_seen_at = :now',
      '#ttl = :ttl',
      '#version = if_not_exists(#version, :zero) + :one'
    ].join(', '),
    ExpressionAttributeNames: {
      '#discord_connection': 'discord_connection',
      '#first_seen_at': 'first_seen_at',
      '#last_seen_at': 'last_seen_at',
      '#ttl': 'ttl',
      '#version': 'version'
    },
    ExpressionAttributeValues: {
      ':discord_connection': writeDiscordConnection(value),
      ':now': dynamoString(nowIso),
      ':ttl': dynamoNumber(ttlFromNow()),
      ':zero': dynamoNumber(0),
      ':one': dynamoNumber(1)
    }
  };
}

export async function recordDiscordConnection(sub, connection = {}) {
  const tableName = process.env.TABLE_NAME;
  const nowIso = new Date().toISOString();
  const params = discordConnectionMemoryUpdate(tableName, sub, connection, nowIso);
  if (!params) return { ok: false, error: 'Missing memory write context.' };
  try {
    const { UpdateItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    const response = await dynamodb.send(new UpdateItemCommand({
      ...params,
      ReturnValues: 'ALL_NEW'
    }));
    logEvent('info', 'user_discord_connection_recorded');
    return { ok: true, memory: memoryFromItem(response?.Attributes, sub), discord_connection: normalizedDiscordConnection(connection, nowIso) };
  } catch (error) {
    logEvent('warning', 'user_discord_connection_write_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return { ok: false, error: 'Memory write failed.' };
  }
}

// Shape the profile for an auth response. Returning users get the
// `returning` flag so the frontend (web or Discord) can welcome them back.
// The empty arrays are a frozen contract shape: web clients deployed
// before the synthesized-memory removal still read these keys.
export function authProfile(memory) {
  if (!memory) {
    return { returning: false };
  }
  const turnCount = Number(memory.turn_count || 0);
  return {
    returning: turnCount > 0,
    first_seen_at: memory.first_seen_at,
    last_seen_at: memory.last_seen_at,
    preferred_name: memory.preferred_name || '',
    turn_count: turnCount,
    current_session_questions: [],
    recent_prompts: [],
    prior_session_summaries: [],
    learned_profile: [],
    memory_synthesis: {},
    discord_connection: memory.discord_connection || null
  };
}
