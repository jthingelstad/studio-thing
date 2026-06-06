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

test('removes leading tool-process narration from answers', () => {
  const answer = 'The Switzerland hike is compelling, but let me pull up the full text first.\n\nI have everything I need. Let me tell it.\n\n---\n\nHere is the story from the archive.';

  const out = sanitizeAnswerProse(answer);

  assert.equal(out, 'Here is the story from the archive.');
});

test('removes leading process narration without paragraph breaks', () => {
  const answer = "I've found it — a perfect post. Let me pull the full context.Here's a story from the archive.";

  const out = sanitizeAnswerProse(answer);

  assert.equal(out, "Here's a story from the archive.");
});

test('removes got-what-i-need process narration', () => {
  const answer = "I've got what I need. Here's a useful answer from an old post.";

  const out = sanitizeAnswerProse(answer);

  assert.equal(out, "Here's a useful answer from an old post.");
});
