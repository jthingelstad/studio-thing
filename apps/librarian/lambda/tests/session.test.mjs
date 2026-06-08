import assert from 'node:assert/strict';
import test from 'node:test';
import { renderFaqAnswer, searchFaq } from '../shared/faq.mjs';
import { buildMagicLink, createMagicToken, magicTokenHash, validMagicToken } from '../shared/magic-link.mjs';
import { buildMagicLinkJmapCalls, magicLinkEmailHtml, magicLinkEmailText, requireMethodResponse } from '../shared/jmap-mail.mjs';
import { createSessionToken, createSessionTokenForSub, emailHash, normalizeEmail, verifyToken } from '../shared/session.mjs';
import { magicLinkBaseWithReturnPath } from '../auth/handler.mjs';
import {
  authProfile,
  memoryContextBlock,
  mergeRememberedFacts,
  normalizeMemoryFact
} from '../shared/user-memory.mjs';
import { renderTemplate, agentUserPrompt } from '../shared/prompts.mjs';
import { subscriberStatus } from '../shared/buttondown.mjs';
import {
  availableConversationModes,
  canUseConversationMode,
  entitlementsForSubscriber,
  isOwnerEmail,
  normalizeConversationMode
} from '../shared/conversation-modes.mjs';
import { normalizeFeedbackReaction, validFeedbackRequestId } from '../shared/feedback.mjs';
import { readConverseStream } from '../shared/bedrock-stream.mjs';
import {
  PREFLIGHT_SYSTEM_PROMPT,
  normalizePreflightDecision,
  parsePreflightJson,
  passThroughPreflight
} from '../shared/prompt-preflight.mjs';

test('session token round trips and rejects tampering', () => {
  process.env.SESSION_SECRET = 'test-secret';
  const now = Math.floor(Date.now() / 1000);
  const { token, expiresAt } = createSessionToken('Reader@Example.com', 'session-1');
  const payload = verifyToken(token);

  assert.equal(payload.sid, 'session-1');
  assert.equal(payload.sub, emailHash('reader@example.com'));
  assert.ok(expiresAt >= now + 60 * 60 * 24 * 10 - 2);
  assert.ok(expiresAt <= now + 60 * 60 * 24 * 10 + 2);
  assert.equal(verifyToken(`${token}x`), null);
});

test('session token can carry safe entitlement claims', () => {
  process.env.SESSION_SECRET = 'test-secret';
  const { token } = createSessionToken('Reader@Example.com', 'session-2', {
    entitlements: ['reader', 'owner']
  });
  const payload = verifyToken(token);

  assert.equal(payload.sid, 'session-2');
  assert.deepEqual(payload.entitlements, ['reader', 'owner']);
});

test('discord bridge token round trips with non-email sub', () => {
  process.env.SESSION_SECRET = 'test-secret';
  const sub = 'discord:0123456789abcdef0123456789abcdef';
  const { token, sessionId, expiresAt } = createSessionTokenForSub(sub, 'session-d1', {
    entitlements: ['reader']
  });
  assert.equal(sessionId, 'session-d1');
  assert.ok(expiresAt > Math.floor(Date.now() / 1000));

  const payload = verifyToken(token);
  assert.equal(payload.sid, 'session-d1');
  assert.equal(payload.sub, sub);
  assert.deepEqual(payload.entitlements, ['reader']);
  assert.equal(verifyToken(`${token}x`), null);
});

test('createSessionTokenForSub rejects empty sub', () => {
  process.env.SESSION_SECRET = 'test-secret';
  assert.throws(() => createSessionTokenForSub(''), /non-empty string/);
  assert.throws(() => createSessionTokenForSub(null), /non-empty string/);
});

