import crypto from 'node:crypto';
import { ConverseCommand, ConverseStreamCommand, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
import { RerankCommand } from '@aws-sdk/client-bedrock-agent-runtime';
import { UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { GetObjectCommand } from '@aws-sdk/client-s3';
import {
  agentModel,
  advancedModel,
  bedrock,
  bedrockAgentRuntime,
  dynamodb,
  embeddingModel,
  fastModel,
  rerankModel,
  s3
} from '../shared/aws-clients.mjs';
import { readConverseStream } from '../shared/bedrock-stream.mjs';
import { sanitizeAnswerProse } from '../shared/answer-sanitizer.mjs';
import { buildArchiveLens } from '../shared/archive-lens.mjs';
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
import { normalizeFeedbackReaction, validFeedbackRequestId } from '../shared/feedback.mjs';
import {
  PREFLIGHT_SYSTEM_PROMPT,
  normalizePreflightDecision,
  parsePreflightJson,
  passThroughPreflight
} from '../shared/prompt-preflight.mjs';
import { countsByPublishYear, yearCountSummary, yearlyContentSignals } from '../shared/corpus-stats.mjs';
import { shouldEmitExperienceForTurn } from '../shared/experience.mjs';
import { searchFaq } from '../shared/faq.mjs';
import { errorFields, truthyEnv } from '../shared/logging.mjs';
import { methodAndPath, normalizeHeaders, parseBody } from '../shared/http.mjs';
import {
  agentSystemPrompt,
  agentUserPrompt,
  loadToolSpecs
} from '../shared/prompts.mjs';
import { extractBearer, verifyToken } from '../shared/session.mjs';
import {
  getUserMemory,
  memoryContextBlock,
  recordUserPreferredName,
  recordUserTurn,
  rememberUserFact
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

const DEFAULT_EMBEDDING_DIMENSIONS = 1024;
const DEFAULT_MAX_TOOL_TURNS = 7;
const DEFAULT_CHAT_SLOW_NOTICE_MS = 75000;
const DEFAULT_CHAT_DEADLINE_MS = 180000;
const RATE_LIMIT_WINDOW_SECONDS = 60 * 60;
const RATE_LIMIT_MAX = 20;
const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;

let corpusCache;
let blogCorpusCache;
let podcastCorpusCache;
let graphCache;
let indexedCache;
let blogIndexedCache;
let podcastIndexedCache;

function logEvent(level, message, fields = {}) {
  console.log(JSON.stringify({
    level,
    message,
    service: 'weekly-thing-librarian-stream',
    timestamp: Math.floor(Date.now() / 1000),
    ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined && value !== null))
  }));
}

function rerankModelArn() {
  const model = rerankModel();
  if (model.startsWith('arn:')) return model;
  const region = process.env.BEDROCK_RERANK_REGION || 'us-west-2';
  return `arn:aws:bedrock:${region}::foundation-model/${model}`;
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

const EMPTY_CORPUS = { version: 0, chunks: [], issues: [], topics: [], links: [] };

async function loadCorpus(kind = 'weekly_thing') {
  if (kind === 'blog') return loadBlogCorpus();
  if (kind === 'podcast') return loadPodcastCorpus();
  if (corpusCache) return corpusCache;
  const bucket = process.env.CORPUS_BUCKET;
  const key = process.env.CORPUS_KEY || 'librarian/corpus.json';
  if (!bucket) throw new Error('CORPUS_BUCKET is required');
  const start = performance.now();
  const response = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
  corpusCache = JSON.parse(await response.Body.transformToString());
  logEvent('info', 'corpus_loaded', {
    source: 's3',
    scope: 'weekly_thing',
    bucket,
    key,
    chunk_count: corpusCache.chunk_count || corpusCache.chunks?.length || 0,
    embedding_dimensions: corpusCache.embedding_dimensions,
    duration_ms: Math.round(performance.now() - start)
  });
  return corpusCache;
}

async function loadOptionalCorpus({ kind, envKey, disabledEvent, failedEvent, cache, setCache }) {
  if (cache) return cache;
  const bucket = process.env.CORPUS_BUCKET;
  const key = process.env[envKey];
  if (!bucket || !key) {
    logEvent('info', disabledEvent, { has_bucket: Boolean(bucket), has_key: Boolean(key) });
    const empty = { ...EMPTY_CORPUS };
    setCache(empty);
    return empty;
  }
  const start = performance.now();
  try {
    const response = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
    const loaded = JSON.parse(await response.Body.transformToString());
    setCache(loaded);
    logEvent('info', 'corpus_loaded', {
      source: 's3',
      scope: kind,
      bucket,
      key,
      chunk_count: loaded.chunk_count || loaded.chunks?.length || 0,
      embedding_dimensions: loaded.embedding_dimensions,
      duration_ms: Math.round(performance.now() - start)
    });
  } catch (error) {
    logEvent('warning', failedEvent, { key, error_type: error.constructor?.name || 'Error' });
    return { ...EMPTY_CORPUS };
  }
  return cache || (kind === 'blog' ? blogCorpusCache : podcastCorpusCache);
}

// Optional non-WT corpora load lazily and cache separately from the WT corpus.
// When an env key is unset, return an empty corpus so source-specific requests
// degrade to no hits.
async function loadBlogCorpus() {
  return loadOptionalCorpus({
    kind: 'blog',
    envKey: 'BLOG_CORPUS_KEY',
    disabledEvent: 'blog_corpus_disabled',
    failedEvent: 'blog_corpus_load_failed',
    cache: blogCorpusCache,
    setCache: (value) => { blogCorpusCache = value; }
  });
}

async function loadPodcastCorpus() {
  return loadOptionalCorpus({
    kind: 'podcast',
    envKey: 'PODCAST_CORPUS_KEY',
    disabledEvent: 'podcast_corpus_disabled',
    failedEvent: 'podcast_corpus_load_failed',
    cache: podcastCorpusCache,
    setCache: (value) => { podcastCorpusCache = value; }
  });
}

async function loadGraph() {
  if (graphCache) return graphCache;
  const bucket = process.env.CORPUS_BUCKET;
  const key = process.env.GRAPH_KEY || 'librarian/graph.json';
  if (!bucket) {
    graphCache = {};
    return graphCache;
  }
  try {
    const response = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
    graphCache = JSON.parse(await response.Body.transformToString());
    logEvent('info', 'graph_loaded', { source: 's3', bucket, key, issue_count: Object.keys(graphCache.issues || {}).length });
  } catch (error) {
    graphCache = {};
    logEvent('warning', 'graph_load_failed', { key, error_type: error.constructor?.name || 'Error' });
  }
  return graphCache;
}

function tokenize(text) {
  return Array.from(String(text || '').matchAll(TOKEN_RE), (match) => match[0].toLowerCase());
}

function buildLexicalIndex(corpus) {
  const documentFrequency = new Map();
  const indexed = (corpus.chunks || []).map((chunk) => {
    const terms = tokenize([chunk.subject, chunk.section, chunk.text].join(' '));
    const termCounts = new Map();
    for (const term of terms) termCounts.set(term, (termCounts.get(term) || 0) + 1);
    for (const term of termCounts.keys()) documentFrequency.set(term, (documentFrequency.get(term) || 0) + 1);
    return { ...chunk, _terms: termCounts };
  });
  const total = Math.max(indexed.length, 1);
  for (const chunk of indexed) {
    const vector = new Map();
    let norm = 0;
    for (const [term, count] of chunk._terms.entries()) {
      const weight = (1 + Math.log(count)) * Math.log(1 + total / (1 + (documentFrequency.get(term) || 0)));
      vector.set(term, weight);
      norm += weight * weight;
    }
    chunk._vector = vector;
    chunk._norm = Math.sqrt(norm) || 1;
  }
  return indexed;
}

async function indexedChunks(kind = 'weekly_thing') {
  if (kind === 'blog') {
    if (!blogIndexedCache) blogIndexedCache = buildLexicalIndex(await loadCorpus('blog'));
    return blogIndexedCache;
  }
  if (kind === 'podcast') {
    if (!podcastIndexedCache) podcastIndexedCache = buildLexicalIndex(await loadCorpus('podcast'));
    return podcastIndexedCache;
  }
  if (!indexedCache) indexedCache = buildLexicalIndex(await loadCorpus('weekly_thing'));
  return indexedCache;
}

function cosine(left, right) {
  if (!left?.length || !right?.length || left.length !== right.length) return 0;
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < left.length; index += 1) {
    dot += left[index] * right[index];
    leftNorm += left[index] * left[index];
    rightNorm += right[index] * right[index];
  }
  return leftNorm && rightNorm ? dot / (Math.sqrt(leftNorm) * Math.sqrt(rightNorm)) : 0;
}

async function embedQuery(query, model, dimensions) {
  const start = performance.now();
  const response = await bedrock.send(new InvokeModelCommand({
    modelId: model,
    accept: 'application/json',
    contentType: 'application/json',
    body: JSON.stringify({ texts: [query], input_type: 'search_query', truncate: 'END' })
  }));
  const data = JSON.parse(new TextDecoder().decode(response.body));
  if (!data.embeddings?.length) throw new Error('Bedrock embedding response did not include embeddings');
  logEvent('info', 'query_embedded', { model, dimensions, duration_ms: Math.round(performance.now() - start) });
  return data.embeddings[0];
}

function publicChunk(chunk) {
  return Object.fromEntries(Object.entries(chunk).filter(([key]) => key !== 'embedding' && !key.startsWith('_')));
}

function sourceAgeLabel(source) {
  const value = source.publish_date || '';
  const published = value ? new Date(value) : null;
  if (!published || Number.isNaN(published.getTime())) return 'unknown age';
  const days = Math.max(0, (Date.now() - published.getTime()) / 86400000);
  if (days < 45) return 'recent';
  if (days < 365) return `about ${Math.max(Math.round(days / 30), 1)} months old`;
  return `about ${Math.max(Math.round(days / 365), 1)} years old`;
}

function compactSource(source, textLimit = 900) {
  return {
    issue_number: source.issue_number,
    source_kind: source.source_kind,
    subject: source.subject,
    publish_date: source.publish_date,
    issue_year: source.issue_year,
    section: source.section,
    age: source.age_label || sourceAgeLabel(source),
    score: source._rerank_score || source._retrieval_score,
    reason: source.retrieval_reason || (source.retrieval_modes || []).join(', '),
    url: source.url,
    transcript_url: source.transcript_url,
    audio_url: source.audio_url,
    episode_number: source.episode_number,
    show: source.show,
    topics: source.topics || [],
    // Present only on blog chunks that a WT issue Journal linked back to —
    // lets the agent cross-reference ("Jamie also featured this in WT###").
    also_in_issues: source.also_in_issues,
    text: String(source.text || '').slice(0, textLimit)
  };
}

function sourceKind(item) {
  if (item?.source_kind) return item.source_kind;
  if (!item?.issue_number && item?.url) return 'external';
  return 'chunk';
}

function sourceHeader(source) {
  const kind = sourceKind(source);
  if (kind === 'blog') return `thingelstad.com blog: ${source.subject || ''}`;
  if (kind === 'podcast') {
    const episode = source.episode_number ? ` episode ${source.episode_number}` : '';
    return `Another Thing podcast${episode}: ${source.subject || ''}`;
  }
  return `Weekly Thing #${source.issue_number}: ${source.subject || ''}`;
}

async function rerankSources(query, sources, limit = 8) {
  if (!sources.length || !truthyEnv('LIBRARIAN_RERANK_ENABLED', '1')) return sources.slice(0, limit);
  const start = performance.now();
  const top = sources.slice(0, Math.max(limit * 5, 40));
  const rerankInputs = top.map((source) => {
    const header = sourceHeader(source);
    return {
      type: 'INLINE',
      inlineDocumentSource: {
        type: 'TEXT',
        textDocument: {
          text: [
            header,
            `Date: ${source.publish_date || ''}`,
            `Section: ${source.section || ''}`,
            `Topics: ${(source.topics || []).join(', ')}`,
            String(source.text || '').replace(/\s+/g, ' ').slice(0, 1800)
          ].join('\n')
        }
      }
    };
  });
  try {
    const data = await bedrockAgentRuntime.send(new RerankCommand({
      queries: [{ type: 'TEXT', textQuery: { text: query } }],
      sources: rerankInputs,
      rerankingConfiguration: {
        type: 'BEDROCK_RERANKING_MODEL',
        bedrockRerankingConfiguration: {
          numberOfResults: Math.min(rerankInputs.length, Math.max(limit, 8)),
          modelConfiguration: { modelArn: rerankModelArn() }
        }
      }
    }));
    const ordered = [];
    for (const item of data.results || []) {
      const index = Number(item.index);
      if (index >= 0 && index < top.length) {
        ordered.push({ ...top[index], _rerank_score: Number(item.relevanceScore ?? 0) });
      }
    }
    if (ordered.length) {
      logEvent('info', 'rerank_completed', { model: rerankModel(), candidate_count: top.length, result_count: ordered.length, duration_ms: Math.round(performance.now() - start) });
      return ordered;
    }
  } catch (error) {
    logEvent('warning', 'rerank_failed', { model: rerankModel(), error_type: error.constructor?.name || 'Error' });
  }
  return sources.slice(0, limit);
}

async function embedForCorpus(query, corpus) {
  const model = corpus.embedding_model || embeddingModel();
  const dimensions = Number(corpus.embedding_dimensions || DEFAULT_EMBEDDING_DIMENSIONS);
  return embedQuery(query, model, dimensions);
}

// Pure cosine scoring over one corpus's embedded chunks. Attaches
// _retrieval_score so callers can merge candidates from multiple corpora and
// re-sort before a single rerank (mixed scopes).
function semanticScore(corpus, queryEmbedding, limit) {
  const chunks = (corpus.chunks || []).filter((chunk) => chunk.embedding);
  if (!chunks.length) return [];
  return chunks
    .map((chunk) => [cosine(queryEmbedding, chunk.embedding), chunk])
    .filter(([score]) => score > 0)
    .sort(([left], [right]) => right - left)
    .slice(0, limit)
    .map(([score, chunk]) => ({ ...publicChunk(chunk), _retrieval_score: score }));
}

async function retrieveLexical(query, limit = 8, kind = 'weekly_thing') {
  const start = performance.now();
  const queryTerms = new Map();
  for (const term of tokenize(query)) queryTerms.set(term, (queryTerms.get(term) || 0) + 1);
  if (!queryTerms.size) return [];
  const scored = [];
  for (const chunk of await indexedChunks(kind)) {
    let score = 0;
    for (const [term, count] of queryTerms.entries()) score += (chunk._vector.get(term) || 0) * count;
    if (score > 0) scored.push([score / chunk._norm, chunk]);
  }
  const result = scored.sort(([left], [right]) => right - left).slice(0, limit).map(([score, chunk]) => ({ ...publicChunk(chunk), _retrieval_score: score }));
  logEvent('info', 'retrieval_completed', { mode: 'lexical', scope: kind, result_count: result.length, duration_ms: Math.round(performance.now() - start) });
  return result;
}

function parseYearRange(value) {
  if (!value) return [null, null];
  if (Array.isArray(value) && value.length >= 2) return [Number(value[0]) || null, Number(value[1]) || null];
  if (typeof value === 'object') return [Number(value.start || value.from) || null, Number(value.end || value.to) || null];
  const years = String(value).match(/\b(?:19|20)\d{2}\b/g)?.map(Number) || [];
  if (years.length > 1) return [Math.min(...years), Math.max(...years)];
  if (years.length === 1) return [years[0], years[0]];
  return [null, null];
}

function matchesFilters(source, { yearRange, section } = {}) {
  const [startYear, endYear] = parseYearRange(yearRange);
  const year = Number(source.issue_year || 0);
  if (startYear && (!year || year < startYear)) return false;
  if (endYear && (!year || year > endYear)) return false;
  if (section && !String(source.section || '').toLowerCase().includes(String(section).toLowerCase())) return false;
  return true;
}

function withAgeLabel(sources) {
  return sources.map((source) => ({ ...source, age_label: source.age_label || sourceAgeLabel(source) }));
}

// Scope is enforced HERE — by which corpus/corpora we scan, not by a
// post-filter. weekly_thing scans the WT corpus (identical to today);
// blog/podcast scan their own corpora; mixed scopes gather candidates from
// each and rerank the union once. matchesFilters only applies year/section.
async function retrieve(query, limit = 8, filters = {}) {
  const kinds = scopeKinds(filters.scope);
  const candidateLimit = Math.max(limit * 5, 40);
  const byScore = (a, b) => (b._retrieval_score || 0) - (a._retrieval_score || 0);
  try {
    let queryEmbedding = null;
    let semantic = [];
    for (const kind of kinds) {
      const corpus = await loadCorpus(kind);
      if (!(corpus.chunks || []).some((chunk) => chunk.embedding)) continue;
      if (!queryEmbedding) queryEmbedding = await embedForCorpus(query, corpus);
      semantic.push(...semanticScore(corpus, queryEmbedding, candidateLimit));
    }
    semantic = semantic.filter((source) => matchesFilters(source, filters)).sort(byScore);
    if (semantic.length) return withAgeLabel((await rerankSources(query, semantic, limit)).slice(0, limit));
  } catch (error) {
    logEvent('error', 'semantic_retrieval_failed', errorFields(error, {
      scope: normalizeScope(filters.scope),
      source_kinds: kinds,
      query_chars: String(query || '').length
    }));
  }
  let lexical = [];
  for (const kind of kinds) lexical.push(...(await retrieveLexical(query, candidateLimit, kind)));
  lexical = lexical.filter((source) => matchesFilters(source, filters)).sort(byScore);
  return withAgeLabel((await rerankSources(query, lexical, limit)).slice(0, limit));
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

function isExternalSource(item) {
  return ['blog', 'podcast'].includes(item?.source_kind) || (!item?.issue_number && Boolean(item?.url));
}

function citationsFor(chunks) {
  const seen = new Set();
  const citations = [];
  for (const chunk of chunks) {
    // WT chunks dedupe by issue+section; external sources have no issue
    // number, so dedupe them by source kind + URL.
    const external = isExternalSource(chunk);
    const key = external ? `${chunk.source_kind || 'external'}\0${chunk.url || ''}` : `${chunk.issue_number}\0${chunk.section || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    citations.push({
      issue_number: chunk.issue_number ?? null,
      source_kind: chunk.source_kind || (external ? 'external' : 'chunk'),
      subject: chunk.subject,
      publish_date: chunk.publish_date,
      section: chunk.section,
      url: chunk.url,
      transcript_url: chunk.transcript_url,
      audio_url: chunk.audio_url,
      episode_number: chunk.episode_number,
      show: chunk.show,
      also_in_issues: chunk.also_in_issues
    });
  }
  return citations;
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

function issueKey(value) {
  return String(value || '').replace(/^#/, '').trim();
}

async function issueByNumber(number) {
  const wanted = issueKey(number);
  const corpus = await loadCorpus();
  return (corpus.issues || []).find((issue) => issueKey(issue.number) === wanted);
}

async function weeklyIssueCatalog() {
  const corpus = await loadCorpus('weekly_thing');
  const catalog = new Map();
  for (const issue of corpus.issues || []) {
    const number = issueKey(issue.number || issue.issue_number);
    if (number) catalog.set(number, issue);
  }
  return catalog;
}

async function issueSections(issue) {
  if (Array.isArray(issue.sections) && issue.sections.length) return issue.sections;
  const corpus = await loadCorpus();
  const grouped = new Map();
  for (const chunk of corpus.chunks || []) {
    if (issueKey(chunk.issue_number) !== issueKey(issue.number)) continue;
    const name = chunk.section || 'Issue';
    grouped.set(name, [...(grouped.get(name) || []), chunk.text || '']);
  }
  return Array.from(grouped.entries(), ([name, parts]) => ({ name, text: parts.join('\n\n') }));
}

function normalizedDomain(value) {
  return String(value || '').toLowerCase().replace(/^https?:\/\//, '').split('/')[0].replace(/^www\./, '');
}

const CORPUS_BY_DOMAIN = {
  'thingelstad.com': 'blog',
  'micro.thingelstad.com': 'blog',
  'weekly.thingelstad.com': 'weekly_thing',
  'another.thingelstad.com': 'podcast'
};
const CORPUS_SOURCE_KINDS = new Set(['blog', 'weekly_thing', 'podcast']);

function normalizeSourceKind(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (!raw) return '';
  if (['weekly_thing', 'weeklything', 'newsletter', 'issue', 'issues', 'archive', 'wt', 'chunk'].includes(raw)) return 'weekly_thing';
  if (['blog', 'thingelstad', 'thingelstad_com', 'post', 'posts', 'micropost'].includes(raw)) return 'blog';
  if (['podcast', 'podcasts', 'another', 'another_thing', 'episode', 'episodes'].includes(raw)) return 'podcast';
  if (raw === 'site') return 'site';
  return '';
}

function linkCorpusKind(link) {
  return normalizeSourceKind(link.corpus_kind || link.source_kind || (link.issue_number ? 'weekly_thing' : ''));
}

function boolFilter(value) {
  if (value === true || value === false) return value;
  const raw = String(value ?? '').trim().toLowerCase();
  if (!raw) return null;
  if (['true', '1', 'yes', 'resolved'].includes(raw)) return true;
  if (['false', '0', 'no', 'unresolved'].includes(raw)) return false;
  return null;
}

function inferredLinkKind(link) {
  if (link.link_kind) return link.link_kind;
  const domain = normalizedDomain(link.domain || link.url || '');
  return domain.endsWith('thingelstad.com') ? 'internal' : 'external';
}

function inferredTargetSourceKind(link, sourceKind, targetResolved) {
  const explicit = normalizeSourceKind(link.target_source_kind || '');
  if (explicit) return explicit;
  if (targetResolved) return 'blog';
  const domain = normalizedDomain(link.domain || link.url || '');
  const target = CORPUS_BY_DOMAIN[domain] || (domain.endsWith('.thingelstad.com') ? 'site' : '');
  return target && target !== sourceKind ? target : undefined;
}

function normalizeLinkRecord(link, kind) {
  const corpusKind = normalizeSourceKind(kind) || linkCorpusKind(link);
  const sourceKind = link.source_kind || (corpusKind === 'blog' ? 'blog' : corpusKind === 'podcast' ? 'podcast' : 'weekly_thing');
  const targetResolved = Boolean(link.target_resolved || link.target_post_url || link.target_microblog_id);
  const targetSourceKind = inferredTargetSourceKind(link, corpusKind, targetResolved);
  const isCrossSource = Boolean(CORPUS_SOURCE_KINDS.has(targetSourceKind) && targetSourceKind !== corpusKind);
  const isInternalSite = targetSourceKind === 'site';
  const linkKind = isCrossSource || isInternalSite ? 'internal' : link.link_kind || inferredLinkKind(link);
  const linkCategory = isCrossSource ? 'cross_source' : isInternalSite ? 'internal_site' : link.link_category || (linkKind === 'external' ? 'external' : targetResolved ? 'resolved_post' : 'internal_unresolved');
  return {
    ...link,
    source_kind: sourceKind,
    corpus_kind: corpusKind,
    subject: link.subject || link.post_subject,
    publish_date: link.publish_date,
    issue_year: link.issue_year || link.post_year,
    source_url: link.issue_url || link.post_url || link.episode_url,
    link_url: link.url,
    link_kind: linkKind,
    link_category: linkCategory,
    target_resolved: targetResolved,
    target_source_kind: targetSourceKind
  };
}

async function linkRecords(scope = 'weekly_thing') {
  const links = [];
  for (const kind of scopeKinds(scope)) {
    const corpus = await loadCorpus(kind);
    if (Array.isArray(corpus.links) && corpus.links.length) {
      links.push(...corpus.links.map((link) => normalizeLinkRecord(link, kind)));
      continue;
    }
    for (const issue of corpus.issues || []) {
      for (const link of issue.links || []) {
        links.push(normalizeLinkRecord({
          ...link,
          issue_number: issue.number,
          subject: issue.subject,
          publish_date: issue.publish_date,
          issue_year: issue.issue_year,
          issue_url: issue.url
        }, kind));
      }
    }
  }
  return links;
}

async function faqReplacements() {
  const corpus = await loadCorpus();
  const issues = (corpus.issues || []).filter((issue) => issue.publish_date);
  const years = issues
    .map((issue) => Number(String(issue.publish_date || '').slice(0, 4)))
    .filter((year) => year > 0);
  const firstYear = years.length ? Math.min(...years) : 2017;
  const latestYear = years.length ? Math.max(...years) : new Date().getUTCFullYear();
  return {
    yearsActive: latestYear - firstYear + 1,
    issueCount: corpus.issue_count || issues.length
  };
}

async function toolSearchFaq(input = {}) {
  const query = String(input.query || '').trim();
  if (!query) return { results: [] };
  const limit = Math.min(Math.max(Number(input.limit || 5), 1), 10);
  return {
    query,
    results: searchFaq(query, {
      limit,
      replacements: await faqReplacements()
    })
  };
}

async function toolSearchArchive(input = {}, { scope } = {}) {
  const query = String(input.query || '').trim();
  if (!query) return { results: [] };
  const limit = Math.min(Math.max(Number(input.limit || 8), 1), 12);
  const results = await retrieve(query, limit, { yearRange: input.year_range, section: input.section, scope });
  return { query, results: results.map((source) => compactSource(source)) };
}

async function toolGetIssue(input = {}) {
  const issue = await issueByNumber(input.number);
  if (!issue) return { error: 'Issue not found.' };
  const sections = await issueSections(issue);
  return {
    issue: {
      number: issue.number,
      subject: issue.subject,
      publish_date: issue.publish_date,
      url: issue.url,
      topics: issue.topics || [],
      sections: sections.map((section) => ({ name: section.name, word_count: tokenize(section.text || '').length })),
      body: String(issue.body || sections.map((section) => `## ${section.name}\n${section.text || ''}`).join('\n\n')).slice(0, 16000)
    }
  };
}

async function toolGetSection(input = {}) {
  const issue = await issueByNumber(input.number);
  const wanted = String(input.section || '').toLowerCase();
  if (!issue || !wanted) return { error: 'Issue or section not found.' };
  const sections = await issueSections(issue);
  const section = sections.find((item) => String(item.name || '').toLowerCase() === wanted || String(item.name || '').toLowerCase().includes(wanted));
  if (!section) return { error: 'Section not found.', available_sections: sections.map((item) => item.name) };
  return { issue_number: issue.number, subject: issue.subject, publish_date: issue.publish_date, section: section.name, url: issue.url, text: String(section.text || '').slice(0, 12000) };
}

async function toolGetSource(input = {}, context = {}) {
  const bundle = await findSourceBundle(input, context);
  if (!bundle) return { error: 'Source not found in the active source scope.' };
  const { kind, record, chunks, links } = bundle;
  const wantedSection = String(input.section || '').trim();
  let sections = [];
  let body = '';
  if (kind === 'weekly_thing') {
    const issue = await issueByNumber(record.issue_number);
    const issueSectionRows = await issueSections(issue || record);
    const wanted = wantedSection.toLowerCase();
    sections = issueSectionRows
      .filter((section) => !wanted || String(section.name || '').toLowerCase().includes(wanted))
      .map((section) => ({
        name: section.name,
        word_count: section.word_count || tokenize(section.text || '').length,
        text: String(section.text || '').slice(0, 14000)
      }));
    body = String(issue?.body || sections.map((section) => `## ${section.name}\n${section.text || ''}`).join('\n\n')).slice(0, 22000);
  } else {
    sections = sectionsFromChunks(chunks, wantedSection);
    body = sourceTextFromChunks(chunks, wantedSection).slice(0, 22000);
  }
  return {
    source: {
      ...compactContentRecord(record),
      word_count: tokenize(body).length,
      section_filter: wantedSection || null,
      sections: sections.map((section) => ({ name: section.name, word_count: section.word_count })),
      links: links.slice(0, 40).map(compactLink),
      body,
      section_texts: sections
    }
  };
}

async function toolFindLinks(input = {}, { scope } = {}) {
  const domain = normalizedDomain(input.domain || '');
  const topic = String(input.topic || '').toLowerCase().trim();
  const linkKind = String(input.link_kind || '').toLowerCase().trim();
  const sourceKind = normalizeSourceKind(input.source_kind || input.source || '');
  const linkCategory = String(input.link_category || '').toLowerCase().trim();
  const targetResolved = boolFilter(input.target_resolved);
  const [startYear, endYear] = parseYearRange(input.year_range);
  const limit = Math.min(Math.max(Number(input.limit || 20), 1), 50);
  const kinds = scopeKinds(scope);
  const graph = topic && kinds.includes('weekly_thing') ? await loadGraph() : {};
  const issueMatches = topic ? new Set(graph.entity_index?.[topic] || []) : new Set();
  const results = [];
  const filteredLinks = [];
  for (const link of await linkRecords(scope)) {
    const linkDomain = normalizedDomain(link.domain || link.url || '');
    const linkSourceKind = linkCorpusKind(link);
    const year = Number(link.issue_year || link.post_year || 0);
    if (sourceKind && linkSourceKind !== sourceKind) continue;
    if (domain && !linkDomain.includes(domain)) continue;
    if (linkKind && link.link_kind !== linkKind) continue;
    if (linkCategory && String(link.link_category || '').toLowerCase() !== linkCategory) continue;
    if (targetResolved !== null && Boolean(link.target_resolved) !== targetResolved) continue;
    if (startYear && (!year || year < startYear)) continue;
    if (endYear && (!year || year > endYear)) continue;
    const haystack = [link.text, link.title, link.section, link.heading_context, link.context, link.domain].join(' ').toLowerCase();
    if (topic && !haystack.includes(topic) && !issueMatches.has(issueKey(link.issue_number))) continue;
    filteredLinks.push(link);
    if (results.length < limit) {
      const sourceUrl = link.source_url || (link.issue_number ? `/archive/${link.issue_number}/` : link.post_url || link.url);
      results.push({
        issue_number: link.issue_number ?? null,
        source_kind: link.source_kind,
        corpus_kind: linkSourceKind,
        subject: link.subject,
        publish_date: link.publish_date,
        section: link.section,
        domain: link.domain,
        link_text: link.text || link.title || link.heading_context,
        context: link.context || link.heading_context,
        url: sourceUrl,
        link_url: link.link_url || link.url,
        destination_url: link.link_url || link.url,
        link_kind: link.link_kind,
        link_category: link.link_category,
        target_resolved: Boolean(link.target_resolved),
        microblog_id: link.microblog_id,
        target_blog_path: link.target_blog_path,
        target_source_kind: link.target_source_kind,
        target_microblog_id: link.target_microblog_id,
        target_post_url: link.target_post_url,
        target_subject: link.target_subject,
        target_publish_date: link.target_publish_date,
        episode_number: link.episode_number,
        show: link.show
      });
    }
  }
  const counts = new Map();
  const countsBySource = new Map();
  const countsByKind = new Map();
  const countsByCategory = new Map();
  for (const link of filteredLinks) {
    const linkSourceKind = linkCorpusKind(link) || 'unknown';
    countsBySource.set(linkSourceKind, (countsBySource.get(linkSourceKind) || 0) + 1);
    countsByKind.set(link.link_kind || 'unknown', (countsByKind.get(link.link_kind || 'unknown') || 0) + 1);
    countsByCategory.set(link.link_category || 'unknown', (countsByCategory.get(link.link_category || 'unknown') || 0) + 1);
    if (!domain && !linkKind && link.link_kind === 'internal') continue;
    const linkDomain = normalizedDomain(link.domain || link.url || '');
    if (linkDomain) counts.set(linkDomain, (counts.get(linkDomain) || 0) + 1);
  }
  const top_domains = Array.from(counts.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 20).map(([domainName, count]) => ({ domain: domainName, count }));
  const countList = (map, key) => Array.from(map.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name, count]) => ({ [key]: name, count }));
  return {
    results,
    total_count: filteredLinks.length,
    top_domains,
    counts_by_source: countList(countsBySource, 'source_kind'),
    counts_by_link_kind: countList(countsByKind, 'link_kind'),
    counts_by_link_category: countList(countsByCategory, 'link_category')
  };
}

