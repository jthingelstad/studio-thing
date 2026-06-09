import assert from 'node:assert/strict';
import test from 'node:test';
import { collectToolCitations } from '../shared/archive-tools.mjs';

test('archive tool citations are exported for chat runtime', () => {
  const citations = collectToolCitations([
    {
      results: [
        {
          issue_number: 350,
          source_kind: 'weekly_thing',
          subject: 'Weekly Thing 350',
          section: 'Featured',
          url: '/archive/350/'
        }
      ]
    },
    {
      source: {
        source_kind: 'blog',
        subject: 'A blog post',
        url: 'https://www.thingelstad.com/example/'
      }
    }
  ]);

  assert.equal(citations.length, 2);
  assert.equal(citations[0].issue_number, 350);
  assert.equal(citations[1].source_kind, 'blog');
});

test('chat runtime imports with the Lambda response-stream shim', async () => {
  globalThis.awslambda = {
    streamifyResponse: (handler) => handler
  };

  const runtime = await import('../chat/runtime.mjs');

  assert.equal(typeof runtime.handler, 'function');
});
