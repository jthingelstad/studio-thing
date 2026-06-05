// Per-user memory backed by the existing Librarian DynamoDB table.
//
// Each user (web subscriber or Discord member) gets one row keyed by
// the session token's `sub`. The row tracks:
//
//   - first_seen_at / last_seen_at / turn_count
//   - current_session_id            — sid of the in-flight session
//   - current_session_questions     — rolling questions for that session
//   - synthesized_history           — Bedrock-summarized past sessions
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

import { logEvent } from './logging.mjs';

const CURRENT_SESSION_QUESTIONS_MAX = 12;
const SYNTHESIZED_HISTORY_MAX = 8;
const QUESTION_TRIM_CHARS = 400;
const TTL_DAYS_DEFAULT = 365;
const SYNTHESIS_MAX_TOKENS = 160;

function dynamoString(value) {
  return { S: String(value ?? '') };
}

function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

function memoryKey(sub) {
  return { pk: dynamoString(`user#${sub}`), sk: dynamoString('memory') };
}

function readQuestion(item) {
  if (!item || !item.M) return null;
  const ts = item.M.ts?.S || '';
  const question = item.M.question?.S || '';
  if (!ts || !question) return null;
  return { ts, question };
}

function writeQuestionItem({ ts, question }) {
  return {
    M: {
      ts: dynamoString(ts),
      question: dynamoString(String(question || '').slice(0, QUESTION_TRIM_CHARS))
    }
  };
}

function readSynth(item) {
  if (!item || !item.M) return null;
  const started_at = item.M.started_at?.S || '';
  const ended_at = item.M.ended_at?.S || '';
  const summary = item.M.summary?.S || '';
  const turn_count = Number(item.M.turn_count?.N || 0);
  if (!summary) return null;
  return { started_at, ended_at, summary, turn_count };
}

function writeSynthItem({ started_at, ended_at, summary, turn_count }) {
  return {
    M: {
      started_at: dynamoString(started_at),
      ended_at: dynamoString(ended_at),
      summary: dynamoString(String(summary || '').slice(0, 1200)),
      turn_count: dynamoNumber(turn_count)
    }
  };
}

function ttlFromNow() {
  const days = Number(process.env.LIBRARIAN_USER_MEMORY_TTL_DAYS || TTL_DAYS_DEFAULT);
  return Math.floor(Date.now() / 1000) + days * 86400;
}

// ---------- public API ----------

export async function getUserMemory(sub) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return null;
  try {
    const { GetItemCommand } = await import('@aws-sdk/client-dynamodb');
    const { dynamodb } = await import('./aws-clients.mjs');
    const response = await dynamodb.send(new GetItemCommand({
      TableName: tableName,
      Key: memoryKey(sub),
      ConsistentRead: false
    }));
    if (!response?.Item) return null;
    const item = response.Item;
    return {
      sub,
      version: Number(item.version?.N || 0),
      first_seen_at: item.first_seen_at?.S || '',
      last_seen_at: item.last_seen_at?.S || '',
      turn_count: Number(item.turn_count?.N || 0),
      current_session_id: item.current_session_id?.S || '',
      current_session_started_at: item.current_session_started_at?.S || '',
      current_session_questions: (item.current_session_questions?.L || [])
        .map(readQuestion)
        .filter(Boolean),
      synthesized_history: (item.synthesized_history?.L || [])
        .map(readSynth)
        .filter(Boolean)
    };
  } catch (error) {
    logEvent('warning', 'user_memory_read_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return null;
  }
}

// Record one chat turn. Best-effort — failures don't propagate.
//
// When the incoming sid differs from current_session_id, the previous
// session's questions get synthesized into a one-paragraph summary and
// rolled into synthesized_history before the new session is opened.
export async function recordUserTurn(sub, { sid, question }) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return;
  const start = Date.now();
  try {
    const existing = await getUserMemory(sub);
    const nowIso = new Date().toISOString();
    const incomingSid = String(sid || '');
    const trimmedQuestion = String(question || '').trim().slice(0, QUESTION_TRIM_CHARS);

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
    const item = {
      pk: dynamoString(`user#${sub}`),
      sk: dynamoString('memory'),
      version: dynamoNumber(nextVersion),
      first_seen_at: dynamoString(existing?.first_seen_at || nowIso),
      last_seen_at: dynamoString(nowIso),
      turn_count: dynamoNumber((existing?.turn_count || 0) + 1),
      current_session_id: dynamoString(currentSessionId),
      current_session_started_at: dynamoString(currentSessionStartedAt),
      current_session_questions: { L: currentSessionQuestions.map(writeQuestionItem) },
      synthesized_history: { L: synthesizedHistory.map(writeSynthItem) },
      ttl: dynamoNumber(ttlFromNow())
    };
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
  } catch (error) {
    logEvent('warning', 'user_memory_write_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
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
    'topics. Do not invent details that the questions did not contain.'
  );
  try {
    const { ConverseCommand } = await import('@aws-sdk/client-bedrock-runtime');
    const { bedrock, agentModel } = await import('./aws-clients.mjs');
    const response = await bedrock.send(new ConverseCommand({
      modelId: agentModel(),
      system: [{ text: system }, { cachePoint: { type: 'default' } }],
      messages: [{ role: 'user', content: [{ text: list }] }],
      inferenceConfig: { maxTokens: SYNTHESIS_MAX_TOKENS, temperature: 0.3 }
    }));
    const parts = response?.output?.message?.content || [];
    const text = parts.map((p) => p.text || '').filter(Boolean).join(' ').trim();
    return text;
  } catch (error) {
    logEvent('warning', 'user_memory_synthesis_failed', {
      error_type: error?.constructor?.name || 'Error'
    });
    return '';
  }
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
    turn_count: turnCount,
    current_session_questions: (memory.current_session_questions || []).slice(-5),
    prior_session_summaries: (memory.synthesized_history || []).slice(-3)
  };
}

// Format a compact context block to inject into Thingy's system prompt
// at chat time. Gives the agent a brief sense of what this user has
// asked about before so it can respond more personally.
export function memoryContextBlock(memory) {
  if (!memory) return '';
  const lines = [];
  const summaries = (memory.synthesized_history || []).slice(-3);
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
  return lines.length > 0 ? lines.join('\n') : '';
}