async function toolDomainHistory(input = {}, context = {}) {
  if (!input.domain) return { error: 'domain is required', results: [] };
  return toolFindLinks({
    domain: input.domain,
    source_kind: input.source_kind || input.source,
    link_kind: input.link_kind,
    link_category: input.link_category,
    target_resolved: input.target_resolved,
    year_range: input.year_range,
    limit: input.limit || 80
  }, context);
}

function latestByDate(items) {
  return [...items]
    .filter((item) => item.publish_date)
    .sort((a, b) => String(b.publish_date || '').localeCompare(String(a.publish_date || '')));
}

function contentRecords(corpus, kind) {
  if (kind === 'blog') {
    return (corpus.posts || []).map((post) => ({
      source_kind: 'blog',
      microblog_id: post.microblog_id,
      subject: post.subject,
      publish_date: post.publish_date,
      url: post.url,
      section: post.post_kind === 'micropost' ? 'Micropost' : 'Blog post',
      also_in_issues: post.also_in_issues,
      domains: post.domains || []
    }));
  }
  if (kind === 'podcast') {
    return (corpus.episodes || []).map((episode) => ({
      source_kind: 'podcast',
      episode_number: episode.number,
      show: episode.show,
      subject: episode.subject,
      publish_date: episode.publish_date,
      url: episode.url,
      transcript_url: episode.transcript_url,
      audio_url: episode.audio_url,
      section: 'Episode',
      domains: episode.domains || []
    }));
  }
  return (corpus.issues || []).map((issue) => ({
    source_kind: 'weekly_thing',
    issue_number: issue.number,
    subject: issue.subject,
    publish_date: issue.publish_date,
    url: issue.url,
    section: 'Issue',
    topics: issue.topics || [],
    domains: issue.domains || []
  }));
}

