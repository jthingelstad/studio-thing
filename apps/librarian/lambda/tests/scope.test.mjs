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

test('normalizeScope canonicalizes the three scopes and common aliases', () => {
  assert.equal(normalizeScope('weekly_thing'), 'weekly_thing');
  assert.equal(normalizeScope('Weekly Thing'), 'weekly_thing');
  assert.equal(normalizeScope('weekly-thing'), 'weekly_thing');
  assert.equal(normalizeScope('WT'), 'weekly_thing');
  assert.equal(normalizeScope('issues'), 'weekly_thing');
  assert.equal(normalizeScope('blog'), 'blog');
  assert.equal(normalizeScope('BLOG'), 'blog');
  assert.equal(normalizeScope('both'), 'both');
  assert.equal(normalizeScope('all'), 'both');
  for (const scope of SCOPES) assert.equal(normalizeScope(scope), scope);
});

test('scopeKinds maps scope to the corpora it scans, WT first for both', () => {
  assert.deepEqual(scopeKinds('weekly_thing'), ['weekly_thing']);
  assert.deepEqual(scopeKinds('blog'), ['blog']);
  assert.deepEqual(scopeKinds('both'), ['weekly_thing', 'blog']);
  // Unknown input falls back to the default scope's kinds.
  assert.deepEqual(scopeKinds('garbage'), ['weekly_thing']);
});

test('scopePromptLine names the active corpus distinctly per scope', () => {
  const wt = scopePromptLine('weekly_thing');
  const blog = scopePromptLine('blog');
  const both = scopePromptLine('both');
  assert.match(wt, /Weekly Thing/);
  assert.match(blog, /blog only/i);
  assert.match(both, /also_in_issues/);
  // Each scope produces a distinct instruction.
  assert.notEqual(wt, blog);
  assert.notEqual(blog, both);
  assert.notEqual(wt, both);
});
