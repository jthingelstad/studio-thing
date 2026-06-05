import assert from 'node:assert/strict';
import test from 'node:test';
import { sanitizeAnswerProse } from '../shared/answer-sanitizer.mjs';

test('removes archive URL sentence from latest-content prose', () => {
  const answer = 'Weekly Thing — WT350, published May 30, 2026. The archive URL is `/archive/350/`.\n\nBlog — newest post.';

  const out = sanitizeAnswerProse(answer);

  assert.equal(out, 'Weekly Thing — WT350, published May 30, 2026.\n\nBlog — newest post.');
  assert.doesNotMatch(out, /\/archive\/350/);
});

test('replaces raw Weekly Thing archive links with WT citations', () => {
  const answer = 'See https://weekly.thingelstad.com/archive/350/ and /archive/349/ for context.';

  const out = sanitizeAnswerProse(answer);

  assert.equal(out, 'See WT350 and WT349 for context.');
});

test('strips other raw urls without touching markdown links', () => {
  const answer = 'Read [Thingy](https://thingy.thingelstad.com/) but not https://example.com/raw.';

  const out = sanitizeAnswerProse(answer);

  assert.equal(out, 'Read [Thingy](https://thingy.thingelstad.com/) but not');
});
