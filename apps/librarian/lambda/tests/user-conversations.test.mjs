import assert from 'node:assert/strict';
import test from 'node:test';
import {
  artifactDynamoString,
  artifactJsonForStorage,
  conversationSummaryFromItem,
  conversationTitle,
  conversationTurnFromItem,
  historyFromTurns,
  messagesFromTurns,
  turnSk,
  turnSkPrefix,
  userConversationPk,
  validConversationId
} from '../shared/user-conversations.mjs';

test('conversation key helpers namespace records by user and conversation', () => {
  assert.equal(userConversationPk('abc'), 'user#abc');
  assert.equal(turnSkPrefix('c1'), 'turn#c1#');
  assert.equal(turnSk('c1', '2026-06-06T01:02:03.000Z', 'r1'), 'turn#c1#2026-06-06T01:02:03.000Z#r1');
  assert.equal(validConversationId('c_abc-123.def:456'), 'c_abc-123.def:456');
  assert.equal(validConversationId('../bad'), '');
});

test('conversationTitle compacts and caps first question', () => {
  assert.equal(conversationTitle('  What   did Jamie write about RSS?  '), 'What did Jamie write about RSS?');
  assert.equal(conversationTitle(''), 'Untitled chat');
  assert.equal(conversationTitle('x'.repeat(100)).length, 80);
});

test('conversationSummaryFromItem unmarshals metadata rows', () => {
  const row = conversationSummaryFromItem({
    sk: { S: 'conversation#c1' },
    title: { S: 'A topic' },
    preview: { S: 'Question preview' },
    scope: { S: 'blog' },
    created_at: { S: '2026-06-06T01:00:00.000Z' },
    updated_at: { S: '2026-06-06T01:03:00.000Z' },
    turn_count: { N: '2' }
  });
  assert.deepEqual(row, {
    id: 'c1',
    conversation_id: 'c1',
    title: 'A topic',
    preview: 'Question preview',
    scope: 'blog',
    created_at: '2026-06-06T01:00:00.000Z',
    updated_at: '2026-06-06T01:03:00.000Z',
    last_message_at: '2026-06-06T01:03:00.000Z',
    last_request_id: '',
    turn_count: 2
  });
});

test('turns expand into messages and compact history', () => {
  const turn = conversationTurnFromItem({
    conversation_id: { S: 'c1' },
    request_id: { S: 'r1' },
    created_at: { S: '2026-06-06T01:00:00.000Z' },
    scope: { S: 'all' },
    question: { S: 'Question?' },
    answer: { S: 'Answer.' },
    citations: { L: [{ M: { subject: { S: 'Source' } } }] }
  });
  assert.equal(turn.request_id, 'r1');
  assert.equal(turn.citations[0].subject, 'Source');
  assert.deepEqual(messagesFromTurns([turn]).map((item) => item.role), ['user', 'assistant']);
  assert.deepEqual(historyFromTurns([turn]), [
    { role: 'user', content: 'Question?' },
    { role: 'assistant', content: 'Answer.' }
  ]);
});

test('artifact-only turns expand into assistant artifact messages', () => {
  const artifact = {
    kind: 'curiosity_map',
    title: 'Curiosity Map: RSS',
    nodes: [{ id: 'rss', label: 'RSS', kind: 'center' }],
    edges: []
  };
  const turn = conversationTurnFromItem({
    conversation_id: { S: 'c-map' },
    request_id: { S: 'r-map' },
    created_at: { S: '2026-06-06T02:00:00.000Z' },
    scope: { S: 'all' },
    question: { S: '' },
    answer: { S: '' },
    artifact_json: artifactDynamoString(artifact)
  });
  assert.equal(turn.artifact.title, 'Curiosity Map: RSS');
  assert.deepEqual(messagesFromTurns([turn]), [{
    role: 'assistant',
    content: '',
    citations: [],
    created_at: '2026-06-06T02:00:00.000Z',
    request_id: 'r-map',
    artifact
  }]);
  assert.deepEqual(historyFromTurns([turn]), []);
});

test('oversized artifacts are compacted without corrupting JSON', () => {
  const artifact = {
    kind: 'curiosity_map',
    title: 'Curiosity Map: Long',
    center: { id: 'long', label: 'Long', kind: 'center', prompt: 'Build a long map.', why: 'Large fixture.' },
    nodes: Array.from({ length: 40 }, (_, index) => ({
      id: `node-${index}`,
      label: `Node ${index}`,
      kind: 'archive',
      prompt: `Trace a very long prompt ${index} ${'x'.repeat(800)}`,
      why: `A very long reason ${index} ${'y'.repeat(800)}`,
      source_refs: [{ title: `Source ${index}`, url: `https://example.com/${index}`, reason: 'Fixture' }]
    })),
    edges: Array.from({ length: 40 }, (_, index) => ({ from: 'long', to: `node-${index}`, why: 'Fixture edge' })),
    sources: Array.from({ length: 20 }, (_, index) => ({ title: `Source ${index}`, url: `https://example.com/${index}` })),
    prompt: 'Follow this huge map.'
  };
  const json = artifactJsonForStorage(artifact);
  assert.ok(json.length <= 20000);
  const parsed = JSON.parse(json);
  assert.equal(parsed.kind, 'curiosity_map');
  assert.equal(parsed.compacted, true);

  const turn = conversationTurnFromItem({
    conversation_id: { S: 'c-map' },
    request_id: { S: 'r-map' },
    created_at: { S: '2026-06-06T02:00:00.000Z' },
    artifact_json: artifactDynamoString(artifact)
  });
  assert.equal(turn.artifact.kind, 'curiosity_map');
  assert.ok(turn.artifact.nodes.length > 0);
});
