import assert from 'node:assert/strict';
import test from 'node:test';
import { DEFAULT_SCOPE, SCOPES, normalizeScope, scopeKinds, scopePromptLine } from '../shared/scope.mjs';

test('normalizeScope defaults to weekly_thing for empty/unknown input', () => {
  assert.equal(normalizeScope(undefined), 'weekly_thing');
  assert.equal(normalizeScope(''), 'weekly_thing');
  assert.equal(normalizeScope(null), 'weekly_thing');
  assert.equal(normalizeScope('nonsense'), 'weekly_thing');
  assert.equal(DEFAULT_SCOPE, 'weekly_thing');
});

test('normalizeScope canonicalizes source scopes and common aliases', () => {
  assert.equal(normalizeScope('weekly_thing'), 'weekly_thing');
  assert.equal(normalizeScope('Weekly Thing'), 'weekly_thing');
  assert.equal(normalizeScope('weekly-thing'), 'weekly_thing');
  assert.equal(normalizeScope('WT'), 'weekly_thing');
  assert.equal(normalizeScope('issues'), 'weekly_thing');
  assert.equal(normalizeScope('blog'), 'blog');
  assert.equal(normalizeScope('BLOG'), 'blog');
  assert.equal(normalizeScope('podcast'), 'podcast');
  assert.equal(normalizeScope('Another Thing'), 'podcast');
  assert.equal(normalizeScope('both'), 'both');
  assert.equal(normalizeScope('weekly_thing,podcast'), 'weekly_thing_podcast');
  assert.equal(normalizeScope('blog|podcast'), 'blog_podcast');
  assert.equal(normalizeScope('newsletter + another'), 'weekly_thing_podcast');
  assert.equal(normalizeScope('blog,unknown'), 'blog');
  assert.equal(normalizeScope('all'), 'all');
  for (const scope of SCOPES) assert.equal(normalizeScope(scope), scope);
});

test('scopeKinds maps scope to the corpora it scans, WT first for mixed scopes', () => {
  assert.deepEqual(scopeKinds('weekly_thing'), ['weekly_thing']);
  assert.deepEqual(scopeKinds('blog'), ['blog']);
  assert.deepEqual(scopeKinds('podcast'), ['podcast']);
  assert.deepEqual(scopeKinds('both'), ['weekly_thing', 'blog']);
  assert.deepEqual(scopeKinds('weekly_thing_podcast'), ['weekly_thing', 'podcast']);
  assert.deepEqual(scopeKinds('blog_podcast'), ['blog', 'podcast']);
  assert.deepEqual(scopeKinds('all'), ['weekly_thing', 'blog', 'podcast']);
  // Unknown input falls back to the default scope's kinds.
  assert.deepEqual(scopeKinds('garbage'), ['weekly_thing']);
});

test('scopePromptLine names the active corpus distinctly per scope', () => {
  const wt = scopePromptLine('weekly_thing');
  const blog = scopePromptLine('blog');
  const podcast = scopePromptLine('podcast');
  const both = scopePromptLine('both');
  const wtPodcast = scopePromptLine('weekly_thing_podcast');
  const blogPodcast = scopePromptLine('blog_podcast');
  const all = scopePromptLine('all');
  assert.match(wt, /Weekly Thing/);
  assert.match(blog, /blog only/i);
  assert.match(podcast, /podcast only/i);
  assert.match(both, /also_in_issues/);
  assert.match(wtPodcast, /not Jamie's blog/);
  assert.match(blogPodcast, /not the Weekly Thing/);
  assert.match(all, /Another Thing/);
  // Each scope produces a distinct instruction.
  assert.notEqual(wt, blog);
  assert.notEqual(blog, podcast);
  assert.notEqual(blog, both);
  assert.notEqual(wt, both);
  assert.notEqual(wtPodcast, both);
  assert.notEqual(blogPodcast, wtPodcast);
  assert.notEqual(both, all);
});
