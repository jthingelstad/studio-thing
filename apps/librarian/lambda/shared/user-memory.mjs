// Per-user memory backed by the existing Librarian DynamoDB table.
//
// Each user (web subscriber or Discord member) gets one row keyed by
// the session token's `sub`. The row tracks:
//
//   - first_seen_at / last_seen_at / turn_count
//   - current_session_id            — sid of the in-flight session
//   - current_session_questions     — rolling questions for that session
//   - synthesized_history           — Bedrock-summarized past sessions
//   - learned_profile               — observed archive-use profile for this reader
//
// On each chat turn the runtime calls ``recordUserTurn(sub, {sid,
// question})``. When ``sid`` differs from ``current_session_id``, the
// previous session's questions are summarized via Bedrock and pushed to
// ``synthesized_history`` (one short paragraph per past session). Then
// the new session is opened with the incoming question.
//
// This lets Thingy carry forward what a user has been talking about
// across token-expiry boundaries without storing every raw question
// forever — old context fades into useful summaries.

// AWS clients and command classes are imported lazily inside the
// functions that touch DynamoDB or Bedrock. Keeps the pure helpers
// (`authProfile`, `memoryContextBlock`, the read/write item shapers)
// loadable in test environments that don't have the AWS SDK installed.

import crypto from 'node:crypto';
import { logEvent } from './logging.mjs';