function sourceRecordKey(record) {
  const kind = normalizeSourceKind(record?.source_kind || '') || (record?.episode_number ? 'podcast' : record?.microblog_id ? 'blog' : record?.issue_number ? 'weekly_thing' : '');
  if (kind === 'weekly_thing') return `weekly_thing\0${issueKey(record.issue_number || record.number)}`;
  if (kind === 'blog') return `blog\0${record.microblog_id || urlKey(record.url)}`;
  if (kind === 'podcast') return `podcast\0${record.episode_number || record.number || urlKey(record.url)}`;
  return `${kind || 'unknown'}\0${urlKey(record?.url)}`;
}

function urlKey(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    const url = new URL(raw, 'https://thingelstad.com');
    let host = url.hostname.toLowerCase().replace(/^www\./, '');
    if (host === 'micro.thingelstad.com') host = 'thingelstad.com';
    return `${host}${url.pathname.replace(/\/$/, '')}`.toLowerCase();
  } catch {
    return raw.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/$/, '');
  }
}

function sourceKeyFromChunk(chunk, fallbackKind = '') {
  const kind = normalizeSourceKind(chunk?.source_kind || fallbackKind) || fallbackKind;
  if (kind === 'weekly_thing' || chunk?.issue_number) return `weekly_thing\0${issueKey(chunk.issue_number)}`;
  if (kind === 'blog') return `blog\0${chunk.microblog_id || urlKey(chunk.url)}`;
  if (kind === 'podcast') return `podcast\0${chunk.episode_number || urlKey(chunk.url)}`;
  return `${kind || 'unknown'}\0${urlKey(chunk?.url)}`;
}