test('conversation mode entitlements unlock the expected modes', () => {
  const priorOwnerEmails = process.env.THINGY_OWNER_EMAILS;
  const priorOwnerHashes = process.env.THINGY_OWNER_EMAIL_HASHES;
  process.env.THINGY_OWNER_EMAILS = 'jamie@thingelstad.com';
  delete process.env.THINGY_OWNER_EMAIL_HASHES;

  try {
    assert.equal(normalizeConversationMode('Thought Partner'), 'thought_partner');
    assert.equal(isOwnerEmail('jamie@thingelstad.com'), true);

    const readerEntitlements = entitlementsForSubscriber({
      email: 'reader@example.com',
      subscriber: { type: 'regular', tags: [] },
      status: 'regular'
    });
    assert.deepEqual(readerEntitlements, ['reader']);
    assert.equal(canUseConversationMode('thought_partner', readerEntitlements), false);

    const supportingEntitlements = entitlementsForSubscriber({
      email: 'supporter@example.com',
      subscriber: { type: 'premium', tags: [] },
      status: 'premium'
    });
    assert.ok(supportingEntitlements.includes('supporting_member'));
    assert.equal(canUseConversationMode('research_guide', supportingEntitlements), true);
    assert.equal(canUseConversationMode('thought_partner', supportingEntitlements), false);

    const trustedEntitlements = entitlementsForSubscriber({
      email: 'family@example.com',
      subscriber: { type: 'regular', tags: [{ name: 'thingy-family' }] },
      status: 'regular'
    });
    assert.ok(trustedEntitlements.includes('trusted_circle'));

    const ownerEntitlements = entitlementsForSubscriber({
      email: 'jamie@thingelstad.com',
      subscriber: { type: 'regular', tags: [] },
      status: 'regular'
    });
    assert.ok(ownerEntitlements.includes('owner'));
    assert.ok(ownerEntitlements.includes('supporting_member'));
    assert.ok(ownerEntitlements.includes('trusted_circle'));
    assert.equal(canUseConversationMode('thought_partner', ownerEntitlements), true);
    assert.deepEqual(
      availableConversationModes(ownerEntitlements).map((mode) => mode.id),
      ['thingy', 'research_guide', 'thought_partner', 'trusted_circle']
    );
  } finally {
    if (priorOwnerEmails === undefined) delete process.env.THINGY_OWNER_EMAILS;
    else process.env.THINGY_OWNER_EMAILS = priorOwnerEmails;
    if (priorOwnerHashes === undefined) delete process.env.THINGY_OWNER_EMAIL_HASHES;
    else process.env.THINGY_OWNER_EMAIL_HASHES = priorOwnerHashes;
  }
});

test('authProfile returns returning=false for first-time users', () => {
  assert.deepEqual(authProfile(null), { returning: false });
});

test('authProfile reflects turn_count and surfaces recent topics', () => {
  const memory = {
    first_seen_at: '2026-01-01T00:00:00Z',
    last_seen_at: '2026-04-01T00:00:00Z',
    preferred_name: 'Jamie',
    turn_count: 7,
    current_session_questions: [
      { ts: '2026-04-01T00:00:00Z', question: 'What about RSS?' },
      { ts: '2026-04-01T00:01:00Z', question: 'Did Jamie mention Atom?' }
    ],
    synthesized_history: [
      { started_at: '2026-03-01', ended_at: '2026-03-01', summary: 'RSS week.', turn_count: 3 },
      { started_at: '2026-03-15', ended_at: '2026-03-15', summary: 'Indie web week.', turn_count: 4 }
    ]
  };
  const profile = authProfile(memory);
  assert.equal(profile.returning, true);
  assert.equal(profile.turn_count, 7);
  assert.equal(profile.preferred_name, 'Jamie');
  assert.equal(profile.current_session_questions.length, 2);
  assert.equal(profile.prior_session_summaries.length, 2);
  assert.equal(profile.prior_session_summaries[1].summary, 'Indie web week.');
});

test('authProfile caps recent topics at 5 + 3', () => {
  const memory = {
    turn_count: 50,
    current_session_questions: Array.from({ length: 12 }, (_, i) => ({ ts: '', question: `q${i}` })),
    synthesized_history: Array.from({ length: 8 }, (_, i) => ({
      summary: `s${i}`, started_at: '', ended_at: '', turn_count: 1
    }))
  };
  const profile = authProfile(memory);
  assert.equal(profile.current_session_questions.length, 5);
  assert.equal(profile.prior_session_summaries.length, 3);
  // Most recent kept.
  assert.equal(profile.current_session_questions[4].question, 'q11');
  assert.equal(profile.prior_session_summaries[2].summary, 's7');
});

test('memoryContextBlock returns empty string when nothing useful', () => {
  assert.equal(memoryContextBlock(null), '');
  assert.equal(memoryContextBlock({}), '');
  assert.equal(memoryContextBlock({ synthesized_history: [], current_session_questions: [] }), '');
});

test('memoryContextBlock formats prior summaries and current questions', () => {
  const block = memoryContextBlock({
    synthesized_history: [
      { summary: 'RSS exploration.', ended_at: '2026-03-01T00:00:00Z' }
    ],
    current_session_questions: [
      { question: 'What did Jamie say about Atom?' }
    ]
  });
  assert.match(block, /past sessions/);
  assert.match(block, /RSS exploration\./);
  assert.match(block, /\(2026-03-01\)/);
  assert.match(block, /Earlier in this same session/);
  assert.match(block, /Atom\?/);
});

