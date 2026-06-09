import assert from 'node:assert/strict';
import test from 'node:test';
import {
  conversationTtlSeconds,
  dispatchDraftTtlSeconds,
  dispatchHistoryTtlSeconds
} from '../shared/retention.mjs';

test('Thingy retention windows default to the agreed shorter durations', () => {
  const now = '2026-06-08T12:00:00.000Z';
  const epoch = Math.floor(Date.parse(now) / 1000);
  const day = 24 * 60 * 60;

  assert.equal(conversationTtlSeconds(now), epoch + (45 * day));
  assert.equal(dispatchDraftTtlSeconds(now), epoch + (7 * day));
  assert.equal(dispatchHistoryTtlSeconds(now), epoch + (90 * day));
});