function sourceKeyFromLink(link) {
  const kind = linkCorpusKind(link);
  if (kind === 'weekly_thing' || link.issue_number) return `weekly_thing\0${issueKey(link.issue_number)}`;
  if (kind === 'blog') return `blog\0${link.microblog_id || urlKey(link.post_url || link.source_url || link.url)}`;
  if (kind === 'podcast') return `podcast\0${link.episode_number || urlKey(link.episode_url || link.source_url || link.url)}`;
  return `${kind || 'unknown'}\0${urlKey(link.source_url)}`;
}

function groupBySourceKey(items, keyFn) {
  const map = new Map();
  for (const item of items || []) {
    const key = keyFn(item);
    if (!key) continue;
    map.set(key, [...(map.get(key) || []), item]);
  }
  return map;
}

function recordYear(record) {
  return Number(record.issue_year || record.post_year || String(record.publish_date || '').match(/\b(?:19|20)\d{2}\b/)?.[0] || 0);
}

function compactContentRecord(record) {
  return {
    source_kind: record.source_kind,
    issue_number: record.issue_number ?? null,
    microblog_id: record.microblog_id,
    episode_number: record.episode_number,
    show: record.show,
    subject: record.subject,
    publish_date: record.publish_date,
    year: recordYear(record) || null,
    section: record.section,
    url: record.url,
    transcript_url: record.transcript_url,
    audio_url: record.audio_url,
    topics: record.topics || [],
    domains: record.domains || [],
    also_in_issues: record.also_in_issues
  };
}

