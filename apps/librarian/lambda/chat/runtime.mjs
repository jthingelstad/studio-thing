import crypto from 'node:crypto';
import { ConverseCommand, ConverseStreamCommand } from '@aws-sdk/client-bedrock-runtime';
import { UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import {
  agentModel,
  advancedModel,
  bedrock,
  dynamodb,
  embeddingModel,
  fastModel,
  rerankModel
} from '../shared/aws-clients.mjs';
import { readConverseStream } from '../shared/bedrock-stream.mjs';
import { sanitizeAnswerProse } from '../shared/answer-sanitizer.mjs';
import {
  ARCHIVE_TOOLS,
  collectToolCitations,
  toolSpecs,
  weeklyIssueCatalog
} from '../shared/archive-tools.mjs';
import {
  conversationContext,
  extractPreferredNameFromMessage,
  normalizeUserProfile,
  readerContextPrompt,
  sanitizeHistory,
  tokenEntitlements
} from '../shared/chat-context.mjs';
import { prioritizeCitationsForAnswer } from '../shared/citations.mjs';
import { normalizeScope, scopeKinds, scopePromptLine } from '../shared/scope.mjs';
import {
  compactSource,
  retrieve,
  tokenize
} from '../shared/retrieval.mjs';
import { normalizeFeedbackReaction, validFeedbackRequestId } from '../shared/feedback.mjs';
import {
  PREFLIGHT_SYSTEM_PROMPT,
  normalizePreflightDecision,
  parsePreflightJson,
  passThroughPreflight
} from '../shared/prompt-preflight.mjs';
import { shouldEmitExperienceForTurn } from '../shared/experience.mjs';
import { errorFields, truthyEnv } from '../shared/logging.mjs';
import { methodAndPath, normalizeHeaders, parseBody } from '../shared/http.mjs';
import {
  agentSystemPrompt,
  agentUserPrompt
} from '../shared/prompts.mjs';
import { extractBearer, verifyToken } from '../shared/session.mjs';
import {
  getUserMemory,
  memoryContextBlock,
  recordUserPreferredName,
  recordUserTurn
} from '../shared/user-memory.mjs';
import {
  validConversationId
} from '../shared/user-conversations.mjs';
import {
  getUserConversationMetadata,
  loadUserConversationHistory,
  loadUserConversationSummaries,
  recordUserArtifactConversation,
  recordUserConversationFeedback,
  recordUserConversationTurn
} from '../shared/conversation-store.mjs';
import {
  canUseConversationMode,
  conversationModeDefinition,
  conversationModePrompt,
  normalizeConversationMode
} from '../shared/conversation-modes.mjs';

const DEFAULT_MAX_TOOL_TURNS = 7;
const DEFAULT_CHAT_SLOW_NOTICE_MS = 75000;
const DEFAULT_CHAT_DEADLINE_MS = 180000;
const RATE_LIMIT_WINDOW_SECONDS = 60 * 60;
const RATE_LIMIT_MAX = 20;

function logEvent(level, message, fields = {}) {
  console.log(JSON.stringify({
    level,
    message,
    service: 'weekly-thing-librarian-stream',
    timestamp: Math.floor(Date.now() / 1000),
    ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined && value !== null))
  }));
}

function privacyGuardAnswer(question) {
  const text = String(question || '').toLowerCase();
  const blockedPatterns = [
    /\b(home|street|personal)\s+address\b/,
    /\b(phone|cell|mobile)\s+(number|#)\b/,
    /\bwhere\s+does\s+jamie\s+live\b/,
    /\bwhat\s+city\s+does\s+jamie\s+live\s+in\b/,
    /\bwhere\s+is\s+jamie'?s\s+(home|house|residence)\b/,
    /\bjamie'?s\s+(home|house|residence)\s+(address|location)\b/
  ];
  if (!blockedPatterns.some((pattern) => pattern.test(text))) return '';
  return "I cannot help find or share Jamie's private home address or phone number. For public contact, use the contact links Jamie publishes on thingelstad.com or reply through the newsletter's normal public channels.";
}

function privacyPreflight(question) {
  const answer = privacyGuardAnswer(question);
  if (!answer) return null;
  return normalizePreflightDecision({
    action: 'direct',
    category: 'privacy_refusal',
    direct_answer: answer,
    rationale: 'Deterministic privacy guard matched an explicit private-address or phone-number request.'
  }, question);
}

function bridgeSecretOk(body) {
  // Constant-time equality against DISCORD_BRIDGE_SECRET. Returns `null`
  // when the secret isn't configured (so callers can return 503 instead
  // of 401 — telling operators "feature is off" vs "your secret is wrong").
  // Mirrors auth/handler.mjs#bridgeSecretOk; kept duplicated here because
  // shared/ doesn't carry crypto helpers and the chat Lambda is a separate
  // bundle (re-exporting across bundles would add build complexity for a
  // 5-line helper).
  const expected = process.env.DISCORD_BRIDGE_SECRET || '';
  if (!expected) return null;
  const expectedBuf = Buffer.from(expected, 'utf8');
  const suppliedBuf = Buffer.from(String(body.bridge_secret || ''), 'utf8');
  return expectedBuf.length === suppliedBuf.length && crypto.timingSafeEqual(expectedBuf, suppliedBuf);
}

async function checkRateLimit(identity, maxRequests = Number(process.env.RATE_LIMIT_MAX || RATE_LIMIT_MAX)) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return true;
  const now = Math.floor(Date.now() / 1000);
  const window = Math.floor(now / RATE_LIMIT_WINDOW_SECONDS);
  const key = `rate#${identity}#${window}`;
  const response = await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: { pk: { S: key }, sk: { S: 'rate' } },
    UpdateExpression: 'ADD #count :one SET #ttl = :ttl',
    ExpressionAttributeNames: { '#count': 'count', '#ttl': 'ttl' },
    ExpressionAttributeValues: {
      ':one': { N: '1' },
      ':ttl': { N: String(now + RATE_LIMIT_WINDOW_SECONDS * 2) }
    },
    ReturnValues: 'UPDATED_NEW'
  }));
  const count = Number(response.Attributes?.count?.N || '0');
  logEvent('info', 'rate_limit_checked', { identity_hash: identity, count, limit: maxRequests, allowed: count <= maxRequests });
  return count <= maxRequests;
}

async function recordFeedback({ subscriberHash, requestId, reaction, comment }) {
  const tableName = process.env.TABLE_NAME;
  const validRequestId = validFeedbackRequestId(requestId);
  const validReaction = normalizeFeedbackReaction(reaction);
  const feedbackComment = String(comment || '').trim().replace(/\s+/g, ' ').slice(0, 1000);
  if (!tableName) return { statusCode: 500, payload: { error: 'Thingy feedback is unavailable right now.' } };
  if (!validRequestId || !validReaction) {
    return { statusCode: 400, payload: { error: 'Feedback requires a valid request_id and reaction.' } };
  }

  const feedbackAt = new Date().toISOString();
  try {
    const result = await recordUserConversationFeedback({
      dynamodb,
      tableName,
      subscriberHash,
      requestId: validRequestId,
      reaction: validReaction,
      comment: feedbackComment,
      feedbackAt,
      logEvent
    });
    if (!result.found) {
      return { statusCode: 404, payload: { error: 'Conversation not found for feedback.', request_id: validRequestId } };
    }
    logEvent('info', 'feedback_recorded', {
      subscriber_hash: subscriberHash,
      request_id: validRequestId,
      reaction: validReaction,
      has_comment: Boolean(feedbackComment)
    });
    return { statusCode: 200, payload: { ok: true, request_id: validRequestId, reaction: validReaction, has_comment: Boolean(feedbackComment) } };
  } catch (error) {
    logEvent('warning', 'feedback_record_failed', { request_id: validRequestId, error_type: error.constructor?.name || 'Error' });
    return { statusCode: 500, payload: { error: 'Thingy could not save feedback right now.', request_id: validRequestId } };
  }
}

