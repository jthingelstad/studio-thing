import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceKeyFromChunk, sourceKeyFromLink, sourceRecordKey } from '../dist/shared/archive-tools.mjs';

test('blog records, chunks, and links use the canonical URL across corpus layers', () => {
  const url = 'https://www.thingelstad.com/2013/03/13/google-reader-rip.html';

  const recordKey = sourceRecordKey({ source_kind: 'blog', microblog_id: '12345', url });

  assert.equal(sourceKeyFromChunk({ source_kind: 'blog', url }), recordKey);
  assert.equal(sourceKeyFromLink({ corpus_kind: 'blog', microblog_id: '12345', post_url: url }), recordKey);
});

test('podcast records, chunks, and links use the canonical URL across corpus layers', () => {
  const url = 'https://another.thingelstad.com/episodes/archive-thinking/';

  const recordKey = sourceRecordKey({ source_kind: 'podcast', episode_number: 42, url });

  assert.equal(sourceKeyFromChunk({ source_kind: 'podcast', url }), recordKey);
  assert.equal(sourceKeyFromLink({ corpus_kind: 'podcast', episode_number: 42, episode_url: url }), recordKey);
});

test('provider identifiers remain a fallback when a canonical URL is absent', () => {
  assert.equal(sourceRecordKey({ source_kind: 'blog', microblog_id: '12345' }), 'blog\0' + '12345');
  assert.equal(sourceKeyFromChunk({ source_kind: 'podcast', episode_number: 42 }), 'podcast\0' + '42');
});
