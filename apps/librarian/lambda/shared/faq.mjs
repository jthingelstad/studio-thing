import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const FAQ_PATH = path.join(ROOT, 'faq.json');
const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;
let faqCache;

export function loadFaq() {
  if (!faqCache) {
    faqCache = JSON.parse(fs.readFileSync(FAQ_PATH, 'utf8'));
  }
  return faqCache;
}

export function renderFaqAnswer(answer, replacements = {}) {
  return String(answer || '').replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, key) => String(replacements[key] ?? ''));
}

export function markdownToPlainText(markdown) {
  return String(markdown || '')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/^[ \t]*[-*]\s+/gm, '')
    .replace(/[>#*_~]+/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function tokenize(value) {
  return Array.from(String(value || '').matchAll(TOKEN_RE), (match) => match[0].toLowerCase());
}

export function faqEntries(replacements = {}) {
  const entries = [];
  for (const section of loadFaq().sections || []) {
    for (const entry of section.entries || []) {
      const answer = renderFaqAnswer(entry.answer, replacements);
      entries.push({
        section: section.title,
        question: entry.question,
        answer,
        answer_text: markdownToPlainText(answer),
        url: '/faq/'
      });
    }
  }
  return entries;
}

export function searchFaq(query, { limit = 5, replacements = {} } = {}) {
  const queryTerms = tokenize(query);
  if (!queryTerms.length) return [];
  const scored = [];
  for (const entry of faqEntries(replacements)) {
    const questionTerms = tokenize(entry.question);
    const answerTerms = tokenize(entry.answer_text);
    const sectionTerms = tokenize(entry.section);
    let score = 0;
    for (const term of queryTerms) {
      score += questionTerms.filter((item) => item === term).length * 8;
      score += sectionTerms.filter((item) => item === term).length * 3;
      score += answerTerms.filter((item) => item === term).length;
    }
    if (score > 0) scored.push({ score, entry });
  }
  return scored
    .sort((left, right) => right.score - left.score || left.entry.question.localeCompare(right.entry.question))
    .slice(0, Math.max(1, Math.min(Number(limit) || 5, 10)))
    .map(({ entry }) => entry);
}
