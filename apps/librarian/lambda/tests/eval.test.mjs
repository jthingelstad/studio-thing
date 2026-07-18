import assert from 'node:assert/strict';
import test from 'node:test';
import { evalSystemPrompt } from '../dist/eval/handler.mjs';
import { turnForPrompt } from '../dist/shared/eval-transcript.mjs';

test('eval criteria preserve citation, temporal, and runtime regression rules', () => {
  const prompt = evalSystemPrompt();

  assert.match(prompt, /visible source labels or citation footer/);
  assert.match(prompt, /retrospective evidence is presented as if it were contemporaneous/);
  assert.match(prompt, /app_deadline_exceeded or tool_use_exhausted/);
  assert.match(prompt, /prefer runtime_timeout and\/or tool_gap/);
});

test('eval prompt includes long answers without silent mid-answer clipping', () => {
  const answer = [
    'Opening section.',
    'A'.repeat(3000),
    'Middle Period: Engineering Philosophy and Org Wisdom.',
    'B'.repeat(3000),
    'Clean ending.'
  ].join(' ');
  const prompt = turnForPrompt({
    question: 'Trace software development across the archive.',
    answer,
    citations: [],
    tool_names: [],
    stop_reason: 'end_turn',
    duration_ms: 53976
  }, 0);

  assert.match(prompt, /Middle Period: Engineering Philosophy/);
  assert.match(prompt, /Clean ending\./);
  assert.doesNotMatch(prompt, /Evaluator transcript note/);
  assert.match(prompt, /Runtime: stop_reason=end_turn, duration_ms=53976/);
});

test('eval prompt marks evaluator-only clipping when answers exceed prompt budget', () => {
  const prompt = turnForPrompt({
    question: 'Tell me everything.',
    answer: 'x'.repeat(13000),
    citations: [],
    tool_names: []
  }, 0);

  assert.match(prompt, /Evaluator transcript note: \d+ characters omitted/);
  assert.match(prompt, /do not treat this as reader-visible truncation/);
});
