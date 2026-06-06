import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PROMPTS_DIR = path.join(ROOT, 'prompts');
const cache = new Map();

export function promptPath(name) {
  return path.join(PROMPTS_DIR, name);
}

export function loadPrompt(name) {
  if (!cache.has(name)) {
    cache.set(name, fs.readFileSync(promptPath(name), 'utf8').trim());
  }
  return cache.get(name);
}

export function loadToolSpecs() {
  return JSON.parse(loadPrompt('tool-specs.json'));
}

export function renderTemplate(text, values = {}) {
  return String(text || '').replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, key) => String(values[key] ?? ''));
}

export function answerStyle() {
  return loadPrompt('answer-style.md').replace(/\s+/g, ' ');
}

export function agentSystemPrompt() {
  return renderTemplate(loadPrompt('agent-system.md'), { answer_style: answerStyle() });
}

export function agentUserPrompt({ conversation_context, reader_context, question } = {}) {
  return renderTemplate(loadPrompt('agent-user.md'), {
    conversation_context,
    reader_context,
    question
  });
}

export function premiumThankYouSystemPrompt() {
  return loadPrompt('premium-thank-you.md');
}