test('memory helpers normalize and dedupe explicit reader facts', () => {
  assert.deepEqual(
    normalizeMemoryFact({ category: 'name', value: ' Jamie  Thingelstad ' }),
    { category: 'preferred_name', value: 'Jamie Thingelstad', source: '' }
  );
  assert.equal(normalizeMemoryFact({ category: 'private', value: 'secret' }), null);

  const facts = mergeRememberedFacts([
    { category: 'interest', value: 'RSS', remembered_at: '2026-01-01T00:00:00Z' }
  ], { category: 'interest', value: 'rss', source: 'reader said so' }, '2026-02-01T00:00:00Z');
  assert.equal(facts.length, 1);
  assert.equal(facts[0].value, 'rss');
  assert.equal(facts[0].source, 'reader said so');
  assert.equal(facts[0].remembered_at, '2026-02-01T00:00:00Z');
});

test('authProfile and memoryContextBlock surface durable reader memory', () => {
  const memory = {
    turn_count: 4,
    remembered_facts: [
      { category: 'interest', value: 'IndieWeb', remembered_at: '2026-01-01T00:00:00Z' },
      { category: 'preference', value: 'prefers concise answers', remembered_at: '2026-01-02T00:00:00Z' }
    ],
    interests: ['IndieWeb']
  };
  const profile = authProfile(memory);
  assert.equal(profile.remembered_facts.length, 2);
  assert.deepEqual(profile.interests, ['IndieWeb']);

  const block = memoryContextBlock(memory);
  assert.match(block, /Remembered reader details/);
  assert.match(block, /interest: IndieWeb/);
  assert.match(block, /Reader interests/);
});

test('email normalization is stable', () => {
  assert.equal(normalizeEmail(' Reader@Example.com '), 'reader@example.com');
  assert.equal(emailHash('Reader@Example.com'), emailHash('reader@example.com'));
});

test('magic link tokens are URL-safe and hashed for storage', () => {
  const token = createMagicToken();
  assert.equal(validMagicToken(token), token);
  assert.match(magicTokenHash(token), /^[a-f0-9]{64}$/);
  assert.equal(validMagicToken('not a token!'), '');
});

test('magic link builder adds login_token without leaking extra state', () => {
  const token = createMagicToken();
  const url = new URL(buildMagicLink(token, 'https://thingy.thingelstad.com/?prompt=hello'));
  assert.equal(url.origin, 'https://thingy.thingelstad.com');
  assert.equal(url.searchParams.get('prompt'), 'hello');
  assert.equal(url.searchParams.get('login_token'), token);
});

test('magic link base lands on signin with the app return path preserved', () => {
  const original = process.env.THINGY_MAGIC_LINK_BASE_URL;
  process.env.THINGY_MAGIC_LINK_BASE_URL = 'https://thingy.example/';
  try {
    const token = createMagicToken();
    const base = magicLinkBaseWithReturnPath('/dispatch/?from=https%3A%2F%2Fweekly.example%2Fissue');
    const url = new URL(buildMagicLink(token, base));
    assert.equal(url.origin, 'https://thingy.example');
    assert.equal(url.pathname, '/signin/');
    assert.equal(url.searchParams.get('return'), '/dispatch/?from=https%3A%2F%2Fweekly.example%2Fissue');
    assert.equal(url.searchParams.get('login_token'), token);
  } finally {
    if (original === undefined) delete process.env.THINGY_MAGIC_LINK_BASE_URL;
    else process.env.THINGY_MAGIC_LINK_BASE_URL = original;
  }
});

test('magic link email text includes expiration and fallback URL', () => {
  const text = magicLinkEmailText({ magicLink: 'https://thingy.example/login?token=abc', expiresMinutes: 15 });
  assert.match(text, /Thingy is ready/);
  assert.match(text, /https:\/\/thingy\.example\/login\?token=abc/);
  assert.match(text, /expires in 15 minutes/);
});

