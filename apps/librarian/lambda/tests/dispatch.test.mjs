import assert from 'node:assert/strict';
import test from 'node:test';
import { dispatchAvailabilityFromRows, dispatchForClient } from '../shared/dispatch-store.mjs';
import {
  dispatchHtmlEmail,
  dispatchSubject,
  dispatchTextEmail,
  dispatchTemplateTestPayload,
  parseDispatchJson,
  selectDispatchSources
} from '../shared/dispatch-generator.mjs';

test('dispatch availability enforces active and rolling 24-hour limits', () => {
  const nowSeconds = Math.floor(Date.parse('2026-06-08T12:00:00Z') / 1000);
  assert.deepEqual(
    dispatchAvailabilityFromRows([{ id: 'd1', status: 'queued' }], { nowSeconds }),
    {
      allowed: false,
      reason: 'active',
      message: 'A Dispatch is already being prepared. Wait for that one to finish before starting another.',
      active_dispatch_id: 'd1'
    }
  );

  const limited = dispatchAvailabilityFromRows([
    { id: 'd2', status: 'sent', sent_at: '2026-06-08T00:00:00Z' }
  ], { nowSeconds });
  assert.equal(limited.allowed, false);
  assert.equal(limited.reason, 'cooldown');
  assert.equal(limited.retry_after_seconds, 43200);

  assert.equal(dispatchAvailabilityFromRows([
    { id: 'd2', status: 'sent', sent_at: '2026-06-08T00:00:00Z' }
  ], { nowSeconds, owner: true }).allowed, true);

  assert.equal(dispatchAvailabilityFromRows([
    { id: 'd3', status: 'ready' }
  ], { nowSeconds }).allowed, true);
});

test('dispatchForClient includes draft state but omits generated content', () => {
  const client = dispatchForClient({
    pk: { S: 'user#abc' },
    sk: { S: 'dispatch#2026-06-08T12:00:00.000Z#d1' },
    dispatch_id: { S: 'd1' },
    status: { S: 'ready' },
    prompt: { S: 'Explore the open web' },
    direction: { S: 'Write about ownership and RSS.' },
    clarification_question: { S: 'What angle?' },
    clarification_answer: { S: 'The personal web.' },
    title: { S: 'Open web Dispatch' },
    template_test: { BOOL: true },
    messages: {
      L: [{
        M: {
          role: { S: 'user' },
          text: { S: 'Open web please' },
          time: { S: '2026-06-08T12:00:00.000Z' }
        }
      }]
    },
    content_html: { S: '<p>private</p>' },
    content_text: { S: 'private' }
  });
  assert.equal(client.id, 'd1');
  assert.equal(client.status, 'ready');
  assert.equal(client.prompt, 'Explore the open web');
  assert.equal(client.template_test, true);
  assert.equal(client.messages.length, 1);
  assert.equal(client.content_html, undefined);
  assert.equal(client.content_text, undefined);
});

test('dispatch template test payload renders placeholder content with real source links', () => {
  const sources = [{
    id: 'S1',
    label: 'WT10',
    title: 'Open web',
    url: 'https://weekly.example/10',
    source_kind: 'weekly_thing',
    publish_date: '2026-01-01'
  }];
  const payload = dispatchTemplateTestPayload({
    prompt: 'Explore RSS',
    direction: 'Template-test the Dispatch email around RSS and ownership.'
  }, sources);
  const html = dispatchHtmlEmail(payload, sources);

  assert.match(payload.subject, /^Thingy Dispatch - Template Test:/);
  assert.match(payload.intro, /intentionally does not contain generated long-form Dispatch writing/);
  assert.match(html, /Thingy Dispatch/);
  assert.match(html, /Template Test:/);
  assert.match(html, /https:\/\/weekly\.example\/10/);
});

test('selectDispatchSources scores archive chunks and dedupes by url', () => {
  const chunks = [
    {
      source_kind: 'weekly_thing',
      issue_number: 10,
      title: 'Open web',
      url: 'https://weekly.example/10',
      text: 'RSS and open web ownership matter.'
    },
    {
      source_kind: 'blog',
      title: 'Owning your notes',
      url: 'https://blog.example/notes',
      text: 'Personal ownership and automation with notes.'
    },
    {
      source_kind: 'blog',
      title: 'Duplicate',
      url: 'https://blog.example/notes',
      text: 'ownership ownership ownership'
    }
  ];
  const selected = selectDispatchSources(chunks, 'open web ownership automation', 3);
  assert.equal(selected.length, 2);
  assert.equal(selected[0].id, 'S1');
  assert.equal(selected[0].label, 'WT10');
  assert.ok(selected.some((source) => source.source_kind === 'blog'));
});

test('parseDispatchJson handles fenced JSON', () => {
  assert.deepEqual(parseDispatchJson('```json\n{"title":"Dispatch"}\n```'), { title: 'Dispatch' });
});

test('dispatchHtmlEmail renders request provenance authorship boundary and linked sources', () => {
  const html = dispatchHtmlEmail({
    title: 'Ownership Dispatch',
    preview: 'A short preview.',
    intro: 'Thingy found a thread [S1].',
    sections: [{ heading: 'The thread', body: 'This depends on [S1].' }],
    closing: 'Keep exploring.',
    followups: ['What changed over time?']
  }, [{
    id: 'S1',
    label: 'WT10',
    title: 'Open web',
    url: 'https://weekly.example/10',
    source_kind: 'weekly_thing',
    publish_date: '2026-01-01'
  }], {
    toEmail: 'reader@example.com',
    requestedAt: '2026-06-08T12:00:00.000Z'
  });
  assert.match(html, /Thingy Dispatch/);
  assert.match(html, /requested by reader@example\.com on 2026-06-08 12:00Z/);
  assert.match(html, /Written by Thingy, not Jamie/);
  assert.match(html, /https:\/\/weekly\.example\/10/);
});

test('dispatch email rendering preserves paragraph breaks and normalizes subject prefix', () => {
  const payload = dispatchTemplateTestPayload({
    prompt: 'Explore RSS',
    direction: 'RSS and ownership'
  }, []);
  const html = dispatchHtmlEmail({
    ...payload,
    subject: 'A custom generated title',
    intro: 'First paragraph has useful setup.\n\nSecond paragraph should not be eaten.',
    sections: [{
      heading: 'The thread',
      body: 'Sentence one. Sentence two should not run into sentence three. Sentence three keeps breathing room.'
    }]
  }, [], {
    toEmail: 'reader@example.com',
    requestedAt: '2026-06-08T12:00:00.000Z'
  });
  const text = dispatchTextEmail(payload, [], {
    toEmail: 'reader@example.com',
    requestedAt: '2026-06-08T12:00:00.000Z'
  });

  assert.equal(payload.subject, 'Thingy Dispatch - Template Test: RSS and ownership');
  assert.equal(dispatchSubject('Dispatch: Old shape title'), 'Thingy Dispatch - Old shape title');
  assert.match(html, /First paragraph has useful setup\./);
  assert.match(html, /Second paragraph should not be eaten\./);
  assert.match(text, /This Thingy Dispatch was requested by reader@example\.com on 2026-06-08 12:00Z\./);
});