function compactLink(link) {
  return {
    source_kind: link.source_kind,
    corpus_kind: linkCorpusKind(link),
    issue_number: link.issue_number ?? null,
    microblog_id: link.microblog_id,
    episode_number: link.episode_number,
    show: link.show,
    subject: link.subject,
    publish_date: link.publish_date,
    section: link.section,
    domain: link.domain,
    link_text: link.text || link.title || link.heading_context,
    context: link.context || link.heading_context,
    url: link.source_url || (link.issue_number ? `/archive/${link.issue_number}/` : link.post_url || link.episode_url || link.url),
    destination_url: link.link_url || link.url,
    link_kind: link.link_kind,
    link_category: link.link_category,
    target_resolved: Boolean(link.target_resolved),
    target_source_kind: link.target_source_kind,
    target_microblog_id: link.target_microblog_id,
    target_post_url: link.target_post_url,
    target_subject: link.target_subject,
    target_publish_date: link.target_publish_date
  };
}

function sourceTextFromChunks(chunks, section = '') {
  const wanted = String(section || '').toLowerCase().trim();
  return (chunks || [])
    .filter((chunk) => !wanted || String(chunk.section || '').toLowerCase().includes(wanted))
    .map((chunk) => String(chunk.text || '').trim())
    .filter(Boolean)
    .join('\n\n');
}

function sectionsFromChunks(chunks, section = '') {
  const wanted = String(section || '').toLowerCase().trim();
  const grouped = new Map();
  for (const chunk of chunks || []) {
    if (wanted && !String(chunk.section || '').toLowerCase().includes(wanted)) continue;
    const name = chunk.section || 'Source';
    grouped.set(name, [...(grouped.get(name) || []), String(chunk.text || '').trim()].filter(Boolean));
  }
  return Array.from(grouped.entries(), ([name, parts]) => ({
    name,
    word_count: tokenize(parts.join(' ')).length,
    text: parts.join('\n\n').slice(0, 14000)
  }));
}

function inferSourceKindFromInput(input = {}) {
  const explicit = normalizeSourceKind(input.source_kind || input.source || '');
  if (explicit) return explicit;
  if (input.issue_number || input.number || input.issue) return 'weekly_thing';
  if (input.microblog_id || input.post_id) return 'blog';
  if (input.episode_number || input.episode) return 'podcast';
  const domain = normalizedDomain(input.url || input.permalink || '');
  return CORPUS_BY_DOMAIN[domain] || '';
}

function recordMatchesIdentifier(record, input = {}) {
  const issue = input.issue_number ?? input.issue ?? input.number;
  const microblogId = input.microblog_id ?? input.post_id;
  const episode = input.episode_number ?? input.episode ?? input.number;
  const url = input.url || input.permalink;
  if (record.source_kind === 'weekly_thing' && issue !== undefined && issueKey(record.issue_number) === issueKey(issue)) return true;
  if (record.source_kind === 'blog' && microblogId !== undefined && String(record.microblog_id) === String(microblogId)) return true;
  if (record.source_kind === 'podcast' && episode !== undefined && String(record.episode_number) === String(episode)) return true;
  if (url && urlKey(record.url) === urlKey(url)) return true;
  return false;
}

async function findSourceBundle(input = {}, { scope } = {}) {
  const requestedKind = inferSourceKindFromInput(input);
  const kinds = scopeKinds(scope).filter((kind) => !requestedKind || kind === requestedKind);
  for (const kind of kinds) {
    const corpus = await loadCorpus(kind);
    const records = contentRecords(corpus, kind);
    const record = records.find((item) => recordMatchesIdentifier(item, input));
    if (!record) continue;
    const key = sourceRecordKey(record);
    const chunks = groupBySourceKey(corpus.chunks || [], (chunk) => sourceKeyFromChunk(chunk, kind)).get(key) || [];
    const links = (await linkRecords(kind)).filter((link) => sourceKeyFromLink(link) === key);
    return { kind, corpus, record, key, chunks, links };
  }
  return null;
}

