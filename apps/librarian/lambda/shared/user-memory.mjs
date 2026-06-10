// Per-user memory backed by the existing Librarian DynamoDB table.
//
// Each user (web subscriber or Discord member) gets one row keyed by
// the session token's `sub`. The row tracks:
//
//   - first_seen_at / last_seen_at / turn_count
//   - current_session_id            — sid of the in-flight session
//   - current_session_questions     — rolling questions for that session
//   - synthesized_history           — Bedrock-summarized past sessions
//   - remembered_facts              — explicit reader-offered preferences/interests
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
const SYNTHESIZED_MEMORIES_MAX = 12;
const QUESTION_TRIM_CHARS = 400;
const REMEMBERED_FACTS_MAX = 24;
const INTERESTS_MAX = 16;
const MEMORY_TOMBSTONES_MAX = 48;
const MEMORY_EVENT_LIMIT = 120;
const TTL_DAYS_DEFAULT = 365;
const SYNTHESIS_MAX_TOKENS = 160;
const MEMORY_SYNTHESIS_MAX_TOKENS = 900;
const MEMORY_SYNTHESIS_VERSION = 'thingy-memory-v1';
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

function readFact(item) {
  if (!item || !item.M) return null;
  const category = item.M.category?.S || '';
  const value = item.M.value?.S || '';
  if (!category || !value) return null;
  const source = item.M.source?.S || '';
  const remembered_at = item.M.remembered_at?.S || '';
  return {
    id: item.M.id?.S || memoryItemId('fact', category, remembered_at, value, source),
    category,
    value,
    source,
    remembered_at
  };
}