async function resolveRequestedConversationMode({ body, payload, subscriberHash, conversationId }) {
  const entitlements = tokenEntitlements(payload);
  const existing = conversationId
    ? await getUserConversationMetadata({
      dynamodb,
      tableName: process.env.TABLE_NAME,
      subscriberHash,
      conversationId
    })
    : null;
  const mode = existing?.mode || normalizeConversationMode(body.mode);
  if (!canUseConversationMode(mode, entitlements)) {
    return { ok: false, mode, entitlements, error: 'That Thingy mode is not available for this account.' };
  }
  return { ok: true, mode, entitlements, conversation: existing };
}

function bedrockMessageText(message) {
  const parts = [];
  for (const content of message?.content || []) {
    if (content.text) parts.push(content.text);
  }
  return parts.join('\n').trim();
}

function writeSse(stream, event, data) {
  stream.write(`event: ${event}\n`);
  stream.write(`data: ${JSON.stringify(data)}\n\n`);
}

function activityCommentaryText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .replace(/([.!?])(?=\S)/g, '$1 ')
    .trim();
}

function shortToolValue(value, max = 80) {
  const text = String(value || '').trim().replace(/\s+/g, ' ');
  return text.length <= max ? text : `${text.slice(0, max - 1).trim()}…`;
}

function quotedToolValue(value) {
  const text = shortToolValue(value);
  return text ? `“${text}”` : '';
}

function toolActivityCommentary(name, input = {}) {
  const value = input && typeof input === 'object' ? input : {};
  const query = quotedToolValue(value.query || value.topic || value.theme || value.entity || value.domain || value.claim);
  switch (name) {
    case 'search_faq':
      return query ? `Checking the FAQ for ${query}.` : 'Checking the public FAQ first.';
    case 'search_archive':
      return query ? `Searching archive text for ${query}.` : 'Searching the active archive sources.';
    case 'quote_search':
      return query ? `Looking for the exact phrase ${query}.` : 'Looking for exact wording in the archive.';
    case 'get_source':
      return value.url || value.source_id || value.issue_number
        ? 'Opening a promising source for fuller context.'
        : 'Opening source detail for context.';
    case 'get_issue':
      return value.issue_number ? `Opening WT${shortToolValue(value.issue_number, 12)} for issue-level context.` : 'Opening a Weekly Thing issue.';
    case 'get_section':
      return value.issue_number ? `Opening a specific section from WT${shortToolValue(value.issue_number, 12)}.` : 'Opening a specific archive section.';
    case 'find_links':
    case 'domain_history':
      return query ? `Tracing link metadata around ${query}.` : 'Tracing link and domain metadata.';
    case 'corpus_stats':
      return 'Checking aggregate corpus metadata and counts.';
    case 'latest_content':
      return 'Checking the freshest indexed sources.';
    case 'list_content':
      return 'Listing matching sources deterministically.';
    case 'archive_lens':
    case 'compare_eras':
      return query ? `Mapping ${query} across time and source types.` : 'Mapping the theme across the archive.';
    case 'source_neighborhood':
      return 'Inspecting the links and nearby sources around this item.';
    case 'entity_lens':
      return query ? `Checking where ${query} appears across the archive.` : 'Checking where the named entity appears.';
    case 'archive_gems':
      return query ? `Looking for a surprising archive spark around ${query}.` : 'Looking for a surprising archive spark.';
    case 'claim_check':
      return query ? `Verifying ${query} against archive evidence.` : 'Verifying the claim against archive evidence.';
    case 'remember_user':
      return 'Saving the reader preference for future turns.';
    default:
      return 'Using an archive tool to narrow the answer.';
  }
}

function commandInferenceConfig() {
  return {
    maxTokens: Number(process.env.BEDROCK_MAX_OUTPUT_TOKENS || '2500'),
    temperature: Number(process.env.BEDROCK_TEMPERATURE || '0.45')
  };
}

function chatSlowNoticeMs() {
  const value = Number(process.env.CHAT_SLOW_NOTICE_MS || DEFAULT_CHAT_SLOW_NOTICE_MS);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_CHAT_SLOW_NOTICE_MS;
}

function chatDeadlineMs() {
  const value = Number(process.env.CHAT_DEADLINE_MS || DEFAULT_CHAT_DEADLINE_MS);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_CHAT_DEADLINE_MS;
}

function preflightInferenceConfig() {
  return {
    maxTokens: Number(process.env.BEDROCK_PREFLIGHT_MAX_TOKENS || '650'),
    temperature: Number(process.env.BEDROCK_PREFLIGHT_TEMPERATURE || '0')
  };
}

function welcomeInferenceConfig() {
  return {
    maxTokens: Number(process.env.BEDROCK_WELCOME_MAX_TOKENS || '320'),
    temperature: Number(process.env.BEDROCK_WELCOME_TEMPERATURE || '0.7')
  };
}

function sourceKindLabel(kind) {
  const normalized = normalizeSourceKind(kind);
  if (normalized === 'weekly_thing') return 'Weekly Thing';
  if (normalized === 'blog') return 'Blog';
  if (normalized === 'podcast') return 'Another Thing';
  return 'Archive';
}

function sourceDisplayTitle(source = {}) {
  const sourceKind = normalizeSourceKind(source.source_kind);
  if (source.issue_number) return `WT${source.issue_number}: ${source.subject || 'Weekly Thing'}`;
  if (sourceKind === 'podcast' && source.episode_number) return `Episode ${source.episode_number}: ${source.subject || 'Another Thing'}`;
  return source.subject || source.title || source.url || 'Archive source';
}

function sourceHref(source = {}) {
  if (source.url) return source.url;
  if (source.issue_number) return `/archive/${source.issue_number}/`;
  return '';
}

function experienceSource(source = {}, reason = '') {
  const sourceKind = normalizeSourceKind(source.source_kind || (source.issue_number ? 'weekly_thing' : ''));
  return {
    source_kind: sourceKind || source.source_kind || '',
    label: sourceKindLabel(sourceKind || source.source_kind || ''),
    title: sourceDisplayTitle(source),
    subject: source.subject || '',
    publish_date: source.publish_date || '',
    year: recordYear(source) || null,
    url: sourceHref(source),
    issue_number: source.issue_number ?? null,
    microblog_id: source.microblog_id,
    episode_number: source.episode_number,
    show: source.show,
    reason: reason || source.reason || '',
    also_in_issues: source.also_in_issues,
    audio_url: source.audio_url,
    transcript_url: source.transcript_url
  };
}