test('magic link email copy reflects reader context', () => {
  const text = magicLinkEmailText({
    magicLink: 'https://thingy.example/login?token=abc',
    expiresMinutes: 15,
    context: { preferred_name: 'Jamie', returning: true, turn_count: 4, subscriber_status: 'premium' }
  });
  assert.match(text, /Hi Jamie/);
  assert.match(text, /archive thread is waiting/);
  assert.match(text, /Supporting Member/);

  const html = magicLinkEmailHtml({
    magicLink: 'https://thingy.example/login?token=abc&x=<bad>',
    expiresMinutes: 15,
    context: { preferred_name: 'Jamie', returning: true, turn_count: 4 },
    imageUrl: 'https://thingy.example/img/thingy.png'
  });
  assert.match(html, /Hi Jamie/);
  assert.match(html, /Open Thingy/);
  assert.match(html, /thingy\.png/);
  assert.doesNotMatch(html, /<bad>/);
});

test('JMAP method errors are treated as hard send failures', () => {
  assert.throws(
    () => requireMethodResponse([['error', { type: 'accountReadOnly' }, 'email']], 'Email/set', 'email'),
    /accountReadOnly/
  );
  assert.deepEqual(
    requireMethodResponse([['Email/set', { created: { draft: { id: 'm1' } } }, 'email']], 'Email/set', 'email'),
    { created: { draft: { id: 'm1' } } }
  );
});

test('JMAP magic link payload creates a draft and submits it through Sent', () => {
  const calls = buildMagicLinkJmapCalls({
    context: {
      mailAccountId: 'mail-account',
      submissionAccountId: 'submission-account',
      identityId: 'identity-1',
      draftMailboxId: 'drafts-1',
      sentMailboxId: 'sent-1'
    },
    fromEmail: 'thingy@example.com',
    fromName: 'Thingy',
    to: 'reader@example.com',
    text: 'hello',
    html: '<p>hello</p>'
  });

  const emailSet = calls[0][1];
  assert.equal(calls[0][0], 'Email/set');
  assert.deepEqual(emailSet.create.draft.mailboxIds, { 'drafts-1': true });
  assert.deepEqual(emailSet.create.draft.bodyStructure, {
    type: 'multipart/alternative',
    subParts: [
      { partId: 'text', type: 'text/plain' },
      { partId: 'html', type: 'text/html' }
    ]
  });
  assert.equal(emailSet.create.draft.bodyValues.text.value, 'hello');
  assert.equal(emailSet.create.draft.bodyValues.html.value, '<p>hello</p>');

  const submissionSet = calls[1][1];
  assert.equal(calls[1][0], 'EmailSubmission/set');
  assert.equal(submissionSet.create.send.emailId, '#draft');
  assert.equal(submissionSet.create.send.identityId, 'identity-1');
  assert.deepEqual(submissionSet.create.send.envelope, {
    mailFrom: { email: 'thingy@example.com' },
    rcptTo: [{ email: 'reader@example.com' }]
  });
  assert.deepEqual(submissionSet.onSuccessUpdateEmail['#send'], {
    'mailboxIds/sent-1': true,
    'mailboxIds/drafts-1': null,
    'keywords/$draft': null
  });
});

test('buttondown subscriber status maps active and inactive states', () => {
  assert.equal(subscriberStatus(null), 'not_found');
  assert.equal(subscriberStatus({ type: 'regular' }), 'active');
  assert.equal(subscriberStatus({ type: 'premium' }), 'premium');
  assert.equal(subscriberStatus({ type: 'unactivated' }), 'unconfirmed');
  assert.equal(subscriberStatus({ type: 'regular', unsubscription_date: '2026-01-01' }), 'inactive');
  assert.equal(subscriberStatus({ type: 'disabled' }), 'inactive');
});

test('prompt template renderer substitutes named placeholders', () => {
  assert.equal(renderTemplate('Hello {{ name }} from {{ place }}.', { name: 'Thingy', place: 'the archive' }), 'Hello Thingy from the archive.');
});

test('agent user prompt renders dynamic conversation context', () => {
  const prompt = agentUserPrompt({
    conversation_context: 'User: Tell me more.',
    reader_context: 'Reader preferred name: Jamie',
    question: 'What did the archive say about RSS?'
  });

  assert.match(prompt, /User: Tell me more\./);
  assert.match(prompt, /Reader preferred name: Jamie/);
  assert.match(prompt, /What did the archive say about RSS\?/);
  assert.match(prompt, /Investigate with tools as needed/);
});

test('preflight JSON parser tolerates fenced strict JSON', () => {
  const parsed = parsePreflightJson('```json\n{"action":"rewrite","category":"archive_rewrite"}\n```');
  assert.deepEqual(parsed, { action: 'rewrite', category: 'archive_rewrite' });
  assert.equal(parsePreflightJson('not json'), null);
});

