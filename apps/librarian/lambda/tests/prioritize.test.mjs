import assert from 'node:assert/strict';
import test from 'node:test';
import { prioritizeCitationsForAnswer } from '../shared/citations.mjs';

const c = (issueNumber, section = 'Issue') => ({
  issue_number: String(issueNumber),
  subject: `Weekly Thing ${issueNumber}`,
  publish_date: '2024-01-01T00:00:00Z',
  section,
  url: `/archive/${issueNumber}/`
});

test('drops citations whose issue numbers do not appear in the answer body', () => {
  const citations = [c(228), c(332), c(345), c(130), c(159), c(9)];
  const answer = 'See WT228, WT332, and WT345 — those are the load-bearing ones.';
  const out = prioritizeCitationsForAnswer(citations, answer);
  assert.deepEqual(out.map((x) => x.issue_number), ['228', '332', '345']);
});

test('preserves first-mention order regardless of original list order', () => {
  const citations = [c(332), c(228), c(347), c(345)];
  const answer = 'WT347 came up first, then WT228 and WT332. WT345 ties it together.';
  const out = prioritizeCitationsForAnswer(citations, answer);
  assert.deepEqual(out.map((x) => x.issue_number), ['347', '228', '332', '345']);
});

test('dedupes when one issue surfaced under two sections', () => {
  // Mirrors conv #16 where WT332 came back twice with different sections.
  const citations = [
    c(332, 'A fad piece'),
    c(332, 'Git AI is now 1.0'),
    c(159, 'VP of Engineering')
  ];
  const answer = 'WT332 and WT159 both apply.';
  const out = prioritizeCitationsForAnswer(citations, answer);
  assert.equal(out.length, 2);
  assert.deepEqual(out.map((x) => x.issue_number), ['332', '159']);
  // First section seen wins for the deduped citation.
  assert.equal(out[0].section, 'A fad piece');
});

test('returns everything when the answer mentions no issue numbers', () => {
  // FAQ-only answers, out-of-scope refusals, etc. shouldn't lose the
  // "we looked at these" footer even though nothing is inline-cited.
  const citations = [c(100), c(101)];
  const answer = 'You can unsubscribe from the link in the email footer.';
  const out = prioritizeCitationsForAnswer(citations, answer);
  assert.equal(out.length, 2);
});

test('keeps podcast citations because they are cited by title/link', () => {
  const podcast = {
    issue_number: null,
    source_kind: 'podcast',
    subject: 'How do you start a podcast?',
    publish_date: '2025-10-05',
    section: 'Transcript',
    url: 'https://another.thingelstad.com/2025/10/05/how-do-you-start-a.html'
  };
  const out = prioritizeCitationsForAnswer([c(228), podcast], 'WT228 is a newsletter citation.');
  assert.deepEqual(out.map((x) => x.source_kind || 'chunk'), ['chunk', 'podcast']);
});

test('recognizes both WT and # prefixes', () => {
  const citations = [c(228), c(345)];
  const answer = 'Compare WT228 with #345.';
  const out = prioritizeCitationsForAnswer(citations, answer);
  assert.deepEqual(out.map((x) => x.issue_number), ['228', '345']);
});

test('adds missing inline WT issue citations from the issue catalog', () => {
  const citations = [c(148), c(175)];
  const catalog = new Map([
    ['190', { number: 190, subject: 'Weekly Thing 190 / DeAll', publish_date: '2021-06-12T12:00:00Z', url: '/archive/190/' }],
    ['237', { number: 237, subject: 'Weekly Thing 237 / Erratic Narratives', publish_date: '2022-12-11T13:00:00Z', url: '/archive/237/' }]
  ]);
  const answer = 'Start with WT148, then WT190 and WT237, with WT175 as context.';
  const out = prioritizeCitationsForAnswer(citations, answer, catalog);

  assert.deepEqual(out.map((x) => x.issue_number), ['148', '190', '237', '175']);
  assert.equal(out[1].subject, 'Weekly Thing 190 / DeAll');
  assert.equal(out[2].url, '/archive/237/');
});

test('empty citations stays empty', () => {
  assert.deepEqual(prioritizeCitationsForAnswer([], 'WT100'), []);
});
