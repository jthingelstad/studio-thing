import assert from 'node:assert/strict';
import test from 'node:test';
import {
  answerFramesExperience,
  isExperienceRequest,
  shouldEmitExperienceForTurn
} from '../dist/shared/experience.mjs';

test('ordinary topical questions do not request archive experience cards', () => {
  assert.equal(isExperienceRequest('Tell me about Jamie and publishing.'), false);
  assert.equal(shouldEmitExperienceForTurn({
    question: 'Tell me about Jamie and publishing.',
    answer: 'Jamie wrote about this in several places, mostly as part of a broader publishing thread.'
  }), false);
});

test('discovery and recommendation prompts request archive experience cards', () => {
  assert.equal(isExperienceRequest('Surprise me with something interesting from the archive.'), true);
  assert.equal(isExperienceRequest('What should I read about RSS?'), true);
  assert.equal(isExperienceRequest('Build me a reading path about RSS.'), true);
  assert.equal(isExperienceRequest('Find an adjacent thread that branches out from privacy.'), true);
});

test('answers can explicitly frame an experience card', () => {
  assert.equal(answerFramesExperience('Here is a small Archive Spark from the older blog.'), true);
  assert.equal(answerFramesExperience('A Thingy Trail through RSS starts with these sources.'), true);
});

test('plain trail or spark words alone are not enough to emit cards', () => {
  assert.equal(answerFramesExperience('This source leaves a trail of links.'), false);
  assert.equal(answerFramesExperience('Apache Spark does not appear much here.'), false);
});