function writeFactItem({ id, category, value, source, remembered_at }) {
  const cleanValue = String(value || '').slice(0, 240);
  const cleanSource = String(source || '').slice(0, 120);
  return {
    M: {
      id: dynamoString(id || memoryItemId('fact', category, remembered_at, cleanValue, cleanSource)),
      category: dynamoString(category),
      value: dynamoString(cleanValue),
      source: dynamoString(cleanSource),
      remembered_at: dynamoString(remembered_at || '')
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

function readSynthesizedMemory(item) {
  if (!item || !item.M) return null;
  const label = item.M.label?.S || '';
  const summary = item.M.summary?.S || '';
  if (!label && !summary) return null;
  const created_at = item.M.created_at?.S || '';
  const synthesized_at = item.M.synthesized_at?.S || created_at;
  return {
    id: item.M.id?.S || memoryItemId('learned', label, summary, synthesized_at),
    type: item.M.type?.S || 'learned',
    label,
    summary,
    confidence: Number(item.M.confidence?.N || 0),
    evidence: readEvidenceList(item.M.evidence),
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
  return {
    M: {
      id: dynamoString(memory.id || memoryItemId('learned', label, summary, synthesizedAt)),
      type: dynamoString(String(memory.type || 'learned').slice(0, 80)),
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

function readStringList(value) {
  return (value?.L || [])
    .map((item) => item.S || '')
    .filter(Boolean);
}

function writeStringList(values) {
  return { L: (values || []).map((value) => dynamoString(value)) };
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

export function normalizeMemoryCategory(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (['name', 'preferred_name', 'call_me'].includes(raw)) return 'preferred_name';
  if (['interest', 'topic', 'likes', 'curious_about'].includes(raw)) return 'interest';
  if (['preference', 'answer_preference', 'style', 'format'].includes(raw)) return 'preference';
  if (['project', 'work', 'current_project'].includes(raw)) return 'project';
  if (['relationship', 'relationship_to_archive', 'reader_context'].includes(raw)) return 'relationship_to_archive';
  if (['note', 'memory', 'remember'].includes(raw)) return 'note';
  return '';
}

export function normalizeMemoryFact(input = {}) {
  const category = normalizeMemoryCategory(input.category || input.type);
  const value = String(input.value || input.name || input.interest || '').trim().replace(/\s+/g, ' ').slice(0, 240);
  const source = String(input.source || input.reason || '').trim().replace(/\s+/g, ' ').slice(0, 120);
  if (!category || !value) return null;
  return { category, value, source };
}

function mergeUniqueStrings(existing = [], next = [], limit = INTERESTS_MAX) {
  const seen = new Set();
  const merged = [];
  for (const value of [...existing, ...next]) {
    const clean = String(value || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const key = clean.toLowerCase();
    if (!clean || seen.has(key)) continue;
    seen.add(key);
    merged.push(clean);
  }
  return merged.slice(-limit);
}

export function mergeRememberedFacts(existing = [], incoming, nowIso = new Date().toISOString()) {
  const fact = normalizeMemoryFact(incoming);
  if (!fact) return existing.slice(-REMEMBERED_FACTS_MAX);
  const withoutDuplicate = (existing || []).filter((item) => (
    String(item.category || '').toLowerCase() !== fact.category ||
    String(item.value || '').trim().toLowerCase() !== fact.value.toLowerCase()
  ));
  return [
    ...withoutDuplicate,
    { ...fact, id: memoryItemId('fact', fact.category, nowIso, fact.value, fact.source), remembered_at: nowIso }
  ].slice(-REMEMBERED_FACTS_MAX);
}

function interestsFromFacts(facts = [], fallback = []) {
  const fromFacts = (facts || [])
    .filter((item) => item?.category === 'interest')
    .map((item) => item.value);
  return mergeUniqueStrings([], fromFacts.length ? fromFacts : fallback, INTERESTS_MAX);
}

function memoryDynamoItem(sub, memory = {}, nowIso = new Date().toISOString(), overrides = {}) {
  const version = Number(overrides.version ?? memory.version ?? 0);
  return {
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
    remembered_facts: { L: (overrides.remembered_facts || memory.remembered_facts || []).map(writeFactItem) },
    interests: writeStringList(overrides.interests || memory.interests || []),
    synthesized_memories: { L: (overrides.synthesized_memories || memory.synthesized_memories || []).map(writeSynthesizedMemoryItem) },
    memory_tombstones: { L: (overrides.memory_tombstones || memory.memory_tombstones || []).map(writeTombstoneItem) },
    memory_synthesis: writeSynthesisStatus(overrides.memory_synthesis || memory.memory_synthesis || {}),
    ttl: dynamoNumber(ttlFromNow())
  };
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
  const rememberedFacts = (item.remembered_facts?.L || [])
    .map(readFact)
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
    remembered_facts: rememberedFacts,
    interests: readStringList(item.interests),
    synthesized_memories: (item.synthesized_memories?.L || [])
      .map(readSynthesizedMemory)
      .filter(Boolean),
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
    const rememberedFacts = existing?.remembered_facts || [];
    const interests = existing?.interests || [];

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
      synthesized_history: synthesizedHistory,
      remembered_facts: rememberedFacts,
      interests
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

export async function rememberUserFact(sub, input = {}) {
  const tableName = process.env.TABLE_NAME;
  const fact = normalizeMemoryFact(input);
  if (!tableName || !sub || !fact) return { ok: false, error: 'Nothing memorable supplied.' };
  const nowIso = new Date().toISOString();
  try {
    if (fact.category === 'preferred_name') {
      await recordUserPreferredName(sub, fact.value);
    }
    const existing = await getUserMemory(sub);
    const rememberedFacts = mergeRememberedFacts(existing?.remembered_facts || [], fact, nowIso);
    const interests = fact.category === 'interest'
      ? mergeUniqueStrings(existing?.interests || [], [fact.value])
      : existing?.interests || [];
    const { UpdateItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    await dynamodb.send(new UpdateItemCommand({
      TableName: tableName,
      Key: memoryKey(sub),
      UpdateExpression: [
        'SET #first_seen_at = if_not_exists(#first_seen_at, :now)',
        '#last_seen_at = :now',
        '#remembered_facts = :remembered_facts',
        '#interests = :interests',
        '#ttl = :ttl',
        '#version = if_not_exists(#version, :zero) + :one'
      ].join(', '),
      ExpressionAttributeNames: {
        '#first_seen_at': 'first_seen_at',
        '#last_seen_at': 'last_seen_at',
        '#remembered_facts': 'remembered_facts',
        '#interests': 'interests',
        '#ttl': 'ttl',
        '#version': 'version'
      },
      ExpressionAttributeValues: {
        ':now': dynamoString(nowIso),
        ':remembered_facts': { L: rememberedFacts.map(writeFactItem) },
        ':interests': writeStringList(interests),
        ':ttl': dynamoNumber(ttlFromNow()),
        ':zero': dynamoNumber(0),
        ':one': dynamoNumber(1)
      }
    }));
    logEvent('info', 'user_fact_remembered', {
      category: fact.category,
      remembered_facts_len: rememberedFacts.length,
      interests_len: interests.length
    });
    recordMemoryEvent(sub, {
      type: 'remembered_fact',
      ts: nowIso,
      label: `${fact.category}: ${fact.value}`,
      detail: fact.value,
      metadata: { category: fact.category }
    }).catch(() => {});
    return {
      ok: true,
      fact: { ...fact, remembered_at: nowIso },
      interests
    };
  } catch (error) {
    logEvent('warning', 'user_fact_remember_failed', {
      category: fact.category,
      error_type: error?.constructor?.name || 'Error'
    });
    return { ok: false, error: 'Memory write failed.' };
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

function parseSynthesizedMemoryJson(text, nowIso = new Date().toISOString()) {
  const raw = String(text || '').trim().replace(/^```(?:json)?/i, '').replace(/```$/i, '').trim();
  if (!raw) return [];
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  const rows = Array.isArray(parsed) ? parsed : Array.isArray(parsed.memories) ? parsed.memories : [];
  return rows.map((item) => {
    const label = String(item.label || item.title || '').trim().replace(/\s+/g, ' ').slice(0, 160);
    const summary = String(item.summary || item.description || '').trim().replace(/\s+/g, ' ').slice(0, 600);
    if (!label && !summary) return null;
    const evidence = Array.isArray(item.evidence) ? item.evidence : [];
    return {
      id: item.id || memoryItemId('learned', label, summary, nowIso),
      type: String(item.type || 'learned').slice(0, 80),
      label: label || summary.slice(0, 80),
      summary,
      confidence: Math.max(0, Math.min(1, Number(item.confidence || 0.5))),
      evidence: evidence.map((entry) => ({
        event_id: String(entry.event_id || entry.id || '').slice(0, 80),
        label: String(entry.label || entry.summary || '').trim().replace(/\s+/g, ' ').slice(0, 160)
      })).filter((entry) => entry.event_id || entry.label).slice(0, 8),
      created_at: nowIso,
      updated_at: nowIso,
      synthesized_at: nowIso,
      synthesis_version: MEMORY_SYNTHESIS_VERSION
    };
  }).filter(Boolean).slice(0, SYNTHESIZED_MEMORIES_MAX);
}

function heuristicSynthesizedMemories(events = [], nowIso = new Date().toISOString()) {
  const labels = events.map((event) => String(event.label || event.detail || '').trim()).filter(Boolean).slice(-6);
  if (labels.length < 2) return [];
  const summary = `Recent activity includes ${labels.slice(0, 4).join('; ')}.`;
  return [{
    id: memoryItemId('learned', 'recent archive interests', summary, nowIso),
    type: 'learned',
    label: 'Recent archive interests',
    summary,
    confidence: 0.35,
    evidence: events.slice(-6).map((event) => ({ event_id: event.event_id || event.id || '', label: event.label || '' })),
    created_at: nowIso,
    updated_at: nowIso,
    synthesized_at: nowIso,
    synthesis_version: MEMORY_SYNTHESIS_VERSION
  }];
}

function mergeSynthesizedMemories(existing = [], incoming = []) {
  const seen = new Set();
  const merged = [];
  for (const item of [...existing, ...incoming]) {
    const key = String(item.id || item.label || item.summary || '').trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    merged.push(item);
  }
  return merged.slice(-SYNTHESIZED_MEMORIES_MAX);
}

export function memorySynthesisStatus(memory = {}, events = []) {
  const stored = memory?.memory_synthesis || {};
  const lastSynthesizedAt = String(stored.last_synthesized_at || '').trim();
  const lastEventAt = events.reduce((latest, event) => (
    event.ts && event.ts > latest ? event.ts : latest
  ), String(stored.last_event_at || '').trim());
  const pending = events.filter((event) => event.ts && (!lastSynthesizedAt || event.ts > lastSynthesizedAt)).length;
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

async function synthesizeEngagementMemories(events = [], memory = {}, nowIso = new Date().toISOString()) {
  if (!events.length) return [];
  const facts = (memory.remembered_facts || []).map((fact) => `${fact.category}: ${fact.value}`).join('\n');
  const eventLines = events.map((event, idx) => (
    `${idx + 1}. [${event.event_id || event.id || ''}] ${event.type || 'event'}: ${event.label || event.detail || ''}`
  )).join('\n').slice(0, 8000);
  const system = [
    'You synthesize Thingy user engagement into durable, user-visible learned memories.',
    'Create only memories supported by repeated or meaningful user activity.',
    'Do not infer sensitive personal details. Do not invent facts.',
    'Return strict JSON: {"memories":[{"type":"learned_interest|learned_preference|learned_pattern","label":"short label","summary":"one sentence","confidence":0.0,"evidence":[{"event_id":"id","label":"why"}]}]}.',
    'Return {"memories":[]} when there is nothing useful to learn.'
  ].join(' ');
  const user = [
    facts ? `Explicit remembered facts:\n${facts}` : 'No explicit remembered facts.',
    '',
    `Engagement events:\n${eventLines}`
  ].join('\n');
  try {
    const { ConverseCommand } = await import('@aws-sdk/client-bedrock-runtime');
    const { bedrock, fastModel } = await import('./aws-clients.mjs');
    const response = await bedrock.send(new ConverseCommand({
      modelId: fastModel(),
      system: [{ text: system }],
      messages: [{ role: 'user', content: [{ text: user }] }],
      inferenceConfig: { maxTokens: MEMORY_SYNTHESIS_MAX_TOKENS, temperature: 0.2 }
    }));
    const parts = response?.output?.message?.content || [];
    const text = parts.map((part) => part.text || '').filter(Boolean).join(' ').trim();
    const parsed = parseSynthesizedMemoryJson(text, nowIso);
    return parsed.length ? parsed : heuristicSynthesizedMemories(events, nowIso);
  } catch (error) {
    logEvent('warning', 'user_memory_engagement_synthesis_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return heuristicSynthesizedMemories(events, nowIso);
  }
}

export async function synthesizeUserMemory(sub, options = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return { ok: false, error: 'Missing memory context.' };
  const mode = String(options.mode || 'incremental');
  const nowIso = new Date().toISOString();
  const existing = await getUserMemory(sub, { consistent: true }) || { sub };
  const since = mode === 'full'
    ? String(options.from || '').trim()
    : String(existing.memory_synthesis?.last_synthesized_at || options.from || '').trim();
  const events = await listUserMemoryEvents(sub, { since, limit: MEMORY_EVENT_LIMIT });
  const allEvents = await listUserMemoryEvents(sub, { limit: MEMORY_EVENT_LIMIT });
  const lastEventAt = allEvents.reduce((latest, event) => event.ts && event.ts > latest ? event.ts : latest, existing.memory_synthesis?.last_event_at || '');
  const generated = await synthesizeEngagementMemories(events, existing, nowIso);
  const synthesizedMemories = mode === 'full'
    ? generated
    : mergeSynthesizedMemories(existing.synthesized_memories || [], generated);
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
      synthesized_memories: synthesizedMemories,
      memory_synthesis: nextStatus
    })
  }));
  logEvent('info', 'user_memory_synthesized', {
    mode,
    event_count: events.length,
    synthesized_memories_len: synthesizedMemories.length
  });
  const memory = await getUserMemory(sub, { consistent: true });
  return { ok: true, memory, generated_count: generated.length };
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
  let rememberedFacts = existing.remembered_facts || [];
  let synthesizedHistory = existing.synthesized_history || [];
  let currentQuestions = existing.current_session_questions || [];
  let synthesizedMemories = existing.synthesized_memories || [];
  let interests = existing.interests || [];

  if (['remembered_fact', 'fact', 'details', 'detail'].includes(type)) {
    const next = rememberedFacts.filter((item) => !match(item));
    deleted = next.length !== rememberedFacts.length;
    rememberedFacts = next;
    interests = interestsFromFacts(rememberedFacts, []);
  } else if (type === 'interest') {
    const nextInterests = interests.filter((item) => !(id === memoryItemId('interest', item) || item === value));
    const nextFacts = rememberedFacts.filter((item) => !(item.category === 'interest' && (match(item) || item.value === value)));
    deleted = nextInterests.length !== interests.length || nextFacts.length !== rememberedFacts.length;
    interests = nextInterests;
    rememberedFacts = nextFacts;
  } else if (['thread', 'prior_thread', 'summary'].includes(type)) {
    const next = synthesizedHistory.filter((item) => !match(item));
    deleted = next.length !== synthesizedHistory.length;
    synthesizedHistory = next;
  } else if (['recent', 'question'].includes(type)) {
    const next = currentQuestions.filter((item) => !match(item));
    deleted = next.length !== currentQuestions.length;
    currentQuestions = next;
  } else if (['learned', 'synthesized_memory'].includes(type)) {
    const next = synthesizedMemories.filter((item) => !match(item));
    deleted = next.length !== synthesizedMemories.length;
    synthesizedMemories = next;
  }
  if (!deleted) return { ok: false, error: 'Memory item not found.', memory: existing };

  const memoryTombstones = [
    ...(existing.memory_tombstones || []),
    { memory_id: id || memoryItemId(type || 'memory', value), type, deleted_at: nowIso, reason: 'user_deleted' }
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
      remembered_facts: rememberedFacts,
      interests,
      synthesized_memories: synthesizedMemories,
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
  return {
    returning: turnCount > 0,
    first_seen_at: memory.first_seen_at,
    last_seen_at: memory.last_seen_at,
    preferred_name: memory.preferred_name || '',
    turn_count: turnCount,
    current_session_questions: (memory.current_session_questions || []).slice(-5),
    prior_session_summaries: usefulSynthesizedHistory(memory.synthesized_history).slice(-3),
    remembered_facts: (memory.remembered_facts || []).slice(-8),
    interests: (memory.interests || []).slice(-8),
    synthesized_memories: (memory.synthesized_memories || []).slice(-8),
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
  const summaries = usefulSynthesizedHistory(memory.synthesized_history).slice(-3);
  if (summaries.length > 0) {
    lines.push('What this reader has been exploring across past sessions:');
    summaries.forEach((s, idx) => {
      const when = s.ended_at ? s.ended_at.slice(0, 10) : '';
      lines.push(`- ${when ? `(${when}) ` : ''}${s.summary}`);
    });
  }
  const current = (memory.current_session_questions || []).slice(-4);
  if (current.length > 0 && lines.length > 0) {
    lines.push('');
  }
  if (current.length > 0) {
    lines.push('Earlier in this same session they asked:');
    current.forEach((q) => {
      lines.push(`- ${q.question}`);
    });
  }
  const facts = (memory.remembered_facts || []).slice(-8);
  if (facts.length > 0) {
    if (lines.length > 0) lines.push('');
    lines.push('Remembered reader details explicitly offered by the reader:');
    facts.forEach((fact) => {
      lines.push(`- ${fact.category}: ${fact.value}`);
    });
  }
  const interests = (memory.interests || []).slice(-8);
  if (interests.length > 0) {
    if (lines.length > 0) lines.push('');
    lines.push(`Reader interests to consider when useful: ${interests.join(', ')}`);
  }
  const learned = (memory.synthesized_memories || []).slice(-6);
  if (learned.length > 0) {
    if (lines.length > 0) lines.push('');
    lines.push('Learned reader context synthesized from prior engagement:');
    learned.forEach((item) => {
      lines.push(`- ${item.label || item.type}: ${item.summary || item.label}`);
    });
  }
  return lines.length > 0 ? lines.join('\n') : '';
}
