import assert from 'node:assert/strict';
import test from 'node:test';
import { dispatchAvailabilityFromRows, dispatchForClient } from '../shared/dispatch-store.mjs';
import { discordDispatchCard } from '../shared/dispatch-worker.mjs';
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

  assert.equal(payload.subject, 'Thingy Dispatch — Template-test the Dispatch email around RSS and ownership.');
  assert.equal(payload.title, 'Template-test the Dispatch email around RSS and ownership.');
  assert.match(payload.intro, /intentionally does not contain generated long-form Dispatch writing/);
  assert.match(html, /Thingy Dispatch/);
  assert.match(html, /template test/i);
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
    intro: 'Thingy found a *thread* [S1].',
    sections: [{ heading: 'The thread', body: 'This depends on **ownership** and [S1].' }],
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
    requestedAt: '2026-06-08T12:00:00.000Z',
    requestSummary: 'Explore ownership and the open web from the archive.'
  });
  assert.match(html, /Thingy Dispatch/);
  assert.match(html, /requested by reader@example\.com on 2026-06-08 12:00Z/);
  assert.match(html, /<strong[^>]*>Request<\/strong>Explore ownership and the open web from the archive\./);
  assert.doesNotMatch(html, />Requested</);
  assert.doesNotMatch(html, />Attribution</);
  assert.match(html, /<em>thread<\/em>/);
  assert.match(html, /<strong>ownership<\/strong>/);
  assert.match(html, /href="https:\/\/thingy\.thingelstad\.com\/"/);
  assert.match(html, /Written by Thingy, not Jamie/);
  assert.match(html, /https:\/\/weekly\.example\/10/);
  assert.doesNotMatch(html, /<strong>S1<\/strong>/);
  assert.doesNotMatch(html, /\(2026-01-01\)/);
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
    requestedAt: '2026-06-08T12:00:00.000Z',
    requestSummary: 'RSS and ownership'
  });

  assert.equal(payload.subject, 'Thingy Dispatch — RSS and ownership');
  assert.equal(dispatchSubject('Dispatch: Old shape title'), 'Thingy Dispatch — Old shape title');
  assert.match(html, /display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;color:transparent;line-height:1px;font-size:1px;">A low-cost Thingy Dispatch template test/);
  assert.match(html, /First paragraph has useful setup\./);
  assert.match(html, /Second paragraph should not be eaten\./);
  assert.match(text, /This Thingy Dispatch was requested by reader@example\.com on 2026-06-08 12:00Z\./);
  assert.match(text, /Request: RSS and ownership/);
  assert.match(text, /Prepared by Thingy \(https:\/\/thingy\.thingelstad\.com\/\)/);
});

test('dispatch renderer turns source refs and followups into normal links', () => {
  const html = dispatchHtmlEmail({
    title: 'Home Automation',
    preview: 'A dispatch about coordination.',
    intro: 'In Weekly Thing 336, Jamie draws a privacy line around smart devices. [S1]\n\nThe blog post "My GTD Structure" maps routine work into a system. [S2]',
    sections: [{
      heading: 'Thread',
      body: 'This leans on [S1] when no source title is nearby.'
    }],
    closing: '',
    followups: ['How does this connect to OmniFocus?']
  }, [{
    id: 'S1',
    label: 'WT336',
    title: 'Weekly Thing 336 / Culture, Retention, Transmission',
    url: '/archive/336/',
    source_kind: 'weekly_thing',
    publish_date: '2026-01-01'
  }, {
    id: 'S2',
    label: 'Blog',
    title: 'My GTD Structure',
    url: 'https://www.thingelstad.com/2024/09/02/my-gtd-structure.html',
    source_kind: 'blog',
    publish_date: '2024-09-02'
  }]);

  assert.match(html, /<a href="https:\/\/weekly\.thingelstad\.com\/archive\/336\/"[^>]*>Weekly Thing 336<\/a>/);
  assert.match(html, /<a href="https:\/\/www\.thingelstad\.com\/2024\/09\/02\/my-gtd-structure\.html"[^>]*>My GTD Structure<\/a>/);
  assert.match(html, /href="https:\/\/thingy\.thingelstad\.com\/chat\/\?prompt=How\+does\+this\+connect\+to\+OmniFocus%3F"/);
  assert.doesNotMatch(html, /<strong>S1<\/strong> WT336/);
  assert.doesNotMatch(html, /\(2024-09-02\)/);
});

test('dispatch Discord card summarizes sent dispatch without body content', () => {
  const card = discordDispatchCard({
    dispatch: {
      id: 'dispatch-1',
      to_email: 'reader@example.com',
      direction: 'Explore home automation as coordination infrastructure.',
      template_test: true
    },
    result: {
      subject: 'Thingy Dispatch — Home Automation as Coordination Infrastructure',
      preview: 'How systems thinking reduces friction in family routines.',
      model: 'template-test',
      usage: { inputTokens: 12, outputTokens: 34 },
      sources: [
        { label: 'WT336', title: 'Weekly Thing 336 / Culture, Retention, Transmission' },
        { label: 'Blog', title: 'My GTD Structure' }
      ],
      text: 'full dispatch body should not appear'
    }
  });

  assert.match(card, /Thingy Dispatch · `dispatch-1`/);
  assert.match(card, /template test/);
  assert.match(card, /reader@example\.com/);
  assert.match(card, /Thingy Dispatch — Home Automation/);
  assert.match(card, /WT336 · Weekly Thing 336/);
  assert.match(card, /Tokens:\*\* in 12 \/ out 34/);
  assert.doesNotMatch(card, /full dispatch body/);
  assert.ok(card.length <= 1900);
});