function issueList(values) {
  return (values || [])
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
}

function summarizeDomains(links, limit = 12) {
  const counts = new Map();
  for (const link of links || []) {
    if ((link.link_kind || inferredLinkKind(link)) === 'internal') continue;
    const domain = normalizedDomain(link.domain || link.url || '');
    if (domain) counts.set(domain, (counts.get(domain) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([domain, count]) => ({ domain, count }));
}

async function toolCorpusStats(input = {}, { scope } = {}) {
  const requestedSource = normalizeSourceKind(input.source_kind || input.source || '');
  const kinds = scopeKinds(scope).filter((kind) => !requestedSource || kind === requestedSource);
  const sources = [];
  for (const kind of kinds) {
    const corpus = await loadCorpus(kind);
    const records = latestByDate(contentRecords(corpus, kind));
    const links = await linkRecords(kind);
    const linkKindCounts = new Map();
    const categoryCounts = new Map();
    for (const link of links) {
      const linkKind = link.link_kind || inferredLinkKind(link);
      linkKindCounts.set(linkKind, (linkKindCounts.get(linkKind) || 0) + 1);
      const category = link.link_category || (linkKind === 'external' ? 'external' : 'internal_unresolved');
      categoryCounts.set(category, (categoryCounts.get(category) || 0) + 1);
    }
    const countList = (map, key) => Array.from(map.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([name, count]) => ({ [key]: name, count }));
    const countsByYear = countsByPublishYear(records);
    const stats = {
      source_kind: kind,
      generated_at: corpus.generated_at,
      item_count: kind === 'blog' ? corpus.post_count || records.length : kind === 'podcast' ? corpus.episode_count || records.length : corpus.issue_count || records.length,
      chunk_count: corpus.chunk_count || (corpus.chunks || []).length,
      link_count: corpus.link_count || links.length,
      oldest: records[records.length - 1] || null,
      newest: records[0] || null,
      counts_by_year: countsByYear,
      year_count_summary: yearCountSummary(countsByYear),
      yearly_signals: yearlyContentSignals(records, { chunks: corpus.chunks || [] }),
      top_domains: summarizeDomains(links),
      counts_by_link_kind: countList(linkKindCounts, 'link_kind'),
      counts_by_link_category: countList(categoryCounts, 'link_category')
    };
    if (kind === 'weekly_thing') {
      stats.issue_count = corpus.issue_count || records.length;
      stats.content_item_count = records.length;
    }
    if (kind === 'blog') {
      const withIssueRefs = records.filter((record) => issueList(record.also_in_issues).length);
      const issueCounts = new Map();
      for (const record of withIssueRefs) {
        for (const issue of issueList(record.also_in_issues)) {
          issueCounts.set(String(issue), (issueCounts.get(String(issue)) || 0) + 1);
        }
      }
      stats.post_count = corpus.post_count || records.length;
      stats.posts_with_also_in_issues_count = withIssueRefs.length;
      stats.newest_also_in_issues = withIssueRefs[0] || null;
      stats.also_in_issue_counts = countList(issueCounts, 'issue_number');
    }
    if (kind === 'podcast') {
      stats.episode_count = corpus.episode_count || records.length;
    }
    sources.push(stats);
  }
  return { scope: normalizeScope(scope), sources };
}

async function toolLatestContent(input = {}, { scope } = {}) {
  const requestedSource = normalizeSourceKind(input.source_kind || input.source || '');
  const limit = Math.min(Math.max(Number(input.limit || 10), 1), 30);
  const hasAlsoInIssues = boolFilter(input.has_also_in_issues);
  const alsoInIssue = input.also_in_issue ?? input.issue_number;
  const items = [];
  for (const kind of scopeKinds(scope)) {
    if (requestedSource && kind !== requestedSource) continue;
    const corpus = await loadCorpus(kind);
    items.push(...contentRecords(corpus, kind));
  }
  const filtered = items.filter((item) => {
    const refs = issueList(item.also_in_issues);
    if (hasAlsoInIssues !== null && Boolean(refs.length) !== hasAlsoInIssues) return false;
    if (alsoInIssue !== undefined && alsoInIssue !== null && String(alsoInIssue).trim()) {
      const wanted = Number(issueKey(alsoInIssue));
      if (!Number.isFinite(wanted) || !refs.includes(wanted)) return false;
    }
    return true;
  });
  return {
    scope: normalizeScope(scope),
    source_kind: requestedSource || null,
    has_also_in_issues: hasAlsoInIssues,
    also_in_issue: alsoInIssue ?? null,
    results: latestByDate(filtered).slice(0, limit)
  };
}

function sourceMatchesTopic(record, chunks, topic) {
  const raw = String(topic || '').toLowerCase().trim();
  if (!raw) return true;
  const haystack = [
    record.subject,
    record.section,
    (record.topics || []).join(' '),
    (record.domains || []).join(' '),
    ...((chunks || []).slice(0, 12).map((chunk) => chunk.text || ''))
  ].join(' ').toLowerCase();
  if (haystack.includes(raw)) return true;
  const tokens = tokenize(raw).filter((token) => token.length > 2);
  if (!tokens.length) return false;
  const matches = tokens.filter((token) => haystack.includes(token)).length;
  return tokens.length <= 2 ? matches === tokens.length : matches >= Math.ceil(tokens.length * 0.7);
}

function countList(values, key) {
  const map = new Map();
  for (const value of values || []) {
    if (!value) continue;
    map.set(value, (map.get(value) || 0) + 1);
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .map(([name, count]) => ({ [key]: name, count }));
}

async function toolListContent(input = {}, { scope } = {}) {
  const requestedSource = normalizeSourceKind(input.source_kind || input.source || '');
  const [startYear, endYear] = parseYearRange(input.year_range || input.year);
  const topic = String(input.topic || input.entity || input.query || '').trim();
  const domain = normalizedDomain(input.domain || '');
  const linkKind = String(input.link_kind || '').toLowerCase().trim();
  const linkCategory = String(input.link_category || '').toLowerCase().trim();
  const targetResolved = boolFilter(input.target_resolved);
  const hasAlsoInIssues = boolFilter(input.has_also_in_issues);
  const alsoInIssue = input.also_in_issue ?? input.issue_number;
  const limit = Math.min(Math.max(Number(input.limit || 40), 1), 120);
  const results = [];
  const years = [];
  const sources = [];
  for (const kind of scopeKinds(scope)) {
    if (requestedSource && kind !== requestedSource) continue;
    const corpus = await loadCorpus(kind);
    const records = latestByDate(contentRecords(corpus, kind));
    const chunksBySource = groupBySourceKey(corpus.chunks || [], (chunk) => sourceKeyFromChunk(chunk, kind));
    const linksBySource = groupBySourceKey(await linkRecords(kind), sourceKeyFromLink);
    for (const record of records) {
      const year = recordYear(record);
      if (startYear && (!year || year < startYear)) continue;
      if (endYear && (!year || year > endYear)) continue;
      const key = sourceRecordKey(record);
      const chunks = chunksBySource.get(key) || [];
      const links = linksBySource.get(key) || [];
      if (topic && !sourceMatchesTopic(record, chunks, topic)) continue;
      if (domain && ![...(record.domains || []), ...links.map((link) => link.domain || link.url)].some((value) => normalizedDomain(value).includes(domain))) continue;
      if (linkKind && !links.some((link) => link.link_kind === linkKind)) continue;
      if (linkCategory && !links.some((link) => String(link.link_category || '').toLowerCase() === linkCategory)) continue;
      if (targetResolved !== null && !links.some((link) => Boolean(link.target_resolved) === targetResolved)) continue;
      const refs = issueList(record.also_in_issues);
      if (hasAlsoInIssues !== null && Boolean(refs.length) !== hasAlsoInIssues) continue;
      if (alsoInIssue !== undefined && alsoInIssue !== null && String(alsoInIssue).trim()) {
        const wanted = Number(issueKey(alsoInIssue));
        if (!Number.isFinite(wanted) || !refs.includes(wanted)) continue;
      }
      years.push(year);
      sources.push(kind);
      if (results.length < limit) {
        results.push({
          ...compactContentRecord(record),
          link_count: links.length,
          matching_sections: chunks
            .filter((chunk) => !topic || sourceMatchesTopic(record, [chunk], topic))
            .map((chunk) => chunk.section)
            .filter(Boolean)
            .slice(0, 6)
        });
      }
    }
  }
  return {
    scope: normalizeScope(scope),
    source_kind: requestedSource || null,
    total_count: years.length,
    counts_by_year: countList(years, 'year'),
    counts_by_source: countList(sources, 'source_kind'),
    results
  };
}

function contextAround(text, phrase, radius = 240) {
  const index = text.toLowerCase().indexOf(String(phrase).toLowerCase());
  if (index < 0) return '';
  return text.slice(Math.max(0, index - radius), Math.min(text.length, index + String(phrase).length + radius)).trim();
}

async function toolQuoteSearch(input = {}, { scope } = {}) {
  const phrase = String(input.phrase || '').trim();
  if (phrase.length < 3) return { results: [] };
  const limit = Math.min(Math.max(Number(input.limit || 20), 1), 50);
  const needle = phrase.toLowerCase();
  const kinds = scopeKinds(scope);
  const results = [];
  if (kinds.includes('weekly_thing')) {
    const corpus = await loadCorpus('weekly_thing');
    for (const issue of corpus.issues || []) {
      let body = String(issue.body || '');
      if (!body) body = (await issueSections(issue)).map((section) => section.text || '').join('\n\n');
      if (body.toLowerCase().includes(needle)) {
        results.push({ issue_number: issue.number, subject: issue.subject, publish_date: issue.publish_date, url: issue.url, context: contextAround(body, phrase) });
        if (results.length >= limit) break;
      }
    }
  }
  // Non-WT corpora have no issue-shaped records, so exact-phrase search runs
  // over reconstructed source text grouped from chunks.
  for (const kind of kinds.filter((item) => item !== 'weekly_thing')) {
    if (results.length >= limit) break;
    const corpus = await loadCorpus(kind);
    const records = contentRecords(corpus, kind);
    const chunksBySource = groupBySourceKey(corpus.chunks || [], (chunk) => sourceKeyFromChunk(chunk, kind));
    for (const record of records) {
      const chunks = chunksBySource.get(sourceRecordKey(record)) || [];
      const text = sourceTextFromChunks(chunks);
      if (!text.toLowerCase().includes(needle)) continue;
      results.push({
        issue_number: null,
        ...compactContentRecord(record),
        context: contextAround(text, phrase)
      });
      if (results.length >= limit) break;
    }
  }
  return { phrase, results };
}

async function toolListIssues(input = {}) {
  const corpus = await loadCorpus();
  const graph = await loadGraph();
  const topic = String(input.topic || input.entity || '').toLowerCase().trim();
  const issueMatches = topic ? new Set(graph.entity_index?.[topic] || []) : new Set();
  const limit = Math.min(Math.max(Number(input.limit || 60), 1), 120);
  const results = [];
  const topicCounts = new Map();
  const entityCounts = new Map();
  const tropeCounts = new Map();
  for (const issue of corpus.issues || []) {
    const graphIssue = graph.issues?.[issueKey(issue.number)] || {};
    for (const issueTopic of issue.topics || []) topicCounts.set(issueTopic, (topicCounts.get(issueTopic) || 0) + 1);
    for (const entity of (graphIssue.entities || []).slice(0, 20)) {
      const key = String(entity).toLowerCase();
      entityCounts.set(key, (entityCounts.get(key) || 0) + 1);
    }
    for (const trope of (graphIssue.tropes || []).slice(0, 12)) {
      const key = String(trope).toLowerCase();
      tropeCounts.set(key, (tropeCounts.get(key) || 0) + 1);
    }
    if (input.year && Number(issue.issue_year || 0) !== Number(input.year)) continue;
    const haystack = [issue.subject, ...(issue.topics || [])].join(' ').toLowerCase();
    if (topic && !haystack.includes(topic) && !issueMatches.has(issueKey(issue.number))) continue;
    if (results.length < limit) {
      results.push({ number: issue.number, issue_number: issue.number, subject: issue.subject, publish_date: issue.publish_date, url: issue.url, topics: issue.topics || [], entities: (graphIssue.entities || []).slice(0, 12), tropes: (graphIssue.tropes || []).slice(0, 6) });
    }
  }
  const formatCounts = (map, key) => Array.from(map.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 20).map(([name, count]) => ({ [key]: name, count }));
  return { results, topic_counts: formatCounts(topicCounts, 'topic'), entity_counts: formatCounts(entityCounts, 'entity'), trope_counts: formatCounts(tropeCounts, 'trope') };
}

async function toolCompareEras(input = {}, { scope } = {}) {
  const topic = String(input.topic || '').trim();
  if (!topic) return { error: 'topic is required' };
  const limit = Math.min(Math.max(Number(input.limit || 6), 1), 10);
  const first = await retrieve(topic, limit, { yearRange: input.year_a, scope });
  const second = await retrieve(topic, limit, { yearRange: input.year_b, scope });
  return { topic, year_a: input.year_a, year_b: input.year_b, results_a: first.map((item) => compactSource(item, 700)), results_b: second.map((item) => compactSource(item, 700)) };
}

async function toolArchiveLens(input = {}, { scope } = {}) {
  const topic = String(input.topic || input.query || '').trim();
  if (!topic) return { error: 'topic is required' };
  const requestedSource = normalizeSourceKind(input.source_kind || input.source || '');
  const records = [];
  const chunks = [];
  for (const kind of scopeKinds(scope)) {
    if (requestedSource && kind !== requestedSource) continue;
    const corpus = await loadCorpus(kind);
    records.push(...contentRecords(corpus, kind));
    chunks.push(...(corpus.chunks || []).map((chunk) => ({
      ...chunk,
      source_kind: chunk.source_kind || kind
    })));
  }
  return {
    scope: normalizeScope(scope),
    source_kind: requestedSource || null,
    ...buildArchiveLens({
      topic,
      operation: input.operation,
      records,
      chunks,
      yearRange: input.year_range,
      limit: input.limit
    })
  };
}

function targetMatchesSource(link, record) {
  if (!link || !record) return false;
  if (record.source_kind === 'blog') {
    if (link.target_microblog_id && String(link.target_microblog_id) === String(record.microblog_id)) return true;
    if (link.target_post_url && urlKey(link.target_post_url) === urlKey(record.url)) return true;
  }
  if (record.source_kind === 'weekly_thing') {
    const targetUrl = link.target_url || link.url || link.link_url || '';
    if (urlKey(targetUrl).endsWith(`/archive/${issueKey(record.issue_number)}`)) return true;
  }
  if (record.source_kind === 'podcast') {
    const targetUrl = link.target_url || link.url || link.link_url || '';
    if (urlKey(targetUrl) === urlKey(record.url)) return true;
  }
  return false;
}

function scoreRelatedSource(base, candidate, candidateChunks, candidateLinks) {
  if (sourceRecordKey(base.record) === sourceRecordKey(candidate)) return 0;
  const baseDomains = new Set([...(base.record.domains || []), ...(base.links || []).map((link) => normalizedDomain(link.domain || link.url))].filter(Boolean));
  const candidateDomains = new Set([...(candidate.domains || []), ...(candidateLinks || []).map((link) => normalizedDomain(link.domain || link.url))].filter(Boolean));
  let score = 0;
  for (const domain of candidateDomains) if (baseDomains.has(domain)) score += 4;
  const baseTokens = new Set(tokenize([base.record.subject, sourceTextFromChunks(base.chunks).slice(0, 3000)].join(' ')).filter((token) => token.length > 4));
  const candidateTokens = new Set(tokenize([candidate.subject, sourceTextFromChunks(candidateChunks).slice(0, 3000)].join(' ')).filter((token) => token.length > 4));
  for (const token of candidateTokens) if (baseTokens.has(token)) score += 1;
  if (candidate.source_kind !== base.record.source_kind) score += 2;
  return score;
}

async function toolSourceNeighborhood(input = {}, { scope } = {}) {
  const bundle = await findSourceBundle(input, { scope });
  if (!bundle) return { error: 'Source not found in the active source scope.' };
  const allLinks = await linkRecords(scope);
  const incoming = allLinks.filter((link) => sourceKeyFromLink(link) !== bundle.key && targetMatchesSource(link, bundle.record));
  const related = [];
  for (const kind of scopeKinds(scope)) {
    const corpus = await loadCorpus(kind);
    const chunksBySource = groupBySourceKey(corpus.chunks || [], (chunk) => sourceKeyFromChunk(chunk, kind));
    const linksBySource = groupBySourceKey(await linkRecords(kind), sourceKeyFromLink);
    for (const record of contentRecords(corpus, kind)) {
      const key = sourceRecordKey(record);
      if (key === bundle.key) continue;
      const score = scoreRelatedSource(bundle, record, chunksBySource.get(key) || [], linksBySource.get(key) || []);
      if (score > 0) related.push({ score, record, link_count: (linksBySource.get(key) || []).length });
    }
  }
  related.sort((a, b) => b.score - a.score || String(b.record.publish_date || '').localeCompare(String(a.record.publish_date || '')));
  return {
    source: compactContentRecord(bundle.record),
    outgoing_links: bundle.links.slice(0, 30).map(compactLink),
    incoming_links: incoming.slice(0, 30).map(compactLink),
    cross_source_links: [...bundle.links, ...incoming]
      .filter((link) => link.link_category === 'cross_source')
      .slice(0, 30)
      .map(compactLink),
    related_sources: related.slice(0, Math.min(Math.max(Number(input.limit || 8), 1), 20)).map((item) => ({
      ...compactContentRecord(item.record),
      score: item.score,
      link_count: item.link_count
    }))
  };
}

async function toolEntityLens(input = {}, context = {}) {
  const entity = String(input.entity || input.topic || input.query || '').trim();
  if (!entity) return { error: 'entity is required' };
  const operation = input.operation || 'timeline';
  const lens = await toolArchiveLens({
    topic: entity,
    operation,
    source_kind: input.source_kind,
    year_range: input.year_range,
    limit: input.limit || 18
  }, context);
  return {
    entity,
    aliases_checked: [entity],
    ...lens
  };
}

async function toolArchiveGems(input = {}, { scope } = {}) {
  const theme = String(input.theme || input.topic || input.query || '').trim();
  const requestedSource = normalizeSourceKind(input.source_kind || input.source || '');
  const mood = String(input.mood || input.mode || '').toLowerCase().trim();
  const limit = Math.min(Math.max(Number(input.limit || 6), 1), 12);
  if (theme) {
    const lens = await toolArchiveLens({
      topic: theme,
      operation: 'reading_path',
      source_kind: requestedSource,
      year_range: input.year_range,
      limit
    }, { scope });
    return {
      theme,
      mode: 'theme_reading_path',
      results: (lens.reading_path || []).slice(0, limit).map((source) => ({
        ...source,
        reason: source.reason || `representative source for ${theme}`
      }))
    };
  }
  const candidates = [];
  const [startYear, endYear] = parseYearRange(input.year_range || input.era);
  for (const kind of scopeKinds(scope)) {
    if (requestedSource && kind !== requestedSource) continue;
    const corpus = await loadCorpus(kind);
    const linksBySource = groupBySourceKey(await linkRecords(kind), sourceKeyFromLink);
    for (const record of contentRecords(corpus, kind)) {
      const year = recordYear(record);
      if (startYear && (!year || year < startYear)) continue;
      if (endYear && (!year || year > endYear)) continue;
      const links = linksBySource.get(sourceRecordKey(record)) || [];
      const cross = links.filter((link) => link.link_category === 'cross_source').length;
      const domains = new Set([...(record.domains || []), ...links.map((link) => normalizedDomain(link.domain || link.url))].filter(Boolean));
      const age = year ? Math.max(0, new Date().getUTCFullYear() - year) : 0;
      let score = domains.size + cross * 5 + links.length * 0.2;
      let reason = cross ? 'connects multiple Jamie-owned sources' : domains.size ? 'link-rich archive trail' : 'quiet representative source';
      if (mood.includes('forgotten') || mood.includes('old')) {
        score += age * 0.5;
        reason = 'older archive source worth resurfacing';
      } else if (mood.includes('recent') || mood.includes('new')) {
        score += Math.max(0, 20 - age);
        reason = 'recent source with archive signals';
      }
      candidates.push({ score, reason, record, link_count: links.length, cross_source_link_count: cross });
    }
  }
  candidates.sort((a, b) => b.score - a.score || String(b.record.publish_date || '').localeCompare(String(a.record.publish_date || '')));
  return {
    theme: null,
    mode: mood || 'serendipity',
    results: candidates.slice(0, limit).map((item) => ({
      ...compactContentRecord(item.record),
      reason: item.reason,
      score: Number(item.score.toFixed(2)),
      link_count: item.link_count,
      cross_source_link_count: item.cross_source_link_count
    }))
  };
}

async function toolClaimCheck(input = {}, { scope } = {}) {
  const rawClaims = Array.isArray(input.claims) ? input.claims : [input.claim || input.query || input.text];
  const claims = rawClaims.map((claim) => String(claim || '').trim()).filter(Boolean).slice(0, 4);
  const results = [];
  for (const claim of claims) {
    const hits = await retrieve(claim, 3, { scope });
    results.push({
      claim,
      status: hits.length ? 'evidence_found' : 'needs_caution',
      evidence: hits.map((source) => compactSource(source, 450))
    });
  }
  return { results };
}

async function toolRememberUser(input = {}, { subscriberHash } = {}) {
  if (!subscriberHash) return { ok: false, error: 'No authenticated user memory is available.' };
  return rememberUserFact(subscriberHash, input);
}

const ARCHIVE_TOOLS = {
  search_faq: toolSearchFaq,
  search_archive: toolSearchArchive,
  get_source: toolGetSource,
  get_issue: toolGetIssue,
  get_section: toolGetSection,
  find_links: toolFindLinks,
  domain_history: toolDomainHistory,
  corpus_stats: toolCorpusStats,
  latest_content: toolLatestContent,
  quote_search: toolQuoteSearch,
  list_content: toolListContent,
  list_issues: toolListIssues,
  compare_eras: toolCompareEras,
  archive_lens: toolArchiveLens,
  source_neighborhood: toolSourceNeighborhood,
  entity_lens: toolEntityLens,
  archive_gems: toolArchiveGems,
  claim_check: toolClaimCheck,
  remember_user: toolRememberUser
};

function toolSpecs() {
  return loadToolSpecs();
}

const AGENT_SYSTEM_PROMPT = agentSystemPrompt();

function collectToolCitations(toolResults) {
  const sources = [];
  for (const result of toolResults) {
    const candidates = [];
    if (Array.isArray(result.results)) candidates.push(...result.results);
    if (Array.isArray(result.results_a)) candidates.push(...result.results_a);
    if (Array.isArray(result.results_b)) candidates.push(...result.results_b);
    if (Array.isArray(result.related_sources)) candidates.push(...result.related_sources);
    if (Array.isArray(result.incoming_links)) candidates.push(...result.incoming_links);
    if (Array.isArray(result.outgoing_links)) candidates.push(...result.outgoing_links);
    if (Array.isArray(result.cross_source_links)) candidates.push(...result.cross_source_links);
    if (result.issue) candidates.push({ issue_number: result.issue.number, ...result.issue });
    if (result.source) candidates.push(result.source);
    for (const item of candidates) {
      if (item?.issue_number) {
        sources.push({ issue_number: item.issue_number, subject: item.subject, publish_date: item.publish_date, section: item.section || 'Issue', url: item.url || `/archive/${item.issue_number}/` });
      } else if (isExternalSource(item)) {
        sources.push({
          issue_number: null,
          source_kind: item.source_kind || 'external',
          subject: item.subject,
          publish_date: item.publish_date,
          section: item.section,
          url: item.url,
          transcript_url: item.transcript_url,
          audio_url: item.audio_url,
          episode_number: item.episode_number,
          show: item.show,
          also_in_issues: item.also_in_issues
        });
      }
    }
  }
  return citationsFor(sources);
}

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