const CURRENT_SESSION_QUESTIONS_MAX = 12;
const SYNTHESIZED_HISTORY_MAX = 8;
const LEARNED_PROFILE_MAX = 12;
const QUESTION_TRIM_CHARS = 400;
const MEMORY_TOMBSTONES_MAX = 48;
const MEMORY_EVENT_LIMIT = 120;
const TTL_DAYS_DEFAULT = 365;
const SYNTHESIS_MAX_TOKENS = 160;
const MEMORY_SYNTHESIS_MAX_TOKENS = 900;
const MEMORY_SYNTHESIS_VERSION = 'thingy-memory-v1';
const MEMORY_REFRESH_PRESERVED_ERROR = 'Profile refresh could not produce usable updates. Existing profile was kept.';
const MEMORY_EMPTY_SYNTHESIS_ERROR = 'Profile refresh found evidence but produced no learned profile items.';
const SYNTHESIZABLE_MEMORY_EVENT_TYPES = new Set(['chat_question', 'conversation_summary']);
const AUTO_SYNTHESIS_MIN_PENDING_DEFAULT = 8;
const AUTO_SYNTHESIS_FIRST_MIN_PENDING_DEFAULT = 3;
const AUTO_SYNTHESIS_MAX_PENDING_AGE_HOURS_DEFAULT = 24;
const LOW_SIGNAL_SUMMARY_PATTERNS = [
  /i don['’]t have (?:any )?(?:previous|prior) context/i,
  /i don['’]t see any previous conversation/i,
  /i do not have (?:any )?(?:previous|prior) context/i,
  /no (?:previous|prior) context/i,
  /could you (?:please )?(?:provide|share|give) (?:me )?more details/i,
  /what topic you['’]d like me to elaborate/i,
  /the chat session or questions you['’]d like me to summarize/i,
  /i['’]d be happy to help,? but/i,
  /please provide (?:the )?(?:chat|conversation|session)/i
];

function dynamoString(value) {
  return { S: String(value ?? '') };
}

function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

function memoryKey(sub) {
  return { pk: dynamoString(`user#${sub}`), sk: dynamoString('memory') };
}

function memoryEventKey(sub, eventId, ts = new Date().toISOString()) {
  return {
    pk: dynamoString(`user#${sub}`),
    sk: dynamoString(`memory-event#${ts}#${eventId}`)
  };
}

function memoryItemId(type, ...parts) {
  const hash = crypto.createHash('sha256')
    .update([type, ...parts].map((part) => String(part || '').trim()).join('\0'))
    .digest('hex')
    .slice(0, 18);
  return `mem_${String(type || 'item').replace(/[^a-z0-9_]+/gi, '_')}_${hash}`;
}

function readQuestion(item) {
  if (!item || !item.M) return null;
  const ts = item.M.ts?.S || '';
  const question = item.M.question?.S || '';
  if (!ts || !question) return null;
  return { id: item.M.id?.S || memoryItemId('recent', ts, question), ts, question };
}

function writeQuestionItem({ id, ts, question }) {
  const cleanQuestion = String(question || '').slice(0, QUESTION_TRIM_CHARS);
  return {
    M: {
      id: dynamoString(id || memoryItemId('recent', ts, cleanQuestion)),
      ts: dynamoString(ts),
      question: dynamoString(cleanQuestion)
    }
  };
}

function readSynth(item) {
  if (!item || !item.M) return null;
  const started_at = item.M.started_at?.S || '';
  const ended_at = item.M.ended_at?.S || '';
  const summary = sanitizeSessionSummary(item.M.summary?.S || '');
  const turn_count = Number(item.M.turn_count?.N || 0);
  if (!summary) return null;
  return { id: item.M.id?.S || memoryItemId('thread', started_at, ended_at, summary), started_at, ended_at, summary, turn_count };
}

function writeSynthItem({ id, started_at, ended_at, summary, turn_count }) {
  const cleanSummary = sanitizeSessionSummary(summary);
  return {
    M: {
      id: dynamoString(id || memoryItemId('thread', started_at, ended_at, cleanSummary)),
      started_at: dynamoString(started_at),
      ended_at: dynamoString(ended_at),
      summary: dynamoString(cleanSummary.slice(0, 1200)),
      turn_count: dynamoNumber(turn_count)
    }
  };
}

function readEvidenceList(value) {
  return (value?.L || []).map((item) => {
    const row = item.M || {};
    const event_id = row.event_id?.S || '';
    const label = row.label?.S || '';
    return event_id || label ? { event_id, label } : null;
  }).filter(Boolean);
}

function writeEvidenceList(values = []) {
  return {
    L: (values || []).slice(0, 8).map((item) => ({
      M: {
        event_id: dynamoString(item.event_id || ''),
        label: dynamoString(String(item.label || '').slice(0, 160))
      }
    }))
  };
}

function learnedMemoryType(value) {
  return String(value || 'observed_archive_theme').trim().slice(0, 80) || 'observed_archive_theme';
}

function learnedEvidenceFingerprint(evidence = []) {
  const eventIds = (Array.isArray(evidence) ? evidence : [])
    .map((item) => String(item?.event_id || item?.id || '').trim())
    .filter(Boolean)
    .sort();
  return eventIds.length ? eventIds.join('|') : '';
}

function learnedMemoryStableId(memory = {}) {
  const type = learnedMemoryType(memory.type);
  const label = String(memory.label || '').trim().replace(/\s+/g, ' ').slice(0, 160);
  const summary = String(memory.summary || '').trim().replace(/\s+/g, ' ').slice(0, 600);
  const evidenceKey = learnedEvidenceFingerprint(memory.evidence || []);
  return memoryItemId('learned', type, evidenceKey || label || summary.slice(0, 80));
}

function readSynthesizedMemory(item) {
  if (!item || !item.M) return null;
  const label = item.M.label?.S || '';
  const summary = item.M.summary?.S || '';
  if (!label && !summary) return null;
  const created_at = item.M.created_at?.S || '';
  const synthesized_at = item.M.synthesized_at?.S || created_at;
  const type = learnedMemoryType(item.M.type?.S);
  const evidence = readEvidenceList(item.M.evidence);
  return {
    id: learnedMemoryStableId({ type, label, summary, evidence }),
    type,
    label,
    summary,
    confidence: Number(item.M.confidence?.N || 0),
    evidence,
    created_at,
    updated_at: item.M.updated_at?.S || created_at,
    synthesized_at,
    synthesis_version: item.M.synthesis_version?.S || ''
  };
}

function writeSynthesizedMemoryItem(memory = {}) {
  const label = String(memory.label || '').trim().replace(/\s+/g, ' ').slice(0, 160);
  const summary = String(memory.summary || '').trim().replace(/\s+/g, ' ').slice(0, 600);
  const synthesizedAt = memory.synthesized_at || memory.updated_at || memory.created_at || '';
  const type = learnedMemoryType(memory.type);
  return {
    M: {
      id: dynamoString(learnedMemoryStableId({ type, label, summary, evidence: memory.evidence || [] })),
      type: dynamoString(type),
      label: dynamoString(label),
      summary: dynamoString(summary),
      confidence: dynamoNumber(Math.max(0, Math.min(1, Number(memory.confidence || 0)))),
      evidence: writeEvidenceList(memory.evidence || []),
      created_at: dynamoString(memory.created_at || synthesizedAt),
      updated_at: dynamoString(memory.updated_at || synthesizedAt),
      synthesized_at: dynamoString(synthesizedAt),
      synthesis_version: dynamoString(memory.synthesis_version || MEMORY_SYNTHESIS_VERSION)
    }
  };
}

function readTombstone(item) {
  const row = item?.M || {};
  const memory_id = row.memory_id?.S || row.id?.S || '';
  if (!memory_id) return null;
  return {
    memory_id,
    type: row.type?.S || '',
    deleted_at: row.deleted_at?.S || '',
    reason: row.reason?.S || ''
  };
}

function writeTombstoneItem(item = {}) {
  return {
    M: {
      memory_id: dynamoString(item.memory_id || item.id || ''),
      type: dynamoString(item.type || ''),
      deleted_at: dynamoString(item.deleted_at || ''),
      reason: dynamoString(item.reason || '')
    }
  };
}

function readSynthesisStatus(value) {
  const row = value?.M || {};
  return {
    last_synthesized_at: row.last_synthesized_at?.S || '',
    last_event_at: row.last_event_at?.S || '',
    pending_event_count: Number(row.pending_event_count?.N || 0),
    status: row.status?.S || '',
    error: row.error?.S || ''
  };
}

function writeSynthesisStatus(status = {}) {
  return {
    M: {
      last_synthesized_at: dynamoString(status.last_synthesized_at || ''),
      last_event_at: dynamoString(status.last_event_at || ''),
      pending_event_count: dynamoNumber(status.pending_event_count || 0),
      status: dynamoString(status.status || ''),
      error: dynamoString(String(status.error || '').slice(0, 160))
    }
  };
}

export function sanitizeSessionSummary(value) {
  const text = String(value || '').trim().replace(/\s+/g, ' ');
  if (!text) return '';
  if (text.toUpperCase() === 'NO_USEFUL_SUMMARY') return '';
  if (LOW_SIGNAL_SUMMARY_PATTERNS.some((pattern) => pattern.test(text))) return '';
  return text.slice(0, 1200);
}

function usefulSynthesizedHistory(history = []) {
  return (history || []).filter((item) => sanitizeSessionSummary(item?.summary));
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
  const learnedProfile = overrides.learned_profile ?? memory.learned_profile ?? [];
  const item = {
    pk: dynamoString(`user#${sub}`),
    sk: dynamoString('memory'),
    version: dynamoNumber(version),
    first_seen_at: dynamoString(memory.first_seen_at || nowIso),
    last_seen_at: dynamoString(overrides.last_seen_at || memory.last_seen_at || nowIso),
    preferred_name: dynamoString(overrides.preferred_name ?? memory.preferred_name ?? ''),
    turn_count: dynamoNumber(overrides.turn_count ?? memory.turn_count ?? 0),
    current_session_id: dynamoString(overrides.current_session_id ?? memory.current_session_id ?? ''),
    current_session_started_at: dynamoString(overrides.current_session_started_at ?? memory.current_session_started_at ?? ''),
    current_session_questions: { L: (overrides.current_session_questions || memory.current_session_questions || []).map(writeQuestionItem) },
    synthesized_history: { L: (overrides.synthesized_history || memory.synthesized_history || []).map(writeSynthItem) },
    learned_profile: { L: learnedProfile.map(writeSynthesizedMemoryItem) },
    memory_tombstones: { L: (overrides.memory_tombstones || memory.memory_tombstones || []).map(writeTombstoneItem) },
    memory_synthesis: writeSynthesisStatus(overrides.memory_synthesis || memory.memory_synthesis || {}),
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

function memoryEventFromItem(item = {}) {
  const sk = item.sk?.S || '';
  const parts = sk.split('#');
  const eventId = item.event_id?.S || parts.slice(-1)[0] || '';
  return {
    id: eventId,
    event_id: eventId,
    type: item.event_type?.S || item.type?.S || '',
    ts: item.ts?.S || parts[1] || '',
    label: item.label?.S || '',
    detail: item.detail?.S || '',
    metadata: (() => {
      try {
        return JSON.parse(item.metadata_json?.S || '{}') || {};
      } catch {
        return {};
      }
    })()
  };
}

export async function recordMemoryEvent(sub, event = {}) {
  const tableName = process.env.TABLE_NAME;
  const type = String(event.type || '').trim().slice(0, 80);
  const label = String(event.label || event.detail || '').trim().replace(/\s+/g, ' ').slice(0, 180);
  if (!tableName || !sub || !type || !label) return { ok: false };
  const ts = String(event.ts || new Date().toISOString());
  const eventId = event.id || crypto.randomUUID();
  try {
    const { PutItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    await dynamodb.send(new PutItemCommand({
      TableName: tableName,
      Item: {
        ...memoryEventKey(sub, eventId, ts),
        item_type: dynamoString('memory_event'),
        event_id: dynamoString(eventId),
        event_type: dynamoString(type),
        ts: dynamoString(ts),
        label: dynamoString(label),
        detail: dynamoString(String(event.detail || label).trim().replace(/\s+/g, ' ').slice(0, 600)),
        metadata_json: dynamoString(JSON.stringify(event.metadata || {}).slice(0, 1200)),
        ttl: dynamoNumber(ttlFromNow())
      }
    }));
    return { ok: true, event_id: eventId, ts };
  } catch (error) {
    logEvent('warning', 'user_memory_event_write_failed', {
      event_type: type,
      error_type: error?.constructor?.name || 'Error'
    });
    return { ok: false };
  }
}

export async function listUserMemoryEvents(sub, options = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return [];
  const since = String(options.since || '').trim();
  const limit = Math.max(1, Math.min(MEMORY_EVENT_LIMIT, Number(options.limit || MEMORY_EVENT_LIMIT)));
  try {
    const { QueryCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    const response = await dynamodb.send(new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': dynamoString(`user#${sub}`),
        ':prefix': dynamoString('memory-event#')
      },
      ScanIndexForward: false,
      Limit: limit
    }));
    return (response.Items || [])
      .map(memoryEventFromItem)
      .filter((event) => event.ts && (!since || event.ts > since))
      .sort((a, b) => a.ts.localeCompare(b.ts));
  } catch (error) {
    logEvent('warning', 'user_memory_event_read_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return [];
  }
}

export function memoryFromItem(item, sub = '') {
  if (!item) return null;
  const learnedProfile = (item.learned_profile?.L || [])
    .map(readSynthesizedMemory)
    .filter(Boolean);
  return {
    sub,
    version: Number(item.version?.N || 0),
    first_seen_at: item.first_seen_at?.S || '',
    last_seen_at: item.last_seen_at?.S || '',
    preferred_name: item.preferred_name?.S || '',
    turn_count: Number(item.turn_count?.N || 0),
    current_session_id: item.current_session_id?.S || '',
    current_session_started_at: item.current_session_started_at?.S || '',
    current_session_questions: (item.current_session_questions?.L || [])
      .map(readQuestion)
      .filter(Boolean),
    synthesized_history: (item.synthesized_history?.L || [])
      .map(readSynth)
      .filter(Boolean),
    learned_profile: learnedProfile,
    memory_tombstones: (item.memory_tombstones?.L || [])
      .map(readTombstone)
      .filter(Boolean),
    memory_synthesis: readSynthesisStatus(item.memory_synthesis),
    discord_connection: readDiscordConnection(item.discord_connection)
  };
}

// Record one chat turn. Best-effort — failures don't propagate.
//
// When the incoming sid differs from current_session_id, the previous
// session's questions get synthesized into a one-paragraph summary and
// rolled into synthesized_history before the new session is opened.
export async function recordUserTurn(sub, { sid, question, preferredName }) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return;
  const start = Date.now();
  try {
    const existing = await getUserMemory(sub);
    const nowIso = new Date().toISOString();
    const incomingSid = String(sid || '');
    const trimmedQuestion = String(question || '').trim().slice(0, QUESTION_TRIM_CHARS);
    const cleanPreferredName = String(preferredName || '').trim().replace(/\s+/g, ' ').slice(0, 80);

    let synthesizedHistory = existing?.synthesized_history || [];
    let currentSessionId = existing?.current_session_id || '';
    let currentSessionStartedAt = existing?.current_session_started_at || '';
    let currentSessionQuestions = existing?.current_session_questions || [];

    const sessionRotated = incomingSid && currentSessionId && currentSessionId !== incomingSid;
    if (sessionRotated && currentSessionQuestions.length > 0) {
      const summary = await synthesizeSessionQuestions(currentSessionQuestions).catch(() => '');
      if (summary) {
        synthesizedHistory = [
          ...synthesizedHistory,
          {
            started_at: currentSessionStartedAt || currentSessionQuestions[0]?.ts || '',
            ended_at: currentSessionQuestions[currentSessionQuestions.length - 1]?.ts || nowIso,
            summary,
            turn_count: currentSessionQuestions.length
          }
        ].slice(-SYNTHESIZED_HISTORY_MAX);
      }
    }

    if (sessionRotated || !currentSessionId) {
      currentSessionId = incomingSid;
      currentSessionStartedAt = nowIso;
      currentSessionQuestions = [];
    }

    if (trimmedQuestion) {
      currentSessionQuestions = [
        ...currentSessionQuestions,
        { ts: nowIso, question: trimmedQuestion }
      ].slice(-CURRENT_SESSION_QUESTIONS_MAX);
    }

    const priorVersion = Number(existing?.version || 0);
    const nextVersion = priorVersion + 1;
    const item = memoryDynamoItem(sub, existing || {}, nowIso, {
      version: nextVersion,
      last_seen_at: nowIso,
      preferred_name: cleanPreferredName || existing?.preferred_name || '',
      turn_count: (existing?.turn_count || 0) + 1,
      current_session_id: currentSessionId,
      current_session_started_at: currentSessionStartedAt,
      current_session_questions: currentSessionQuestions,
      synthesized_history: synthesizedHistory
    });
    const { PutItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    // Optimistic lock: only write if `version` is exactly what we read
    // (or absent for a brand-new row). On contention, log and skip —
    // one lost turn is better than clobbering a concurrent writer's
    // appended question.
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
      session_rotated: sessionRotated || false,
      synthesized_history_len: synthesizedHistory.length,
      version: nextVersion,
      duration_ms: Date.now() - start
    });
    if (trimmedQuestion) {
      recordMemoryEvent(sub, {
        type: 'chat_question',
        ts: nowIso,
        label: trimmedQuestion,
        detail: trimmedQuestion,
        metadata: { sid: incomingSid }
      }).catch(() => {});
    }
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
      Key: {
        pk: dynamoString(`user#${sub}`),
        sk: dynamoString('memory')
      },
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

// Bedrock-summarize a session's questions into one short paragraph.
// Surfaces the conversational arc, not a per-question recap. Returns
// '' on failure so the caller can decide whether to skip the synth.
export async function synthesizeSessionQuestions(questions) {
  const list = (questions || [])
    .map((q, idx) => `${idx + 1}. ${q.question}`)
    .join('\n')
    .slice(0, 4000);
  if (!list) return '';
  const system = (
    'You synthesize what one Thingy user was asking about ' +
    "during a single chat session. Output one short paragraph (under 60 words) " +
    "that captures the topic arc, written in third person from Thingy's point " +
    'of view. Skip pleasantries and meta questions; focus on the substantive ' +
    'topics. If there are no substantive topics to summarize, output exactly ' +
    'NO_USEFUL_SUMMARY. Do not invent details that the questions did not contain.'
  );
  try {
    const { ConverseCommand } = await import('@aws-sdk/client-bedrock-runtime');
    const { bedrock, fastModel } = await import('./aws-clients.mjs');
    const model = fastModel();
    const response = await bedrock.send(new ConverseCommand({
      modelId: model,
      system: [{ text: system }, { cachePoint: { type: 'default' } }],
      messages: [{ role: 'user', content: [{ text: list }] }],
      inferenceConfig: { maxTokens: SYNTHESIS_MAX_TOKENS, temperature: 0.3 }
    }));
    const parts = response?.output?.message?.content || [];
    const text = parts.map((p) => p.text || '').filter(Boolean).join(' ').trim();
    return sanitizeSessionSummary(text);
  } catch (error) {
    logEvent('warning', 'user_memory_synthesis_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return '';
  }
}

function parseJsonValue(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function balancedJsonSlice(text, start) {
  const stack = [];
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === '{') stack.push('}');
    else if (ch === '[') stack.push(']');
    else if (ch === '}' || ch === ']') {
      if (stack.at(-1) !== ch) return '';
      stack.pop();
      if (stack.length === 0) return text.slice(start, i + 1);
    }
  }
  return '';
}

function extractJsonPayload(text) {
  const raw = String(text || '').trim();
  if (!raw) return '';
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidates = [
    raw.replace(/^```(?:json)?/i, '').replace(/```$/i, '').trim(),
    fenced?.[1]?.trim()
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (parseJsonValue(candidate)) return candidate;
  }
  for (let i = 0; i < raw.length; i += 1) {
    if (raw[i] !== '{' && raw[i] !== '[') continue;
    const candidate = balancedJsonSlice(raw, i);
    if (candidate && parseJsonValue(candidate)) return candidate;
  }
  return '';
}

export function parseSynthesizedMemoryJson(text, nowIso = new Date().toISOString()) {
  const raw = extractJsonPayload(String(text || ''));
  if (!raw) return null;
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  const rows = Array.isArray(parsed) ? parsed : Array.isArray(parsed.memories) ? parsed.memories : [];
  return rows.map((item) => {
    const label = String(item.label || item.title || '').trim().replace(/\s+/g, ' ').slice(0, 160);
    const summary = String(item.summary || item.description || '').trim().replace(/\s+/g, ' ').slice(0, 600);
    if (!label && !summary) return null;
    const type = learnedMemoryType(item.type);
    const evidence = Array.isArray(item.evidence) ? item.evidence : [];
    const normalizedEvidence = evidence.map((entry) => ({
      event_id: String(entry.event_id || entry.id || '').slice(0, 80),
      label: String(entry.label || entry.summary || '').trim().replace(/\s+/g, ' ').slice(0, 160)
    })).filter((entry) => entry.event_id || entry.label).slice(0, 8);
    return {
      id: learnedMemoryStableId({ type, label, summary, evidence: normalizedEvidence }),
      type,
      label: label || summary.slice(0, 80),
      summary,
      confidence: Math.max(0, Math.min(1, Number(item.confidence || 0.5))),
      evidence: normalizedEvidence,
      created_at: nowIso,
      updated_at: nowIso,
      synthesized_at: nowIso,
      synthesis_version: MEMORY_SYNTHESIS_VERSION
    };
  }).filter(Boolean).slice(0, LEARNED_PROFILE_MAX);
}

function tombstonedMemoryIds(tombstones = [], types = []) {
  const allowed = new Set(types);
  return new Set((tombstones || [])
    .filter((item) => !allowed.size || allowed.has(item.type))
    .map((item) => item.memory_id)
    .filter(Boolean));
}

export function mergeLearnedProfile(existing = [], incoming = [], nowIso = new Date().toISOString(), tombstones = []) {
  const deleted = tombstonedMemoryIds(tombstones, ['learned', 'learned_profile']);
  const byId = new Map();
  for (const item of existing || []) {
    const id = learnedMemoryStableId(item);
    if (!id || deleted.has(id)) continue;
    byId.set(id, { ...item, id });
  }
  for (const item of incoming || []) {
    const id = learnedMemoryStableId(item);
    if (!id || deleted.has(id)) continue;
    const prior = byId.get(id) || {};
    byId.set(id, {
      ...prior,
      ...item,
      id,
      created_at: prior.created_at || item.created_at || nowIso,
      updated_at: nowIso,
      synthesized_at: nowIso,
      synthesis_version: MEMORY_SYNTHESIS_VERSION
    });
  }
  return Array.from(byId.values()).slice(-LEARNED_PROFILE_MAX);
}

export function memorySynthesisStatus(memory = {}, events = []) {
  const stored = memory?.memory_synthesis || {};
  const synthesizableEvents = events.filter((event) => SYNTHESIZABLE_MEMORY_EVENT_TYPES.has(event.type || event.event_type || ''));
  const lastSynthesizedAt = String(stored.last_synthesized_at || '').trim();
  const lastEventAt = synthesizableEvents.reduce((latest, event) => (
    event.ts && event.ts > latest ? event.ts : latest
  ), String(stored.last_event_at || '').trim());
  const pending = synthesizableEvents.filter((event) => event.ts && (!lastSynthesizedAt || event.ts > lastSynthesizedAt)).length;
  const status = pending > 0
    ? 'stale'
    : lastSynthesizedAt
      ? 'current'
      : 'current';
  return {
    last_synthesized_at: lastSynthesizedAt,
    last_event_at: lastEventAt,
    pending_event_count: pending,
    status,
    error: status === 'stale' ? '' : String(stored.error || '')
  };
}

export function shouldAutoSynthesizeMemory(memory = {}, events = [], nowIso = new Date().toISOString(), options = {}) {
  const stored = memory?.memory_synthesis || {};
  const lastSynthesizedAt = String(stored.last_synthesized_at || '').trim();
  const pendingEvents = (events || [])
    .filter((event) => SYNTHESIZABLE_MEMORY_EVENT_TYPES.has(event.type || event.event_type || ''))
    .filter((event) => event.ts && (!lastSynthesizedAt || event.ts > lastSynthesizedAt))
    .sort((a, b) => String(a.ts || '').localeCompare(String(b.ts || '')));
  const pending = pendingEvents.length;
  if (!pending) return false;
  const minPending = Number(options.minPending || process.env.THINGY_MEMORY_AUTO_SYNTHESIS_MIN_PENDING || AUTO_SYNTHESIS_MIN_PENDING_DEFAULT);
  const firstMinPending = Number(options.firstMinPending || process.env.THINGY_MEMORY_AUTO_SYNTHESIS_FIRST_MIN_PENDING || AUTO_SYNTHESIS_FIRST_MIN_PENDING_DEFAULT);
  if (!lastSynthesizedAt && pending >= firstMinPending) return true;
  if (pending >= minPending) return true;
  const maxAgeHours = Number(options.maxPendingAgeHours || process.env.THINGY_MEMORY_AUTO_SYNTHESIS_MAX_PENDING_AGE_HOURS || AUTO_SYNTHESIS_MAX_PENDING_AGE_HOURS_DEFAULT);
  const oldest = Date.parse(pendingEvents[0]?.ts || '');
  const now = Date.parse(nowIso);
  return Number.isFinite(oldest) && Number.isFinite(now) && now - oldest >= maxAgeHours * 60 * 60 * 1000;
}

async function synthesizeEngagementMemories(events = [], memory = {}, nowIso = new Date().toISOString()) {
  if (!events.length) return { ok: true, memories: [] };
  const eventLines = events.map((event, idx) => {
    const label = String(event.label || '').trim().replace(/\s+/g, ' ');
    const detail = String(event.detail || '').trim().replace(/\s+/g, ' ');
    const body = label && detail && detail !== label
      ? `${label} — ${detail}`
      : label || detail;
    return `${idx + 1}. [${event.event_id || event.id || ''}] ${event.type || 'event'}: ${body}`;
  }).join('\n').slice(0, 10000);
  const system = [
    'You synthesize a Thingy reader profile from observed archive-use behavior.',
    'Thingy is Jamie Thingelstad\'s archive agent. The profile should describe what the reader explores in the archive, not personal identity.',
    'Create only durable, user-visible observations supported by repeated or meaningful questions, conversation topics, and retained thread summaries.',
    'When there are several substantive conversation summaries, return 2 to 6 profile items rather than an empty profile.',
    'Use stable labels that would remain the same if the same evidence were synthesized again.',
    'Do not infer sensitive personal details, demographics, health, finances, family, schedules, addresses, or anything outside archive engagement.',
    'Return strict JSON: {"memories":[{"type":"observed_archive_theme|exploration_style|source_affinity|recent_trajectory","label":"stable short label","summary":"one sentence","confidence":0.0,"evidence":[{"event_id":"id","label":"why"}]}]}.',
    'Return {"memories":[]} when there is nothing useful to learn.'
  ].join(' ');
  const user = `Observed Thingy engagement events:\n${eventLines}`;
  try {
    const { ConverseCommand } = await import('@aws-sdk/client-bedrock-runtime');
    const { bedrock, fastModel } = await import('./aws-clients.mjs');
    const response = await bedrock.send(new ConverseCommand({
      modelId: fastModel(),
      system: [{ text: system }],
      messages: [{ role: 'user', content: [{ text: user }] }],
      inferenceConfig: { maxTokens: MEMORY_SYNTHESIS_MAX_TOKENS, temperature: 0 }
    }));
    const parts = response?.output?.message?.content || [];
    const text = parts.map((part) => part.text || '').filter(Boolean).join(' ').trim();
    const parsed = parseSynthesizedMemoryJson(text, nowIso);
    if (!parsed) return { ok: false, memories: [], error: 'Memory synthesis returned invalid JSON.' };
    if (!parsed.length && events.length) return { ok: false, memories: [], error: MEMORY_EMPTY_SYNTHESIS_ERROR };
    return { ok: true, memories: parsed };
  } catch (error) {
    logEvent('warning', 'user_memory_engagement_synthesis_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return { ok: false, memories: [], error: 'Memory synthesis failed.' };
  }
}

export async function synthesizeUserMemory(sub, options = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return { ok: false, error: 'Missing memory context.' };
  const mode = String(options.mode || 'refresh');
  const nowIso = new Date().toISOString();
  const existing = await getUserMemory(sub, { consistent: true }) || { sub };
  const since = mode === 'refresh'
    ? String(options.from || '').trim()
    : String(existing.memory_synthesis?.last_synthesized_at || options.from || '').trim();
  const events = await listUserMemoryEvents(sub, { since, limit: MEMORY_EVENT_LIMIT });
  const allEvents = await listUserMemoryEvents(sub, { limit: MEMORY_EVENT_LIMIT });
  const extraEvents = (Array.isArray(options.extraEvents) ? options.extraEvents : [])
    .map((event) => ({
      ...event,
      type: String(event.type || event.event_type || '').trim(),
      ts: String(event.ts || event.updated_at || event.created_at || nowIso)
    }))
    .filter((event) => event.type && event.label);
  const synthesisEvents = [...events, ...extraEvents]
    .filter((event) => SYNTHESIZABLE_MEMORY_EVENT_TYPES.has(event.type || event.event_type || ''))
    .sort((a, b) => String(a.ts || '').localeCompare(String(b.ts || '')));
  const allSynthesisEvents = [...allEvents, ...extraEvents]
    .filter((event) => SYNTHESIZABLE_MEMORY_EVENT_TYPES.has(event.type || event.event_type || ''));
  const lastEventAt = allSynthesisEvents.reduce((latest, event) => event.ts && event.ts > latest ? event.ts : latest, existing.memory_synthesis?.last_event_at || '');
  const generated = await synthesizeEngagementMemories(synthesisEvents, existing, nowIso);
  if (!generated.ok) {
    logEvent('warning', 'user_memory_synthesis_preserved', {
      mode,
      error: generated.error || 'Memory synthesis failed.',
      event_count: synthesisEvents.length
    });
    const memory = {
      ...existing,
      memory_synthesis: {
        ...(existing.memory_synthesis || {}),
        last_event_at: lastEventAt,
        pending_event_count: synthesisEvents.length,
        status: 'error',
        error: generated.error || 'Memory synthesis failed.'
      }
    };
    return {
      ok: true,
      error: generated.error || 'Memory synthesis failed.',
      refresh_error: MEMORY_REFRESH_PRESERVED_ERROR,
      memory,
      generated_count: 0,
      preserved: true
    };
  }
  const learnedProfile = mergeLearnedProfile(
    existing.learned_profile || [],
    generated.memories || [],
    nowIso,
    existing.memory_tombstones || []
  );
  const nextVersion = Number(existing.version || 0) + 1;
  const nextStatus = {
    last_synthesized_at: nowIso,
    last_event_at: lastEventAt,
    pending_event_count: 0,
    status: 'current',
    error: ''
  };
  const { PutItemCommand } = await import('@aws-sdk/client-dynamodb');
  const { dynamodb } = await import('./aws-clients.mjs');
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: memoryDynamoItem(sub, existing, nowIso, {
      version: nextVersion,
      last_seen_at: nowIso,
      learned_profile: learnedProfile,
      memory_synthesis: nextStatus
    })
  }));
  logEvent('info', 'user_memory_synthesized', {
    mode,
    event_count: synthesisEvents.length,
    learned_profile_len: learnedProfile.length
  });
  const memory = await getUserMemory(sub, { consistent: true });
  return { ok: true, memory, generated_count: generated.memories.length };
}

export async function maybeSynthesizeUserMemory(sub, options = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return { ok: false, skipped: true, reason: 'missing_context' };
  const nowIso = String(options.nowIso || new Date().toISOString());
  const memory = await getUserMemory(sub, { consistent: true }) || { sub };
  const events = await listUserMemoryEvents(sub, { limit: MEMORY_EVENT_LIMIT });
  if (!shouldAutoSynthesizeMemory(memory, events, nowIso, options)) {
    return { ok: true, skipped: true, reason: 'not_due' };
  }
  return await synthesizeUserMemory(sub, { mode: 'incremental' });
}

export async function deleteUserMemoryItem(sub, input = {}) {
  const tableName = process.env.TABLE_NAME;
  const id = String(input.id || input.memory_id || '').trim();
  const type = String(input.type || '').trim();
  const value = String(input.value || '').trim();
  if (!tableName || !sub || (!id && !value)) return { ok: false, error: 'Missing memory item.' };
  const existing = await getUserMemory(sub, { consistent: true });
  if (!existing) return { ok: false, error: 'Memory not found.' };
  const nowIso = new Date().toISOString();
  let deleted = false;
  const match = (item) => (
    (id && item?.id === id) ||
    (value && String(item?.value || item?.summary || item?.label || item?.question || '').trim() === value)
  );
  let synthesizedHistory = existing.synthesized_history || [];
  let currentQuestions = existing.current_session_questions || [];
  let learnedProfile = existing.learned_profile || [];
  let deletedTombstones = [];

  if (['thread', 'prior_thread', 'summary'].includes(type)) {
    const next = synthesizedHistory.filter((item) => !match(item));
    deleted = next.length !== synthesizedHistory.length;
    synthesizedHistory = next;
  } else if (['recent', 'question'].includes(type)) {
    const next = currentQuestions.filter((item) => !match(item));
    deleted = next.length !== currentQuestions.length;
    currentQuestions = next;
  } else if (['learned', 'learned_profile'].includes(type)) {
    const learnedMatch = (item) => match(item) || item.id === id || learnedMemoryStableId(item) === id;
    const removed = learnedProfile.filter((item) => learnedMatch(item));
    const next = learnedProfile.filter((item) => !learnedMatch(item));
    deleted = next.length !== learnedProfile.length;
    learnedProfile = next;
    deletedTombstones = removed.flatMap((item) => {
      const stableId = learnedMemoryStableId(item);
      return [...new Set([item.id, stableId].filter(Boolean))].map((memory_id) => ({
        memory_id,
        type: 'learned',
        deleted_at: nowIso,
        reason: 'user_deleted'
      }));
    });
  }
  if (!deleted) return { ok: false, error: 'Memory item not found.', memory: existing };

  const memoryTombstones = [
    ...(existing.memory_tombstones || []),
    ...(deletedTombstones.length
      ? deletedTombstones
      : [{ memory_id: id || memoryItemId(type || 'memory', value), type, deleted_at: nowIso, reason: 'user_deleted' }])
  ].slice(-MEMORY_TOMBSTONES_MAX);
  const nextVersion = Number(existing.version || 0) + 1;
  const { PutItemCommand } = await import('@aws-sdk/client-dynamodb');
  const { dynamodb } = await import('./aws-clients.mjs');
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: memoryDynamoItem(sub, existing, nowIso, {
      version: nextVersion,
      last_seen_at: nowIso,
      current_session_questions: currentQuestions,
      synthesized_history: synthesizedHistory,
      learned_profile: learnedProfile,
      memory_tombstones: memoryTombstones
    })
  }));
  recordMemoryEvent(sub, {
    type: 'memory_deleted',
    ts: nowIso,
    label: type || id || value,
    metadata: { type, id }
  }).catch(() => {});
  const memory = await getUserMemory(sub, { consistent: true });
  return { ok: true, memory };
}

// Shape memory for an auth response. Returning users get the
// `returning` flag plus their current/prior topic surface so the
// frontend (web or Discord) can offer a "welcome back" prompt.
export function authProfile(memory) {
  if (!memory) {
    return { returning: false };
  }
  const turnCount = Number(memory.turn_count || 0);
  const learnedProfile = (memory.learned_profile || []).slice(-LEARNED_PROFILE_MAX);
  return {
    returning: turnCount > 0,
    first_seen_at: memory.first_seen_at,
    last_seen_at: memory.last_seen_at,
    preferred_name: memory.preferred_name || '',
    turn_count: turnCount,
    current_session_questions: (memory.current_session_questions || []).slice(-5),
    prior_session_summaries: usefulSynthesizedHistory(memory.synthesized_history).slice(-3),
    learned_profile: learnedProfile,
    memory_synthesis: memory.memory_synthesis || {},
    discord_connection: memory.discord_connection || null
  };
}

// Format a compact context block to inject into Thingy's system prompt
// at chat time. Gives the agent a brief sense of what this user has
// asked about before so it can respond more personally.
export function memoryContextBlock(memory) {
  if (!memory) return '';
  const lines = [];
  const learned = (memory.learned_profile || []).slice(-6);
  if (learned.length <= 0) return '';
  lines.push('Learned reader profile from observed Thingy archive use:');
  learned.forEach((item) => {
    lines.push(`- ${item.label || item.type}: ${item.summary || item.label}`);
  });
  return lines.length > 0 ? lines.join('\n') : '';
}