function cleanThemeCandidate(value) {
  const text = String(value || '').trim();
  if (!text || /\b(?:self-referential|identify itself|what it had just been asked|immediately preceding query|thingy'?s identity|no substantive content|substantive content to summarize|no specific details)\b/i.test(text)) return '';
  const focused = text.match(/\b(?:about|exploring|explored|on|around|thread(?:s)? (?:of|around))\s+([^.,;:!?]+)/i)?.[1] || text;
  const cleaned = focused
    .replace(/[`*_#[\]()>]/g, ' ')
    .replace(/\b(?:the|this|that|user|reader|thingy|trail|jamie|archive|weekly thing|blog|podcast|question|questions|asked|asking|about|explored|exploring|conversation|session|centered|wanted|understand|thinking|perspective|structured|walkthrough|framed|through|likely|specific|details|summarize|substantive|content)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned || cleaned.length < 3) return '';
  const words = cleaned.split(/\s+/).filter((word) => word.length > 2).slice(0, 5);
  if (!words.length) return '';
  return words.join(' ').trim();
}

function themeTokens(value) {
  return [...new Set(tokenize(value).filter((token) => token.length > 2))].slice(0, 6);
}

function themesSimilar(first, second) {
  const a = themeTokens(first);
  const b = themeTokens(second);
  if (!a.length || !b.length) return false;
  if (a.join(' ') === b.join(' ')) return true;
  const overlap = a.filter((token) => b.includes(token)).length;
  return overlap >= Math.min(2, a.length, b.length);
}

function recentSparkThemes(memory, conversations = []) {
  const values = [
    ...((memory?.current_session_questions || []).slice(-5).map((item) => item?.question || item)),
    ...((memory?.synthesized_history || []).slice(-3).map((item) => item?.summary || item)),
    ...((conversations || []).slice(0, 6).map((item) => item?.title || item))
  ];
  return values.map(cleanThemeCandidate).filter(Boolean);
}

function isRecentThemeRut(theme, recentThemes = []) {
  if (!theme) return false;
  return recentThemes.filter((recent) => themesSimilar(theme, recent)).length >= 2;
}

function sparkThemeFromMemory(memory, conversations = []) {
  const recentThemes = recentSparkThemes(memory, conversations);
  for (const interest of memory?.interests || []) {
    const theme = cleanThemeCandidate(interest);
    if (theme && !isRecentThemeRut(theme, recentThemes)) return theme;
  }
  for (const fact of memory?.remembered_facts || []) {
    if (fact.category !== 'interest' && fact.category !== 'project') continue;
    const theme = cleanThemeCandidate(fact.value);
    if (theme && !isRecentThemeRut(theme, recentThemes)) return theme;
  }
  for (const summary of [...(memory?.synthesized_history || [])].reverse()) {
    const theme = cleanThemeCandidate(summary.summary);
    if (theme && !isRecentThemeRut(theme, recentThemes)) return theme;
  }
  for (const conversation of conversations || []) {
    const theme = cleanThemeCandidate(conversation.title);
    if (theme && !isRecentThemeRut(theme, recentThemes)) return theme;
  }
  return '';
}

function formatExperienceForPrompt(experience) {
  if (!experience?.items?.length) return 'No archive spark selected.';
  return [
    `${experience.title}: ${experience.intro}`,
    ...experience.items.slice(0, 3).map((item, index) => `- ${index + 1}. ${item.title}${item.publish_date ? ` (${String(item.publish_date).slice(0, 10)})` : ''}${item.reason ? ` — ${item.reason}` : ''}`)
  ].join('\n');
}

function welcomeThemeRelevance(source, theme) {
  const tokens = tokenize(theme).filter((token) => token.length > 2);
  if (!tokens.length) return 0;
  const titleText = [source.subject, source.title].join(' ').toLowerCase();
  const topicText = (source.topics || []).join(' ').toLowerCase();
  const titleMatches = tokens.filter((token) => titleText.includes(token)).length;
  const topicMatches = tokens.filter((token) => topicText.includes(token)).length;
  return titleMatches * 3 + topicMatches * 2;
}

function experienceSourceKey(source = {}) {
  const kind = normalizeSourceKind(source.source_kind || (source.issue_number ? 'weekly_thing' : ''));
  if (kind === 'weekly_thing' && source.issue_number) return `weekly_thing\0${issueKey(source.issue_number)}`;
  if (kind === 'podcast' && source.episode_number) return `podcast\0${source.episode_number}`;
  if (source.url) return `${kind || 'source'}\0${urlKey(source.url)}`;
  if (kind === 'blog' && source.microblog_id) return `blog\0${source.microblog_id}`;
  return sourceRecordKey(source);
}

function welcomeSparkSources(results = [], theme = '') {
  const seen = new Set();
  const sources = [];
  for (const source of results || []) {
    const key = experienceSourceKey(source);
    if (seen.has(key)) continue;
    seen.add(key);
    sources.push(source);
  }
  const reasonRank = (source) => {
    const reason = String(source.reason || '').toLowerCase();
    if (reason.includes('densest') || reason.includes('representative')) return 0;
    if (reason.includes('middle')) return 1;
    if (reason.includes('latest') || reason.includes('recent')) return 2;
    if (reason.includes('earliest')) return 4;
    return 3;
  };
  const sorted = sources.sort((a, b) => reasonRank(a) - reasonRank(b)
    || welcomeThemeRelevance(b, theme) - welcomeThemeRelevance(a, theme)
    || (recordYear(b) || 0) - (recordYear(a) || 0));
  const visiblyThemed = sorted.filter((source) => {
    const reason = String(source.reason || '').toLowerCase();
    return welcomeThemeRelevance(source, theme) > 0 || reason.includes('densest') || reason.includes('latest');
  });
  return (visiblyThemed.length >= 2 ? visiblyThemed : sorted).slice(0, 3);
}

async function buildWelcomeSpark({ memory, conversations, scope }) {
  const theme = sparkThemeFromMemory(memory, conversations);
  const result = await toolArchiveGems({
    theme,
    mood: theme ? '' : 'serendipity',
    limit: theme ? 5 : 3
  }, { scope });
  const sources = theme ? welcomeSparkSources(result.results || [], theme) : (result.results || []).slice(0, 3);
  const items = sources.map((source) => experienceSource(source, source.reason || (theme ? `connects to ${theme}` : 'worth resurfacing')));
  if (!items.length) return null;
  return {
    kind: 'spark',
    title: theme ? `A thread to pick up: ${theme}` : 'Archive Spark',
    intro: theme
      ? `A small path from the archive connected to ${theme}.`
      : 'A small source Thingy found while getting oriented.',
    theme: theme || null,
    items,
    prompt: theme ? `Find an adjacent Thingy Trail that starts near ${theme} but branches somewhere new.` : 'Surprise me with a Thingy Trail.'
  };
}

const CURIOSITY_STOPWORDS = new Set([
  'able', 'across', 'again', 'also', 'another', 'around', 'because', 'before', 'between',
  'conversation', 'could', 'curious', 'different', 'explore', 'exploring', 'getting',
  'jamie', 'librarian', 'little', 'looking', 'maybe', 'might', 'more', 'needs',
  'people', 'really', 'response', 'should', 'source', 'sources', 'thingelstad',
  'thingy', 'things', 'think', 'thinking', 'through', 'topic', 'trying', 'using',
  'weekly', 'would', 'write', 'writing', 'you', 'your'
]);

function titleCaseTheme(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .slice(0, 4)
    .map((word) => {
      const upper = word.toUpperCase();
      if (['AI', 'API', 'AWS', 'CSS', 'HTML', 'RSS', 'UI', 'UX'].includes(upper)) return upper;
      if (word.length <= 2) return word.toLowerCase();
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(' ');
}

function cleanCuriosityLabel(value) {
  const base = cleanThemeCandidate(value) || String(value || '').trim();
  const cleaned = base
    .replace(/^curiosity\s+map:\s*/i, ' ')
    .replace(/\b(?:please|can|could|would|tell|show|find|give|make|build|create|highlight|trace|take|use|ask)\b/gi, ' ')
    .replace(/^(.{3,80}?)\s+\binto\b\s+([^.,;:!?]{3,80}?)\s+\bacross\b.*$/i, '$2')
    .replace(/^(.{3,80}?)\s+\binto\b\s+([^.,;:!?]{3,80})$/i, '$2')
    .replace(/\b(?:from|into|with|without|near|about|around|across|versus|against|toward|towards|and|or|but)\s*$/i, ' ')
    .replace(/^\s*(?:and|or|but|to|for|on|in|of|the|a|an)\s+/i, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned || cleaned.length < 3) return '';
  if (/^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$/i.test(cleaned)) return cleaned.toLowerCase();
  return titleCaseTheme(cleaned);
}

function curiosityNodeId(value) {
  const slug = tokenize(value).slice(0, 6).join('-');
  return slug || crypto.randomUUID().slice(0, 8);
}

function curiosityPrompt(center, label, kind = 'adjacent') {
  if (kind === 'center') return `Build me a Thingy Trail around ${center}.`;
  return `Trace ${center} into ${label} across Jamie's archive.`;
}

function addCuriosityCandidate(candidates, label, { weight = 1, reason = '', source = null, kind = 'adjacent' } = {}) {
  const cleaned = cleanCuriosityLabel(label);
  if (!cleaned || cleaned.length < 3) return;
  const tokens = tokenize(cleaned).filter((token) => token.length > 1).slice(0, 6);
  if (!tokens.length || tokens.every((token) => CURIOSITY_STOPWORDS.has(token))) return;
  const key = tokens.join(' ');
  const existing = candidates.get(key) || {
    label: cleaned,
    weight: 0,
    reasons: [],
    sources: [],
    kind
  };
  existing.weight += weight;
  if (reason && !existing.reasons.includes(reason)) existing.reasons.push(reason);
  if (source && existing.sources.length < 3) existing.sources.push(source);
  existing.kind = existing.kind === 'recent' ? existing.kind : kind;
  candidates.set(key, existing);
}

function curiosityThemeCandidates(memory, conversations = []) {
  const candidates = new Map();
  const add = (value, weight, reason, kind = 'recent') => {
    const theme = cleanThemeCandidate(value);
    if (theme) addCuriosityCandidate(candidates, theme, { weight, reason, kind });
  };
  for (const item of (memory?.current_session_questions || []).slice(-8)) add(item?.question || item, 4, 'recent conversation', 'recent');
  for (const entry of (conversations || []).slice(0, 10)) add(entry?.title || '', 2.5, 'conversation history', 'recent');
  for (const item of (memory?.synthesized_history || []).slice(-5)) add(item?.summary || item, 2, 'remembered conversation pattern', 'recent');
  for (const interest of memory?.interests || []) add(interest, 2, 'remembered interest', 'memory');
  for (const fact of memory?.remembered_facts || []) {
    if (fact?.category === 'interest' || fact?.category === 'project') add(fact.value, 1.5, `remembered ${fact.category}`, 'memory');
  }
  return [...candidates.values()].sort((a, b) => b.weight - a.weight || a.label.localeCompare(b.label));
}

function addSourceCuriosityTerms(candidates, source, center) {
  const centerTokens = new Set(themeTokens(center));
  const sourceTitle = sourceDisplayTitle(source);
  const sourceReason = source.reason || `appears near ${center} in the archive`;
  for (const topic of (source.topics || []).slice(0, 8)) {
    if (!themesSimilar(topic, center)) {
      addCuriosityCandidate(candidates, topic, {
        weight: 3,
        reason: `appears near ${center} in ${sourceTitle}`,
        source,
        kind: 'archive'
      });
    }
  }
  for (const domain of (source.domains || []).slice(0, 3)) {
    const label = String(domain || '').replace(/^www\./i, '');
    if (label && !/thingelstad\.com$/i.test(label)) {
      addCuriosityCandidate(candidates, label, {
        weight: 1.2,
        reason: `linked by ${sourceTitle}`,
        source,
        kind: 'domain'
      });
    }
  }
  for (const token of tokenize([source.subject, source.title, source.section].join(' '))) {
    if (token.length < 5 || centerTokens.has(token) || CURIOSITY_STOPWORDS.has(token)) continue;
    addCuriosityCandidate(candidates, token, {
      weight: 0.45,
      reason: sourceReason,
      source,
      kind: 'archive'
    });
  }
}

async function buildCuriosityMap({ memory, conversations, scope, center }) {
  const requestedCenter = cleanCuriosityLabel(center);
  const userCandidates = curiosityThemeCandidates(memory, conversations);
  const fallbackTheme = cleanCuriosityLabel(sparkThemeFromMemory(memory, conversations));
  const centerTheme = cleanCuriosityLabel(requestedCenter || userCandidates[0]?.label || fallbackTheme) || 'Archive';
  const scopeValue = normalizeScope(scope);
  const archiveResult = centerTheme && centerTheme !== 'Archive'
    ? await toolArchiveGems({ theme: centerTheme, limit: 7 }, { scope: scopeValue })
    : await toolArchiveGems({ mood: 'serendipity', limit: 7 }, { scope: scopeValue });
  const archiveSources = welcomeSparkSources(archiveResult.results || [], centerTheme);
  const candidates = new Map();
  for (const candidate of userCandidates) {
    if (!themesSimilar(candidate.label, centerTheme)) {
      addCuriosityCandidate(candidates, candidate.label, {
        weight: candidate.weight,
        reason: candidate.reasons?.[0] || 'recent conversation pattern',
        kind: candidate.kind || 'recent'
      });
    }
  }
  for (const source of archiveSources) addSourceCuriosityTerms(candidates, source, centerTheme);
  if (candidates.size < 4 && centerTheme !== 'Archive') {
    const broad = await toolArchiveGems({ mood: 'serendipity', limit: 5 }, { scope: scopeValue });
    for (const source of broad.results || []) addSourceCuriosityTerms(candidates, source, centerTheme);
  }
  const sorted = [...candidates.values()]
    .filter((candidate) => !themesSimilar(candidate.label, centerTheme))
    .sort((a, b) => b.weight - a.weight || a.label.localeCompare(b.label))
    .slice(0, 7);
  const centerId = curiosityNodeId(centerTheme);
  const nodes = [
    {
      id: centerId,
      label: centerTheme,
      kind: 'center',
      weight: 1,
      prompt: curiosityPrompt(centerTheme, centerTheme, 'center'),
      why: 'Current center of gravity from your memory and recent conversations.'
    },
    ...sorted.map((candidate, index) => ({
      id: curiosityNodeId(candidate.label),
      label: candidate.label,
      kind: candidate.kind || 'adjacent',
      weight: Number(Math.max(0.2, Math.min(0.95, candidate.weight / Math.max(sorted[0]?.weight || 1, 1))).toFixed(2)),
      prompt: curiosityPrompt(centerTheme, candidate.label),
      why: candidate.reasons?.[0] || `A nearby thread Thingy found from ${centerTheme}.`,
      source_refs: candidate.sources.slice(0, 2).map((source) => experienceSource(source, source.reason || candidate.reasons?.[0] || 'archive evidence'))
    }))
  ];
  const edges = nodes.slice(1).map((node) => ({
    from: centerId,
    to: node.id,
    why: node.why
  }));
  return {
    kind: 'curiosity_map',
    title: `Curiosity Map: ${centerTheme}`,
    scope: scopeValue,
    center: nodes[0],
    nodes,
    edges,
    sources: archiveSources.slice(0, 5).map((source) => experienceSource(source, source.reason || `connected to ${centerTheme}`)),
    prompt: `Find the most surprising Thingy Trail that branches out from ${centerTheme}.`
  };
}

function experienceFromToolResults(toolResults = [], answer = '', question = '') {
  if (!shouldEmitExperienceForTurn({ question, answer })) return null;
  for (const result of toolResults) {
    const path = Array.isArray(result.reading_path) ? result.reading_path : [];
    if (path.length >= 2) {
      const topic = result.topic || '';
      const sources = topic ? welcomeSparkSources(path, topic) : path.slice(0, 5);
      return {
        kind: 'trail',
        title: topic ? `Thingy Trail: ${topic}` : 'Thingy Trail',
        intro: 'A guided path through the archive sources Thingy found.',
        theme: topic || null,
        items: sources.map((source) => experienceSource(source, source.reason || 'part of the trail')),
        prompt: topic ? `What adjacent thread branches out from Jamie's ${topic} trail?` : 'Show me the most surprising turn in this trail.'
      };
    }
    if (Array.isArray(result.results) && result.mode) {
      const items = result.results.slice(0, 5).map((source) => experienceSource(source, source.reason || 'archive gem'));
      if (items.length) {
        const themed = Boolean(result.theme);
        return {
          kind: themed && items.length >= 2 ? 'trail' : 'spark',
          title: themed ? `Thingy Trail: ${result.theme}` : 'Archive Spark',
          intro: themed ? `A path through ${result.theme}.` : 'A few sources worth opening next.',
          theme: result.theme || null,
          items,
          prompt: themed ? `Find an adjacent thread that branches out from ${result.theme}.` : 'Give me another archive spark.'
        };
      }
    }
  }
  if (/thingy trail|reading path|archive spark/i.test(answer)) {
    return { kind: 'trail', title: 'Thingy Trail', intro: 'A guided path through the archive.', items: [], prompt: 'Continue this trail.' };
  }
  return null;
}

function welcomePrompt({ readerContext, memoryContext, conversations, scope, mode, spark }) {
  const recent = (conversations || []).slice(0, 6);
  const modeDefinition = conversationModeDefinition(mode);
  const conversationLines = recent.length
    ? recent.map((entry) => `- ${entry.title || 'Untitled chat'} (${entry.turn_count || 0} turns, updated ${String(entry.updated_at || '').slice(0, 10) || 'unknown'})`).join('\n')
    : 'No prior conversations found.';
  return [
    'Write Thingy\'s opening message for a newly loaded chat.',
    '',
    'Thingy is Jamie Thingelstad\'s archive agent. It can help the reader connect ideas, compare eras, recall prior threads, and explore The Weekly Thing newsletter, the thingelstad.com blog, and Another Thing podcast.',
    '',
    'Reader and session context:',
    readerContext || 'No reader-local context supplied.',
    '',
    'Prior user memory:',
    memoryContext || 'No prior user memory found.',
    '',
    'Recent Thingy conversations:',
    conversationLines,
    '',
    'Archive spark selected for this visit:',
    formatExperienceForPrompt(spark),
    '',
    `Active source scope: ${normalizeScope(scope)}`,
    `Conversation mode: ${modeDefinition.label}`,
    '',
    'Mode guidance:',
    conversationModePrompt(mode),
    '',
    'Requirements:',
    '- Start with a natural greeting that can use the reader local time if supplied.',
    '- If a preferred name is known, use it. If no preferred name is known, ask what Thingy should call the reader, but keep it conversational.',
    '- If this looks like their first time, give a little more orientation. If returning, welcome them back and lightly reference the kind of things they have explored before when memory exists.',
    '- If an archive spark is supplied, mention it as a small invitation, not a citation-heavy answer. The UI may show it as a card.',
    '- In Thought Partner mode, welcome Jamie as the author and invite a reflective thread rather than explaining Thingy to a general reader.',
    '- If they are a Weekly Thing Supporting Member, acknowledge that gracefully without making the whole message about it.',
    '- Do not frame Thingy as just search. Prefer agentic verbs like connect, trace, compare, explore, and pick up threads.',
    '- Do not recite the active source list or say all sources are open; the UI already shows source selection.',
    '- Keep it under 115 words, no heading, no table, no citations.'
  ].join('\n');
}

async function generateWelcome({ readerContext, memoryContext, conversations, scope, mode, spark }) {
  const start = performance.now();
  const response = await bedrock.send(new ConverseCommand({
    modelId: agentModel(),
    system: [{ text: AGENT_SYSTEM_PROMPT }, { cachePoint: { type: 'default' } }],
    messages: [{
      role: 'user',
      content: [{ text: welcomePrompt({ readerContext, memoryContext, conversations, scope, mode, spark }) }]
    }],
    inferenceConfig: welcomeInferenceConfig()
  }));
  const answer = sanitizeAnswerProse(bedrockMessageText(response.output?.message || {})).trim();
  logEvent('info', 'welcome_generated', {
    model: agentModel(),
    mode: normalizeConversationMode(mode),
    conversation_count: (conversations || []).length,
    duration_ms: Math.round(performance.now() - start),
    output_tokens: response.usage?.outputTokens,
    answer_chars: answer.length
  });
  return answer || "Hi. I'm Thingy. Tell me what you're curious about and I'll help you explore Jamie's archive.";
}

function preflightUserPrompt(question, scope, history, context = {}) {
  return [
    `Active source scope: ${normalizeScope(scope)}`,
    `Conversation mode: ${conversationModeDefinition(context.mode).label}`,
    `Recent conversation turns available to the main agent: ${Array.isArray(history) ? history.length : 0}`,
    '',
    'Conversation so far:',
    conversationContext(Array.isArray(history) ? history : []),
    '',
    'Reader context available to the main agent:',
    context.readerContext || 'No reader-local context supplied.',
    '',
    'Durable reader memory available to the main agent:',
    context.memoryContext || 'No durable reader memory supplied.',
    '',
    'Reader prompt:',
    String(question || '').trim()
  ].join('\n');
}

async function evaluatePromptPreflight(question, scope, history = [], context = {}) {
  const hardPrivacy = privacyPreflight(question);
  if (hardPrivacy) return hardPrivacy;
  if (!truthyEnv('LIBRARIAN_PREFLIGHT_ENABLED', '1')) {
    return passThroughPreflight(question, 'Preflight evaluator disabled; passed through.');
  }
  const start = performance.now();
  try {
    const response = await bedrock.send(new ConverseCommand({
      modelId: fastModel(),
      system: [{ text: PREFLIGHT_SYSTEM_PROMPT }],
      messages: [{
        role: 'user',
        content: [{ text: preflightUserPrompt(question, scope, history, context) }]
      }],
      inferenceConfig: preflightInferenceConfig()
    }));
    const message = response.output?.message || {};
    const text = bedrockMessageText(message);
    const parsed = parsePreflightJson(text);
    const preflight = normalizePreflightDecision(parsed || {}, question);
      logEvent('info', 'prompt_preflight_completed', {
        action: preflight.action,
        category: preflight.category,
        mode: normalizeConversationMode(context.mode),
        duration_ms: Math.round(performance.now() - start),
      output_tokens: response.usage?.outputTokens
    });
    return preflight;
  } catch (error) {
    logEvent('warning', 'prompt_preflight_failed', { error_type: error.constructor?.name || 'Error' });
    return passThroughPreflight(question);
  }
}

function agentQuestionForPreflight(question, preflight) {
  if (!preflight || preflight.action !== 'rewrite') return question;
  const parts = [
    'Original reader prompt:',
    question,
    '',
    'Preflight evaluator rewrite:',
    preflight.rewritten_question
  ];
  if (preflight.answer_guidance) {
    parts.push('', 'Evaluator guidance:', preflight.answer_guidance);
  }
  parts.push('', 'Answer the reader by honoring the original prompt through the archive-shaped rewrite. Do not mention the preflight evaluator.');
  return parts.join('\n');
}

const AGENT_SYSTEM_PROMPT = agentSystemPrompt();

function compactTraceValue(value, maxChars = 1200) {
  if (value == null) return value;
  if (typeof value === 'string') return value.slice(0, maxChars);
  try {
    const json = JSON.stringify(value);
    if (json.length <= maxChars) return value;
    return { compacted: true, chars: json.length, preview: json.slice(0, maxChars) };
  } catch {
    return { compacted: true };
  }
}

function countResultItems(result) {
  if (!result || typeof result !== 'object') return 0;
  return [
    result.results,
    result.results_a,
    result.results_b,
    result.reading_path,
    result.related_sources,
    result.incoming_links,
    result.outgoing_links,
    result.cross_source_links
  ].reduce((total, value) => total + (Array.isArray(value) ? value.length : 0), 0);
}

function traceToolResult(result) {
  if (!result || typeof result !== 'object') return {};
  return {
    error: result.error ? String(result.error).slice(0, 300) : '',
    result_count: countResultItems(result),
    total_count: Number(result.total_count || 0),
    scope: result.scope,
    source_kind: result.source_kind,
    mode: result.mode,
    topic: result.topic || result.theme || result.entity || ''
  };
}

async function streamBedrockAgentAnswer(question, history, responseStream, options = {}) {
  const start = performance.now();
    const scope = normalizeScope(options.scope);
    const mode = normalizeConversationMode(options.mode);
    const memoryContext = String(options.memoryContext || '').trim();
  const readerContext = String(options.readerContext || '').trim();
  const agentQuestion = agentQuestionForPreflight(question, options.preflight);
  const shouldStopWriting = () => Boolean(options.deadlineExceeded?.());
  const messages = [{
    role: 'user',
    content: [{
      text: agentUserPrompt({
        conversation_context: conversationContext(history),
        reader_context: readerContext || 'No reader-local context supplied.',
        question: agentQuestion
      })
    }]
  }];
  const toolResults = [];
  const toolTrace = { calls: [] };
  let answer = '';
  let usage = {};
  let stopReason = '';
  const maxTurns = Number(process.env.MAX_TOOL_TURNS || DEFAULT_MAX_TOOL_TURNS);
  // The static system prompt is cached. Per-user memory is appended after
  // the cachePoint as a separate block — uncached, since it varies per
  // request, but it doesn't bust the prefix cache for the static prompt.
  const systemBlocks = [{ text: AGENT_SYSTEM_PROMPT }, { cachePoint: { type: 'default' } }];
  // Active scope varies per request, so it goes after the cachePoint as its
  // own block — it tells the agent which corpus it may speak from without
  // busting the static prompt's prefix cache.
    systemBlocks.push({ text: scopePromptLine(scope) });
    systemBlocks.push({ text: conversationModePrompt(mode) });
    if (memoryContext) {
    systemBlocks.push({ text: memoryContext });
  }
  for (let turn = 0; turn <= maxTurns; turn += 1) {
    const response = await bedrock.send(new ConverseStreamCommand({
      modelId: agentModel(),
      system: systemBlocks,
      messages,
      toolConfig: { tools: toolSpecs() },
      inferenceConfig: commandInferenceConfig()
    }));
    const result = await readConverseStream(response);
    const message = result.message;
    usage = result.usage || usage;
    stopReason = result.stopReason || stopReason;
    messages.push(message);
    const toolUses = (message.content || []).filter((block) => block.toolUse).map((block) => block.toolUse);
    if (!toolUses.length) {
      answer = bedrockMessageText(message) || result.text;
      break;
    }
    const commentary = activityCommentaryText(result.text);
    const resultBlocks = [];
    for (const [index, toolUse] of toolUses.entries()) {
      const toolNote = toolActivityCommentary(toolUse.name, toolUse.input || {});
      const visibleNote = [index === 0 ? commentary : '', toolNote].filter(Boolean).join(' ');
      if (!shouldStopWriting()) {
        writeSse(responseStream, 'status', {
          kind: 'tool',
          tool_name: toolUse.name,
          message: `Checking ${toolUse.name.replaceAll('_', ' ')}...`,
          commentary: visibleNote
        });
      }
      const handler = ARCHIVE_TOOLS[toolUse.name];
      let result;
      const toolStart = performance.now();
      let ok = true;
      try {
        result = handler ? await handler(toolUse.input || {}, { scope, subscriberHash: options.subscriberHash }) : { error: `Unknown tool: ${toolUse.name}` };
      } catch (error) {
        ok = false;
        logEvent('error', 'tool_call_failed', errorFields(error, {
          request_id: options.requestId,
          conversation_id: options.conversationId,
          tool_name: toolUse.name
        }));
        result = { error: `${toolUse.name} failed: ${error.constructor?.name || 'Error'}` };
      }
      toolTrace.calls.push({
        name: toolUse.name,
        input: compactTraceValue(toolUse.input || {}, 1000),
        ok: ok && !result?.error,
        duration_ms: Math.round(performance.now() - toolStart),
        result: traceToolResult(result)
      });
      toolResults.push(result);
      resultBlocks.push({ toolResult: { toolUseId: toolUse.toolUseId, content: [{ json: result }] } });
    }
    messages.push({
      role: 'user',
      content: resultBlocks
    });
  }
  if (!answer) {
    if (stopReason === 'tool_use') {
      stopReason = 'tool_use_exhausted';
      answer = [
        'I found archive material for this, but I ran out of my research loop before I could turn it into a reliable answer.',
        'Try asking again with a narrower angle, or ask me to pick one specific source or time period.'
      ].join(' ');
    } else {
      answer = 'I could not produce a reliable answer from the archive tools for that question.';
    }
  }
  const sanitizedAnswer = sanitizeAnswerProse(answer);
  answer = sanitizedAnswer;
  if (!shouldStopWriting()) writeSse(responseStream, 'answer', { answer });
  const citations = prioritizeCitationsForAnswer(collectToolCitations(toolResults), answer, await weeklyIssueCatalog());
  const experience = experienceFromToolResults(toolResults, answer, question);
  if (experience && !shouldStopWriting()) {
    writeSse(responseStream, 'experience', { experience });
  }
    logEvent('info', 'agent_streamed', {
      request_id: options.requestId,
      conversation_id: options.conversationId,
      model: agentModel(),
      scope,
      mode,
      tool_turns: toolResults.length,
      citation_count: citations.length,
    experience_kind: experience?.kind,
    duration_ms: Math.round(performance.now() - start),
    answer_chars: answer.length,
    output_tokens: usage?.outputTokens,
    stop_reason: stopReason,
    deadline_exceeded: shouldStopWriting()
  });
  return {
    answer,
    citations,
    experience,
    toolTrace,
    metrics: {
      model: agentModel(),
      duration_ms: Math.round(performance.now() - start),
      output_tokens: usage?.outputTokens,
      stop_reason: stopReason
    }
  };
}

function streamFromResponse(responseStream, event, statusCode) {
  return awslambda.HttpResponseStream.from(responseStream, {
    statusCode,
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      'x-accel-buffering': 'no'
    }
  });
}

function jsonResponseStream(responseStream, statusCode) {
  return awslambda.HttpResponseStream.from(responseStream, {
    statusCode,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store'
    }
  });
}

async function handleCuriosityMapRoute({ event, responseStream, requestId, summary, start }) {
  const body = parseBody(event);
  const payload = verifyToken(extractBearer(event, body));
  if (!payload) {
    const s401 = jsonResponseStream(responseStream, 401);
    s401.write(JSON.stringify({ error: 'Please validate your subscriber email to use the librarian.', request_id: requestId }));
    s401.end();
    logEvent('warning', 'curiosity_map_unauthorized', { ...summary });
    return;
    }
    const subscriberHash = String(payload.sub || '');
    const requestedConversationId = validConversationId(body.conversation_id || body.conversationId);
    const modeAccess = await resolveRequestedConversationMode({
      body,
      payload,
      subscriberHash,
      conversationId: requestedConversationId
    });
    if (!modeAccess.ok) {
      const s403 = jsonResponseStream(responseStream, 403);
      s403.write(JSON.stringify({ error: modeAccess.error, request_id: requestId }));
      s403.end();
      return;
    }
    if (!(await checkRateLimit(`curiosity_map#${subscriberHash}`, Number(process.env.RATE_LIMIT_MAX || RATE_LIMIT_MAX)))) {
    const s429 = jsonResponseStream(responseStream, 429);
    s429.write(JSON.stringify({ error: 'Thingy is at the hourly limit for this session.', request_id: requestId }));
    s429.end();
    return;
  }
  try {
    const scope = normalizeScope(body.scope);
    const memory = await getUserMemory(subscriberHash);
    const conversations = await loadUserConversationSummaries({
      dynamodb,
      tableName: process.env.TABLE_NAME,
      subscriberHash,
      limit: 12,
      logEvent
    });
    const map = await buildCuriosityMap({
      memory,
      conversations,
      scope,
      center: body.center || body.topic || body.query
    });
      const conversationId = requestedConversationId || crypto.randomUUID();
    const center = map.center?.label || String(map.title || '').replace(/^Curiosity Map:\s*/i, '') || 'archive';
    const conversation = await recordUserArtifactConversation({
      dynamodb,
      tableName: process.env.TABLE_NAME,
      subscriberHash,
        conversationId,
        artifact: map,
        scope,
        mode: modeAccess.mode,
        requestId,
      title: map.title || 'Curiosity Map',
      preview: `Explore branches from ${center}.`,
      logEvent,
      preserveConversationSummary: Boolean(requestedConversationId)
    });
    const s200 = jsonResponseStream(responseStream, 200);
    s200.write(JSON.stringify({ ...map, request_id: requestId, conversation_id: conversationId, conversation }));
    s200.end();
    logEvent('info', 'curiosity_map_completed', {
        ...summary,
        subscriber_hash: subscriberHash,
        conversation_id: conversationId,
        mode: modeAccess.mode,
        attached_to_existing_conversation: Boolean(requestedConversationId),
      node_count: map.nodes?.length || 0,
      source_count: map.sources?.length || 0,
      scope,
      duration_ms: Math.round(performance.now() - start)
    });
  } catch (error) {
    const s500 = jsonResponseStream(responseStream, 500);
    s500.write(JSON.stringify({ error: 'Thingy could not draw a curiosity map right now.', request_id: requestId }));
    s500.end();
    logEvent('error', 'curiosity_map_failed', { ...summary, error_type: error.constructor?.name || 'Error' });
  }
}

export const handler = awslambda.streamifyResponse(async (event, responseStream, context) => {
  const start = performance.now();
  const requestId = context?.awsRequestId || event.requestContext?.requestId || crypto.randomUUID();
  const { method, path } = methodAndPath(event);
  const summary = { request_id: requestId, method, path, origin: normalizeHeaders(event.headers || {}).origin };
  let subscriberHash = '';
  logEvent('info', 'request_started', summary);

  if (method === 'OPTIONS') {
    const stream = streamFromResponse(responseStream, event, 204);
    stream.end();
    return;
  }

  if (method === 'GET' && path.endsWith('/health')) {
    const stream = jsonResponseStream(responseStream, 200);
    stream.write(JSON.stringify({
      ok: true,
      service: 'weekly-thing-librarian-stream',
      model: agentModel(),
      fast_model: fastModel(),
      advanced_model: advancedModel(),
      embedding_model: embeddingModel(),
      rerank_model: rerankModel()
    }));
    stream.end();
    logEvent('info', 'request_completed', { ...summary, duration_ms: Math.round(performance.now() - start) });
    return;
  }

  if (method === 'POST' && path.endsWith('/feedback')) {
    const body = parseBody(event);
    const payload = verifyToken(extractBearer(event, body));
    const result = payload
      ? await recordFeedback({
        subscriberHash: String(payload.sub || ''),
        requestId: body.request_id,
        reaction: body.reaction,
        comment: body.comment
      })
      : { statusCode: 401, payload: { error: 'Please validate your subscriber email to use the librarian.', request_id: requestId } };
    const stream = jsonResponseStream(responseStream, result.statusCode);
    stream.write(JSON.stringify(result.payload));
    stream.end();
    logEvent('info', 'request_completed', { ...summary, status_code: result.statusCode, duration_ms: Math.round(performance.now() - start) });
    return;
  }

  if (method === 'POST' && path.endsWith('/retrieve')) {
    // Operator-only retrieval. Same Bedrock embed → vector search → Cohere
    // rerank pipeline /chat uses, exposed as a passages-only JSON response
    // (no Sonnet call). Auth via DISCORD_BRIDGE_SECRET, not per-user token —
    // the caller is workshop_bot, not a reader. Used by compose-closer to
    // ground "From the Archive" picks on actual archive content rather
    // than vocabulary-only BM25 matches.
    const body = parseBody(event);
    const secretState = bridgeSecretOk(body);
    if (secretState === null) {
      const s503 = jsonResponseStream(responseStream, 503);
      s503.write(JSON.stringify({ error: 'Bridge retrieval is not enabled.' }));
      s503.end();
      logEvent('warning', 'retrieve_bridge_disabled', { ...summary });
      return;
    }
    if (!secretState) {
      const s401 = jsonResponseStream(responseStream, 401);
      s401.write(JSON.stringify({ error: 'Bridge secret rejected.' }));
      s401.end();
      logEvent('warning', 'retrieve_bad_secret', { ...summary });
      return;
    }
    const query = String(body.query || '').trim();
    if (!query) {
      const s400 = jsonResponseStream(responseStream, 400);
      s400.write(JSON.stringify({ error: 'query is required.' }));
      s400.end();
      return;
    }
    const requestedK = Number(body.k || 12);
    const limit = Math.max(1, Math.min(Number.isFinite(requestedK) ? requestedK : 12, 40));
    const filters = (body.filters && typeof body.filters === 'object') ? body.filters : {};
    // Optional scope (default weekly_thing). workshop_bot sends no scope, so
    // it keeps getting WT-only passages — unaffected by the blog corpus.
    filters.scope = normalizeScope(body.scope ?? filters.scope);
    try {
      const passages = await retrieve(query, limit, filters);
      const compact = passages.map((p) => compactSource(p, 1200));
      const s200 = jsonResponseStream(responseStream, 200);
      s200.write(JSON.stringify({
        passages: compact,
        embedding_model: embeddingModel(),
        rerank_model: rerankModel(),
        request_id: requestId
      }));
      s200.end();
      logEvent('info', 'retrieve_completed', {
        ...summary,
        query_chars: query.length,
        k: limit,
        passage_count: compact.length,
        duration_ms: Math.round(performance.now() - start)
      });
    } catch (error) {
      const s500 = jsonResponseStream(responseStream, 500);
      s500.write(JSON.stringify({ error: 'Retrieval failed.', request_id: requestId }));
      s500.end();
      logEvent('error', 'retrieve_failed', { ...summary, error_type: error.constructor?.name || 'Error' });
    }
    return;
  }

  if (method === 'POST' && path.endsWith('/curiosity-map')) {
    await handleCuriosityMapRoute({ event, responseStream, requestId, summary, start });
    return;
  }

  const isStreamRoute = method === 'POST' && (path.endsWith('/chat') || path.endsWith('/welcome'));
  const stream = streamFromResponse(responseStream, event, isStreamRoute ? 200 : 404);
  try {
    if (!isStreamRoute) {
      writeSse(stream, 'error', { error: 'Not found.', request_id: requestId });
      return;
    }

    const body = parseBody(event);
    const payload = verifyToken(extractBearer(event, body));
    if (!payload) {
      writeSse(stream, 'error', { error: 'Please validate your subscriber email to use the librarian.', request_id: requestId });
      return;
    }
    subscriberHash = String(payload.sub || '');

      if (path.endsWith('/welcome')) {
        const scope = normalizeScope(body.scope);
        const modeAccess = await resolveRequestedConversationMode({
          body,
          payload,
          subscriberHash,
          conversationId: ''
        });
        if (!modeAccess.ok) {
          writeSse(stream, 'error', { error: modeAccess.error, request_id: requestId });
          return;
        }
        const userProfile = normalizeUserProfile(body.user_profile);
      const memory = await getUserMemory(subscriberHash);
      const effectiveProfile = {
        ...userProfile,
        preferred_name: userProfile.preferred_name || memory?.preferred_name || '',
        returning: userProfile.returning || Number(memory?.turn_count || 0) > 0,
        turn_count: userProfile.turn_count ?? Number(memory?.turn_count || 0)
      };
      const readerContext = readerContextPrompt(body.client_context, effectiveProfile);
      const memoryContext = memoryContextBlock(memory);
      const conversations = await loadUserConversationSummaries({
        dynamodb,
        tableName: process.env.TABLE_NAME,
        subscriberHash,
        limit: 8,
        logEvent
      });
      if (!(await checkRateLimit(`welcome#${String(payload.sub)}`, Number(process.env.RATE_LIMIT_MAX || RATE_LIMIT_MAX)))) {
        writeSse(stream, 'error', { error: 'Thingy is at the hourly limit for this session.', request_id: requestId });
        return;
      }
      writeSse(stream, 'meta', { request_id: requestId });
      writeSse(stream, 'status', { message: 'Thingy is getting oriented...' });
      let spark = null;
      try {
        spark = await buildWelcomeSpark({ memory, conversations, scope });
      } catch (error) {
        logEvent('warning', 'welcome_spark_failed', { error_type: error.constructor?.name || 'Error' });
      }
      if (spark) writeSse(stream, 'experience', { experience: spark });
        const answer = await generateWelcome({ readerContext, memoryContext, conversations, scope, mode: modeAccess.mode, spark });
        writeSse(stream, 'answer_delta', { delta: answer });
        writeSse(stream, 'done', { request_id: requestId, mode: modeAccess.mode });
        logEvent('info', 'welcome_completed', {
          subscriber_hash: subscriberHash,
          mode: modeAccess.mode,
          conversation_count: conversations.length,
        has_memory: Boolean(memory),
        has_preferred_name: Boolean(effectiveProfile.preferred_name),
        has_spark: Boolean(spark),
        duration_ms: Math.round(performance.now() - start)
      });
      return;
    }

      const question = String(body.message || '').trim();
      const scope = normalizeScope(body.scope);
      const userProfile = normalizeUserProfile(body.user_profile);
      const suppliedPreferredName = userProfile.preferred_name || extractPreferredNameFromMessage(question);
      let effectiveUserProfile = {
        ...userProfile,
        preferred_name: suppliedPreferredName || userProfile.preferred_name
      };
      let readerContext = readerContextPrompt(body.client_context, effectiveUserProfile);
      const requestedConversationId = validConversationId(body.conversation_id || body.conversationId);
      const conversationId = requestedConversationId || crypto.randomUUID();
      const modeAccess = await resolveRequestedConversationMode({
        body,
        payload,
        subscriberHash,
        conversationId: requestedConversationId
      });
      if (!modeAccess.ok) {
        writeSse(stream, 'error', { error: modeAccess.error, request_id: requestId });
        return;
      }
      const history = await loadUserConversationHistory({
        dynamodb,
        tableName: process.env.TABLE_NAME,
        subscriberHash,
        conversationId,
        logEvent
      });
      if (!question) {
        writeSse(stream, 'error', { error: 'Ask a question about the archive.', request_id: requestId });
        return;
      }
      if (question.length > Number(process.env.MAX_QUESTION_CHARS || '1200')) {
        writeSse(stream, 'error', { error: 'Please ask a shorter question.', request_id: requestId });
        return;
      }
      if (!(await checkRateLimit(String(payload.sub)))) {
        writeSse(stream, 'error', { error: 'The librarian is at the hourly limit for this session.', request_id: requestId });
        return;
      }
      if (effectiveUserProfile.preferred_name) {
        await recordUserPreferredName(subscriberHash, effectiveUserProfile.preferred_name);
      }

      // Fetch user memory before preflight so memory/conversation-meta prompts
      // are not answered by the evaluator from an empty context.
      const userMemory = await getUserMemory(subscriberHash);
      const memoryContext = memoryContextBlock(userMemory);
      if (!effectiveUserProfile.preferred_name && userMemory?.preferred_name) {
        effectiveUserProfile = {
          ...effectiveUserProfile,
          preferred_name: userMemory.preferred_name
        };
        readerContext = readerContextPrompt(body.client_context, effectiveUserProfile);
      }

      writeSse(stream, 'meta', { request_id: requestId, conversation_id: conversationId, mode: modeAccess.mode });
      writeSse(stream, 'status', { message: 'Understanding the request...' });
      const preflight = await evaluatePromptPreflight(question, scope, history, { readerContext, memoryContext, mode: modeAccess.mode });
      if (preflight.action === 'direct') {
        preflight.direct_answer = sanitizeAnswerProse(preflight.direct_answer);
        const citations = [];
        writeSse(stream, 'answer_delta', { delta: preflight.direct_answer });
        writeSse(stream, 'citations', { citations });
        const conversation = await recordUserConversationTurn({
          dynamodb,
          tableName: process.env.TABLE_NAME,
          subscriberHash,
          conversationId,
          question,
          answer: preflight.direct_answer,
          scope,
          mode: modeAccess.mode,
          requestId,
          citations,
          preflight,
          toolTrace: { calls: [] },
          metrics: {
            model: fastModel(),
            stop_reason: 'preflight_direct'
          },
          logEvent
        });
        writeSse(stream, 'done', { request_id: requestId, conversation_id: conversationId, conversation, mode: modeAccess.mode });
        // Guarded/direct turns still update memory — the question text was
        // recorded above, so let the user-memory row reflect that turn too.
        await recordUserTurn(subscriberHash, { sid: String(payload.sid || ''), question, preferredName: effectiveUserProfile.preferred_name });
        return;
      }

      writeSse(stream, 'status', { message: 'Investigating the archive...' });
      let deadlineExceeded = false;
      const deadlineMs = chatDeadlineMs();
      const slowNoticeMs = Math.min(chatSlowNoticeMs(), Math.max(1000, deadlineMs - 1000));
      const slowNoticeTimer = setTimeout(() => {
        if (deadlineExceeded) return;
        try {
          writeSse(stream, 'status', {
            message: 'This is a deeper archive pass. Thingy is still working...'
          });
        } catch {}
        logEvent('info', 'chat_slow_notice_sent', {
          request_id: requestId,
          conversation_id: conversationId,
          subscriber_hash: subscriberHash,
          mode: modeAccess.mode,
          slow_notice_ms: slowNoticeMs,
          deadline_ms: deadlineMs
        });
      }, slowNoticeMs);
      const deadlineTimer = setTimeout(() => {
        deadlineExceeded = true;
        try {
          writeSse(stream, 'error', {
            error: 'Thingy spent too long in the archive. Please try again with a narrower angle.',
            request_id: requestId
          });
        } catch {}
        try { stream.end(); } catch {}
        logEvent('warning', 'chat_deadline_exceeded', {
          request_id: requestId,
          conversation_id: conversationId,
          subscriber_hash: subscriberHash,
          mode: modeAccess.mode,
          deadline_ms: deadlineMs
        });
      }, deadlineMs);
      let result;
      try {
        result = await streamBedrockAgentAnswer(question, history, stream, {
          memoryContext,
          readerContext,
          scope,
          mode: modeAccess.mode,
          preflight,
          subscriberHash,
          requestId,
          conversationId,
          deadlineExceeded: () => deadlineExceeded
        });
      } finally {
        clearTimeout(slowNoticeTimer);
        clearTimeout(deadlineTimer);
      }
      if (deadlineExceeded) {
        await recordUserConversationTurn({
          dynamodb,
          tableName: process.env.TABLE_NAME,
          subscriberHash,
          conversationId,
          question,
          answer: 'Thingy spent too long in the archive before it could return a reliable answer.',
          scope,
          mode: modeAccess.mode,
          requestId,
          citations: [],
          preflight,
          toolTrace: result?.toolTrace || { calls: [] },
          metrics: {
            model: result?.metrics?.model || agentModel(),
            duration_ms: Math.round(performance.now() - start),
            output_tokens: result?.metrics?.output_tokens,
            stop_reason: 'app_deadline_exceeded'
          },
          logEvent
        });
        return;
      }
      const answer = result.answer;
      const citations = result.citations;
      const conversation = await recordUserConversationTurn({
        dynamodb,
        tableName: process.env.TABLE_NAME,
        subscriberHash,
        conversationId,
        question,
        answer,
        scope,
        mode: modeAccess.mode,
        requestId,
        citations,
        preflight,
        toolTrace: result.toolTrace,
        metrics: result.metrics,
        logEvent
      });
      writeSse(stream, 'citations', { citations });
      writeSse(stream, 'done', { request_id: requestId, conversation_id: conversationId, conversation, mode: modeAccess.mode });
      // Update per-user memory after the answer ships. If the sid has
      // rotated since the prior turn, this also triggers a Bedrock-
      // synthesized summary of the previous session.
      await recordUserTurn(subscriberHash, { sid: String(payload.sid || ''), question, preferredName: effectiveUserProfile.preferred_name });
      logEvent('info', 'chat_completed', {
        subscriber_hash: subscriberHash,
        request_id: requestId,
        conversation_id: conversationId,
        mode: modeAccess.mode,
        question_chars: question.length,
        history_count: history.length,
        citation_count: citations.length,
        duration_ms: Math.round(performance.now() - start)
      });
  } catch (error) {
    logEvent('error', 'request_failed', errorFields(error, {
      ...summary,
      subscriber_hash: subscriberHash
    }));
    writeSse(stream, 'error', { error: 'The librarian could not generate an answer right now.', request_id: requestId });
  } finally {
    logEvent('info', 'request_completed', { ...summary, duration_ms: Math.round(performance.now() - start) });
    stream.end();
  }
});
