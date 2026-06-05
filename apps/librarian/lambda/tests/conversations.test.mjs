import assert from 'node:assert/strict';
import test from 'node:test';
import {
  CONVERSATIONS_DEFAULT_LIMIT,
  CONVERSATIONS_MAX_LIMIT,
  conversationRow,
  fromDynamoAttr,
  normalizeListConversationsParams,
  sortAndTrim
} from '../shared/conversations.mjs';

test('fromDynamoAttr unmarshals the attribute types conversation rows use', () => {
  assert.equal(fromDynamoAttr({ S: 'hello' }), 'hello');
  assert.equal(fromDynamoAttr({ N: '42' }), 42);
  assert.equal(fromDynamoAttr({ BOOL: true }), true);
  assert.equal(fromDynamoAttr({ NULL: true }), null);
  assert.deepEqual(fromDynamoAttr({ L: [{ S: '12' }, { S: '13' }] }), ['12', '13']);
  assert.deepEqual(
    fromDynamoAttr({ M: { issue_number: { S: '247' }, subject: { S: 'A subject' } } }),
    { issue_number: '247', subject: 'A subject' }
  );
  assert.equal(fromDynamoAttr(null), null);
  assert.equal(fromDynamoAttr('raw'), null);
});

test('conversationRow flattens a logged DynamoDB conversation item', () => {
  const item = {
    pk: { S: 'conversation#abc-123' },
    sk: { S: 'chat' },
    created_at: { S: '2026-05-12T02:21:00.000Z' },
    request_id: { S: 'abc-123' },
    subscriber_hash: { S: 'a1b2c3d4e5f6' },
    route: { S: 'stream' },
    question: { S: 'Did Jamie write about RSS?' },
    answer: { S: 'Yes — see WT200 and WT247.' },
    question_chars: { N: '26' },
    answer_chars: { N: '24' },
    history_count: { N: '2' },
    citation_count: { N: '2' },
    source_issues: { L: [{ S: '200' }, { S: '247' }] },
    citations: { L: [{ M: { issue_number: { S: '200' }, url: { S: 'https://weekly.thingelstad.com/archive/200/' } } }] },
    preflight: {
      M: {
        action: { S: 'rewrite' },
        category: { S: 'archive_rewrite' },
        original_question: { S: 'Tell me a story.' },
        rewritten_question: { S: 'Tell a concise archive story with evidence.' },
        rationale: { S: 'Vague but answerable.' }
      }
    },
    feedback_reaction: { S: 'up' },
    feedback_at: { S: '2026-05-12T02:25:00.000Z' },
    user_agent: { S: 'Mozilla/5.0' },
    ttl: { N: '1900000000' }
  };
  const row = conversationRow(item);
  assert.equal(row.request_id, 'abc-123');
  assert.equal(row.created_at, '2026-05-12T02:21:00.000Z');
  assert.equal(row.subscriber_hash, 'a1b2c3d4e5f6');
  assert.equal(row.question, 'Did Jamie write about RSS?');
  assert.equal(row.answer, 'Yes — see WT200 and WT247.');
  assert.equal(row.history_count, 2);
  assert.deepEqual(row.source_issues, ['200', '247']);
  assert.equal(row.citations.length, 1);
  assert.equal(row.citations[0].issue_number, '200');
  assert.equal(row.preflight.action, 'rewrite');
  assert.equal(row.preflight.category, 'archive_rewrite');
  assert.match(row.preflight.rewritten_question, /archive story/);
  assert.equal(row.feedback_reaction, 'up');
  assert.equal(row.user_agent, 'Mozilla/5.0');
  assert.equal('ttl' in row, false);
});

test('conversationRow falls back to the pk for request_id and tolerates a sparse item', () => {
  const row = conversationRow({ pk: { S: 'conversation#deadbeef' }, sk: { S: 'chat' }, created_at: { S: '2026-05-12T00:00:00Z' } });
  assert.equal(row.request_id, 'deadbeef');
  assert.equal(row.question, '');
  assert.equal(row.answer, '');
  assert.deepEqual(row.source_issues, []);
  assert.deepEqual(row.citations, []);
  assert.equal(row.feedback_reaction, null);
});

test('normalizeListConversationsParams defaults the window and clamps the limit', () => {
  const now = Date.parse('2026-05-12T12:00:00Z');
  const a = normalizeListConversationsParams({}, now);
  assert.equal(a.since, '2026-05-11T12:00:00.000Z'); // 24h back
  assert.equal(a.limit, CONVERSATIONS_DEFAULT_LIMIT);

  const b = normalizeListConversationsParams({ since: 'not-a-date', limit: 0 }, now);
  assert.equal(b.since, '2026-05-11T12:00:00.000Z');
  assert.equal(b.limit, CONVERSATIONS_DEFAULT_LIMIT);

  const c = normalizeListConversationsParams({ since: '2026-05-01T00:00:00Z', limit: 99999 }, now);
  assert.equal(c.since, '2026-05-01T00:00:00Z');
  assert.equal(c.limit, CONVERSATIONS_MAX_LIMIT);

  const d = normalizeListConversationsParams({ limit: 7 }, now);
  assert.equal(d.limit, 7);
});

test('sortAndTrim orders oldest-first and keeps the most recent N', () => {
  const rows = [
    { created_at: '2026-05-12T03:00:00Z', request_id: 'c' },
    { created_at: '2026-05-12T01:00:00Z', request_id: 'a' },
    { created_at: '2026-05-12T02:00:00Z', request_id: 'b' }
  ];
  assert.deepEqual(sortAndTrim(rows, 10).map((r) => r.request_id), ['a', 'b', 'c']);
  assert.deepEqual(sortAndTrim(rows, 2).map((r) => r.request_id), ['b', 'c']);
});