test('preflight normalizer keeps rewrites/direct answers safe and structured', () => {
  const rewrite = normalizePreflightDecision({
    action: 'rewrite',
    category: 'archive_rewrite',
    rewritten_question: 'Pick one archive thread and tell it as a concise story.',
    answer_guidance: 'Keep the playful intent.'
  }, 'Tell me a story.');
  assert.equal(rewrite.action, 'rewrite');
  assert.equal(rewrite.category, 'archive_rewrite');
  assert.equal(rewrite.original_question, 'Tell me a story.');
  assert.match(rewrite.rewritten_question, /archive thread/);

  const badRewrite = normalizePreflightDecision({ action: 'rewrite', category: 'archive_rewrite' }, 'Surprise me.');
  assert.equal(badRewrite.action, 'pass');

  const direct = normalizePreflightDecision({ action: 'direct', category: 'privacy_refusal' }, 'Where does Jamie live?');
  assert.equal(direct.action, 'direct');
  assert.equal(direct.category, 'privacy_refusal');
  assert.match(direct.direct_answer, /public archive/i);

  assert.equal(passThroughPreflight('What did Jamie write about RSS?').action, 'pass');
});

test('preflight prompt allows named-person archive lookups without weakening privacy refusals', () => {
  assert.match(PREFLIGHT_SYSTEM_PROMPT, /Named-person archive lookups are allowed/);
  assert.match(PREFLIGHT_SYSTEM_PROMPT, /Do not refuse merely because the prompt names a private individual/);
  assert.match(PREFLIGHT_SYSTEM_PROMPT, /home address, phone numbers, whereabouts/);
});

test('FAQ search returns authoritative shared FAQ entries', () => {
  const results = searchFaq('How do I unsubscribe?', { replacements: { yearsActive: 10, issueCount: 345 } });

  assert.equal(results[0].question, 'How do I unsubscribe?');
  assert.equal(results[0].url, '/faq/');
  assert.match(results[0].answer_text, /unsubscribe link/);
  assert.equal(renderFaqAnswer('over {{yearsActive}} years and {{issueCount}} issues', { yearsActive: 10, issueCount: 345 }), 'over 10 years and 345 issues');
});

test('feedback helpers accept only expected reactions and request ids', () => {
  assert.equal(normalizeFeedbackReaction('up'), 'up');
  assert.equal(normalizeFeedbackReaction(' DOWN '), 'down');
  assert.equal(normalizeFeedbackReaction('helpful'), '');

  assert.equal(validFeedbackRequestId('63026f16-ef49-456f-b26f-bc76d7d83481'), '63026f16-ef49-456f-b26f-bc76d7d83481');
  assert.equal(validFeedbackRequestId('request:local.test_1'), 'request:local.test_1');
  assert.equal(validFeedbackRequestId('conversation#bad'), '');
  assert.equal(validFeedbackRequestId(''), '');
});

test('Bedrock converse stream reader emits incremental text deltas', async () => {
  const deltas = [];
  const result = await readConverseStream({
    stream: [
      { messageStart: { role: 'assistant' } },
      { contentBlockDelta: { contentBlockIndex: 0, delta: { text: 'First ' } } },
      { contentBlockDelta: { contentBlockIndex: 0, delta: { text: 'second.' } } },
      { messageStop: { stopReason: 'end_turn' } },
      { metadata: { usage: { outputTokens: 3 } } }
    ]
  }, { onTextDelta: (delta) => deltas.push(delta) });

  assert.deepEqual(deltas, ['First ', 'second.']);
  assert.equal(result.text, 'First second.');
  assert.deepEqual(result.message.content, [{ text: 'First second.' }]);
  assert.equal(result.stopReason, 'end_turn');
  assert.equal(result.usage.outputTokens, 3);
});

test('Bedrock converse stream reader reconstructs streamed tool use input', async () => {
  const result = await readConverseStream({
    stream: [
      { messageStart: { role: 'assistant' } },
      {
        contentBlockStart: {
          contentBlockIndex: 0,
          start: { toolUse: { toolUseId: 'tool-1', name: 'search_archive' } }
        }
      },
      { contentBlockDelta: { contentBlockIndex: 0, delta: { toolUse: { input: '{"query":"' } } } },
      { contentBlockDelta: { contentBlockIndex: 0, delta: { toolUse: { input: 'RSS"}' } } } },
      { messageStop: { stopReason: 'tool_use' } }
    ]
  });

  assert.deepEqual(result.message.content, [{
    toolUse: { toolUseId: 'tool-1', name: 'search_archive', input: { query: 'RSS' } }
  }]);
  assert.equal(result.stopReason, 'tool_use');
});
