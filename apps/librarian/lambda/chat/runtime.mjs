import crypto from 'node:crypto';
import { BedrockRuntimeClient, ConverseStreamCommand, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
import { BedrockAgentRuntimeClient, RerankCommand } from '@aws-sdk/client-bedrock-agent-runtime';
import { DynamoDBClient, PutItemCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { GetObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { readConverseStream } from '../shared/bedrock-stream.mjs';
import { prioritizeCitationsForAnswer } from '../shared/citations.mjs';
import { normalizeScope, scopeKinds, scopePromptLine } from '../shared/scope.mjs';
import { normalizeFeedbackReaction, validFeedbackRequestId } from '../shared/feedback.mjs';
import { searchFaq } from '../shared/faq.mjs';
import { truthyEnv } from '../shared/logging.mjs';
import {
  agentSystemPrompt,
  agentUserPrompt,
  loadToolSpecs
} from '../shared/prompts.mjs';
import {
  getUserMemory,
  memoryContextBlock,
  recordUserTurn
} from '../shared/user-memory.mjs';

const DEFAULT_AGENT_MODEL = 'us.anthropic.claude-sonnet-4-6';
const DEFAULT_EMBEDDING_MODEL = 'cohere.embed-english-v3';
const DEFAULT_RERANK_MODEL = 'cohere.rerank-v3-5:0';
const DEFAULT_EMBEDDING_DIMENSIONS = 1024;
const DEFAULT_MAX_TOOL_TURNS = 5;
const RATE_LIMIT_WINDOW_SECONDS = 60 * 60;
const RATE_LIMIT_MAX = 20;
const CONVERSATION_LOG_TTL_DAYS = 60;
const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;
const MAX_HISTORY_MESSAGES = 8;
const MAX_HISTORY_CHARS = 4000;

const s3 = new S3Client({});
const dynamodb = new DynamoDBClient({});
const bedrock = new BedrockRuntimeClient({});
const bedrockAgentRuntime = new BedrockAgentRuntimeClient({ region: process.env.BEDROCK_RERANK_REGION || 'us-west-2' });
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

function agentModel() {
  return process.env.BEDROCK_AGENT_MODEL || DEFAULT_AGENT_MODEL;
}

function embeddingModel() {
  return process.env.BEDROCK_EMBEDDING_MODEL || DEFAULT_EMBEDDING_MODEL;
}

function rerankModel() {
  return process.env.BEDROCK_RERANK_MODEL || DEFAULT_RERANK_MODEL;
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

function normalizeHeaders(headers) {
  return Object.fromEntries(Object.entries(headers || {}).map(([key, value]) => [key.toLowerCase(), value]));
}

function clientSourceIp(event) {
  return event.requestContext?.http?.sourceIp || event.requestContext?.identity?.sourceIp || '';
}

function userAgent(event) {
  return normalizeHeaders(event.headers || {})['user-agent'] || '';
}

function methodAndPath(event) {
  const method = (event.requestContext?.http?.method || event.httpMethod || 'GET').toUpperCase();
  const path = (event.rawPath || event.path || '/').replace(/\/$/, '') || '/';
  return { method, path };
}

function parseBody(event) {
  const body = event.body || '{}';
  const text = event.isBase64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function b64urlDecode(value) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  return Buffer.from(value + padding, 'base64url');
}

function sessionSecret() {
  const value = process.env.SESSION_SECRET || process.env.LIBRARIAN_SIGNING_SECRET;
  if (!value) throw new Error('SESSION_SECRET is required');
  return value;
}

function verifyToken(token) {
  try {
    const [encoded, signature] = String(token || '').split('.', 2);
    if (!encoded || !signature) return null;
    const expected = crypto.createHmac('sha256', sessionSecret()).update(encoded).digest();
    const supplied = b64urlDecode(signature);
    if (expected.length !== supplied.length || !crypto.timingSafeEqual(expected, supplied)) return null;
    const payload = JSON.parse(b64urlDecode(encoded).toString('utf8'));
    if (Number(payload.exp || 0) < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
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

function extractBearer(event, body) {
  const auth = String(normalizeHeaders(event.headers || {}).authorization || '');
  if (auth.toLowerCase().startsWith('bearer ')) return auth.slice(7).trim();
  return String(body.token || '');
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

function conversationLoggingEnabled() {
  return !['0', 'false', 'no'].includes(String(process.env.LIBRARIAN_CONVERSATION_LOGGING || '1').toLowerCase());
}

function citationIssues(citations) {
  const seen = new Set();
  const issues = [];
  for (const citation of citations || []) {
    const issue = String(citation.issue_number || '').trim();
    if (issue && !seen.has(issue)) {
      seen.add(issue);
      issues.push(issue);
    }
  }
  return issues;
}

function dynamoString(value) {
  return { S: String(value || '') };
}

function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

function citationItem(citation) {
  return {
    M: {
      issue_number: dynamoString(citation.issue_number),
      subject: dynamoString(citation.subject),
      publish_date: dynamoString(citation.publish_date),
      section: dynamoString(citation.section),
      url: dynamoString(citation.url)
    }
  };
}

async function recordConversation({
  event,
  subscriberHash,
  question,
  answer,
  historyCount,
  citations,
  route,
  requestId
}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !conversationLoggingEnabled()) return;
  const start = performance.now();
  const now = new Date();
  const createdAt = now.toISOString();
  const ttlDays = Number(process.env.LIBRARIAN_CONVERSATION_LOG_TTL_DAYS || CONVERSATION_LOG_TTL_DAYS);
  const ttl = Math.floor(Date.now() / 1000) + ttlDays * 86400;
  const issues = citationIssues(citations);
  const conversationRequestId = requestId || crypto.randomUUID();
  try {
    await dynamodb.send(new PutItemCommand({
      TableName: tableName,
      Item: {
        pk: dynamoString(`conversation#${conversationRequestId}`),
        sk: dynamoString('chat'),
        created_at: dynamoString(createdAt),
        ttl: dynamoNumber(ttl),
        request_id: dynamoString(conversationRequestId),
        subscriber_hash: dynamoString(subscriberHash),
        route: dynamoString(route),
        question: dynamoString(String(question || '').slice(0, 4000)),
        answer: dynamoString(String(answer || '').slice(0, 12000)),
        question_chars: dynamoNumber(String(question || '').length),
        answer_chars: dynamoNumber(String(answer || '').length),
        history_count: dynamoNumber(historyCount),
        citation_count: dynamoNumber((citations || []).length),
        source_issues: { L: issues.map(dynamoString) },
        citations: { L: (citations || []).slice(0, 12).map(citationItem) },
        user_agent: dynamoString(userAgent(event).slice(0, 300))
      }
    }));
    logEvent('info', 'conversation_recorded', {
      subscriber_hash: subscriberHash,
      request_id: conversationRequestId,
      question_chars: String(question || '').length,
      answer_chars: String(answer || '').length,
      citation_count: (citations || []).length,
      duration_ms: Math.round(performance.now() - start)
    });
  } catch (error) {
    logEvent('warning', 'conversation_record_failed', { request_id: requestId, error_type: error.constructor?.name || 'Error' });
  }
}

async function recordFeedback({ subscriberHash, requestId, reaction }) {
  const tableName = process.env.TABLE_NAME;
  const validRequestId = validFeedbackRequestId(requestId);
  const validReaction = normalizeFeedbackReaction(reaction);
  if (!tableName) return { statusCode: 500, payload: { error: 'Thingy feedback is unavailable right now.' } };
  if (!validRequestId || !validReaction) {
    return { statusCode: 400, payload: { error: 'Feedback requires a valid request_id and reaction.' } };
  }

  const feedbackAt = new Date().toISOString();
  try {
    await dynamodb.send(new UpdateItemCommand({
      TableName: tableName,
      Key: { pk: dynamoString(`conversation#${validRequestId}`), sk: dynamoString('chat') },
      UpdateExpression: 'SET feedback_reaction = :reaction, feedback_at = :feedback_at ADD feedback_revision :one',
      ConditionExpression: 'attribute_exists(pk) AND subscriber_hash = :subscriber_hash',
      ExpressionAttributeValues: {
        ':reaction': dynamoString(validReaction),
        ':feedback_at': dynamoString(feedbackAt),
        ':one': dynamoNumber(1),
        ':subscriber_hash': dynamoString(subscriberHash)
      }
    }));
    logEvent('info', 'feedback_recorded', {
      subscriber_hash: subscriberHash,
      request_id: validRequestId,
      reaction: validReaction
    });
    return { statusCode: 200, payload: { ok: true, request_id: validRequestId, reaction: validReaction } };
  } catch (error) {
    if (error.name === 'ConditionalCheckFailedException') {
      return { statusCode: 404, payload: { error: 'Conversation not found for feedback.', request_id: validRequestId } };
    }
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

// The blog corpus is large and only needed for blog/both/all scopes, so it
// loads lazily and caches separately from the WT corpus. When the env key is
// unset, return an empty corpus so source-specific requests degrade to no hits.
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
    logEvent('error', 'semantic_retrieval_failed', { error_type: error.constructor?.name || 'Error' });
  }
  let lexical = [];
  for (const kind of kinds) lexical.push(...(await retrieveLexical(query, candidateLimit, kind)));
  lexical = lexical.filter((source) => matchesFilters(source, filters)).sort(byScore);
  return withAgeLabel((await rerankSources(query, lexical, limit)).slice(0, limit));
}

function sanitizeHistory(history) {
  if (!Array.isArray(history)) return [];
  const cleaned = [];
  let chars = 0;
  for (const item of history.slice(-MAX_HISTORY_MESSAGES)) {
    const role = item?.role === 'assistant' ? 'assistant' : item?.role === 'user' ? 'user' : '';
    const content = String(item?.content || '').trim().replace(/\s+/g, ' ');
    if (!role || !content) continue;
    const clipped = content.slice(0, 700);
    chars += clipped.length;
    if (chars > MAX_HISTORY_CHARS) break;
    cleaned.push({ role, content: clipped });
  }
  return cleaned;
}

function conversationContext(history) {
  if (!history.length) return 'No earlier conversation in this session.';
  return history.map((item) => `${item.role === 'user' ? 'User' : 'Thingy'}: ${item.content}`).join('\n');
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

function commandInferenceConfig() {
  return {
    maxTokens: Number(process.env.BEDROCK_MAX_OUTPUT_TOKENS || '2500'),
    temperature: Number(process.env.BEDROCK_TEMPERATURE || '0.45')
  };
}

function issueKey(value) {
  return String(value || '').replace(/^#/, '').trim();
}

async function issueByNumber(number) {
  const wanted = issueKey(number);
  const corpus = await loadCorpus();
  return (corpus.issues || []).find((issue) => issueKey(issue.number) === wanted);
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

function normalizeSourceKind(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (!raw) return '';
  if (['weekly_thing', 'weeklything', 'newsletter', 'issue', 'issues', 'archive', 'wt', 'chunk'].includes(raw)) return 'weekly_thing';
  if (['blog', 'thingelstad', 'thingelstad_com', 'post', 'posts', 'micropost'].includes(raw)) return 'blog';
  if (['podcast', 'podcasts', 'another', 'another_thing', 'episode', 'episodes'].includes(raw)) return 'podcast';
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

function normalizeLinkRecord(link, kind) {
  const sourceKind = link.source_kind || (kind === 'blog' ? 'blog' : kind === 'podcast' ? 'podcast' : 'chunk');
  const linkKind = inferredLinkKind(link);
  const targetResolved = Boolean(link.target_resolved || link.target_post_url || link.target_microblog_id);
  return {
    ...link,
    source_kind: sourceKind,
    corpus_kind: normalizeSourceKind(kind) || linkCorpusKind(link),
    subject: link.subject || link.post_subject,
    publish_date: link.publish_date,
    issue_year: link.issue_year || link.post_year,
    source_url: link.issue_url || link.post_url || link.episode_url,
    link_url: link.url,
    link_kind: linkKind,
    link_category: link.link_category || (linkKind === 'external' ? 'external' : targetResolved ? 'resolved_post' : 'internal_unresolved'),
    target_resolved: targetResolved,
    target_source_kind: link.target_source_kind || (targetResolved ? 'blog' : undefined)
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
    sources.push({
      source_kind: kind,
      generated_at: corpus.generated_at,
      item_count: kind === 'blog' ? corpus.post_count || records.length : kind === 'podcast' ? corpus.episode_count || records.length : corpus.issue_count || records.length,
      chunk_count: corpus.chunk_count || (corpus.chunks || []).length,
      link_count: corpus.link_count || links.length,
      oldest: records[records.length - 1] || null,
      newest: records[0] || null,
      top_domains: summarizeDomains(links),
      counts_by_link_kind: countList(linkKindCounts, 'link_kind'),
      counts_by_link_category: countList(categoryCounts, 'link_category')
    });
  }
  return { scope: normalizeScope(scope), sources };
}

async function toolLatestContent(input = {}, { scope } = {}) {
  const requestedSource = normalizeSourceKind(input.source_kind || input.source || '');
  const limit = Math.min(Math.max(Number(input.limit || 10), 1), 30);
  const items = [];
  for (const kind of scopeKinds(scope)) {
    if (requestedSource && kind !== requestedSource) continue;
    const corpus = await loadCorpus(kind);
    items.push(...contentRecords(corpus, kind));
  }
  return {
    scope: normalizeScope(scope),
    source_kind: requestedSource || null,
    results: latestByDate(items).slice(0, limit)
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
  // over chunk text, deduped by source kind + permalink.
  for (const kind of kinds.filter((item) => item !== 'weekly_thing')) {
    if (results.length >= limit) break;
    const corpus = await loadCorpus(kind);
    const seen = new Set();
    for (const chunk of corpus.chunks || []) {
      const text = String(chunk.text || '');
      if (!text.toLowerCase().includes(needle)) continue;
      const url = chunk.url || '';
      const key = `${kind}\0${url}`;
      if (seen.has(key)) continue;
      seen.add(key);
      results.push({
        issue_number: null,
        source_kind: chunk.source_kind || kind,
        subject: chunk.subject,
        publish_date: chunk.publish_date,
        section: chunk.section,
        url,
        transcript_url: chunk.transcript_url,
        audio_url: chunk.audio_url,
        episode_number: chunk.episode_number,
        show: chunk.show,
        also_in_issues: chunk.also_in_issues,
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

const ARCHIVE_TOOLS = {
  search_faq: toolSearchFaq,
  search_archive: toolSearchArchive,
  get_issue: toolGetIssue,
  get_section: toolGetSection,
  find_links: toolFindLinks,
  domain_history: toolDomainHistory,
  corpus_stats: toolCorpusStats,
  latest_content: toolLatestContent,
  quote_search: toolQuoteSearch,
  list_issues: toolListIssues,
  compare_eras: toolCompareEras
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
    if (result.issue) candidates.push({ issue_number: result.issue.number, ...result.issue });
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

async function streamBedrockAgentAnswer(question, history, responseStream, options = {}) {
  const start = performance.now();
  const scope = normalizeScope(options.scope);
  const memoryContext = String(options.memoryContext || '').trim();
  const messages = [{
    role: 'user',
    content: [{
      text: agentUserPrompt({
        conversation_context: conversationContext(history),
        question
      })
    }]
  }];
  const toolResults = [];
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
    const result = await readConverseStream(response, {
      onTextDelta: (delta) => writeSse(responseStream, 'answer_delta', { delta })
    });
    const message = result.message;
    usage = result.usage || usage;
    stopReason = result.stopReason || stopReason;
    messages.push(message);
    const toolUses = (message.content || []).filter((block) => block.toolUse).map((block) => block.toolUse);
    if (!toolUses.length) {
      answer = bedrockMessageText(message) || result.text;
      break;
    }
    const resultBlocks = [];
    for (const toolUse of toolUses) {
      writeSse(responseStream, 'status', { message: `Checking ${toolUse.name.replaceAll('_', ' ')}...` });
      const handler = ARCHIVE_TOOLS[toolUse.name];
      let result;
      try {
        result = handler ? await handler(toolUse.input || {}, { scope }) : { error: `Unknown tool: ${toolUse.name}` };
      } catch (error) {
        logEvent('error', 'tool_call_failed', { tool_name: toolUse.name, error_type: error.constructor?.name || 'Error' });
        result = { error: `${toolUse.name} failed: ${error.constructor?.name || 'Error'}` };
      }
      toolResults.push(result);
      resultBlocks.push({ toolResult: { toolUseId: toolUse.toolUseId, content: [{ json: result }] } });
    }
    messages.push({
      role: 'user',
      content: resultBlocks
    });
  }
  if (!answer) {
    answer = 'I could not produce a reliable answer from the archive tools for that question.';
    writeSse(responseStream, 'answer_delta', { delta: answer });
  }
  const citations = prioritizeCitationsForAnswer(collectToolCitations(toolResults), answer);
  logEvent('info', 'agent_streamed', {
    model: agentModel(),
    scope,
    tool_turns: toolResults.length,
    citation_count: citations.length,
    duration_ms: Math.round(performance.now() - start),
    answer_chars: answer.length,
    output_tokens: usage?.outputTokens,
    stop_reason: stopReason
  });
  return { answer, citations };
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
        reaction: body.reaction
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

  const stream = streamFromResponse(responseStream, event, method === 'POST' && path.endsWith('/chat') ? 200 : 404);
  try {
    if (method !== 'POST' || !path.endsWith('/chat')) {
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

    const question = String(body.message || '').trim();
    const scope = normalizeScope(body.scope);
    const history = sanitizeHistory(body.history);
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

    // Fetch user memory once at turn start. Used to inject prior-session
    // context into Thingy's system prompt so the agent can respond more
    // personally; also recorded back at turn end.
    const userMemory = await getUserMemory(subscriberHash);
    const memoryContext = memoryContextBlock(userMemory);

    writeSse(stream, 'meta', { request_id: requestId });
    const guardedAnswer = privacyGuardAnswer(question);
    if (guardedAnswer) {
      const citations = [];
      writeSse(stream, 'answer_delta', { delta: guardedAnswer });
      writeSse(stream, 'citations', { citations });
      writeSse(stream, 'done', { request_id: requestId });
      await recordConversation({ event, subscriberHash, question, answer: guardedAnswer, historyCount: history.length, citations, route: 'stream', requestId });
      // Privacy-guarded turn still updates memory — the question text was
      // recorded above, so let the user-memory row reflect that turn too.
      await recordUserTurn(subscriberHash, { sid: String(payload.sid || ''), question });
      return;
    }

    writeSse(stream, 'status', { message: 'Investigating the archive...' });
    let deadlineExceeded = false;
    const deadlineTimer = setTimeout(() => {
      deadlineExceeded = true;
      try {
        writeSse(stream, 'error', { error: 'The archive is taking longer than usual. Please try again.', request_id: requestId });
      } catch {}
      try { stream.end(); } catch {}
      logEvent('warn', 'chat_deadline_exceeded', { request_id: requestId, subscriber_hash: subscriberHash });
    }, 75000);
    let result;
    try {
      result = await streamBedrockAgentAnswer(question, history, stream, { memoryContext, scope });
    } finally {
      clearTimeout(deadlineTimer);
    }
    if (deadlineExceeded) return;
    const answer = result.answer;
    const citations = result.citations;
    writeSse(stream, 'citations', { citations });
    writeSse(stream, 'done', { request_id: requestId });
    await recordConversation({
      event,
      subscriberHash,
      question,
      answer,
      historyCount: history.length,
      citations,
      route: 'stream',
      requestId
    });
    // Update per-user memory after the answer ships. If the sid has
    // rotated since the prior turn, this also triggers a Bedrock-
    // synthesized summary of the previous session.
    await recordUserTurn(subscriberHash, { sid: String(payload.sid || ''), question });
    logEvent('info', 'chat_completed', {
      subscriber_hash: subscriberHash,
      question_chars: question.length,
      history_count: history.length,
      citation_count: citations.length,
      duration_ms: Math.round(performance.now() - start)
    });
  } catch (error) {
    logEvent('error', 'request_failed', { ...summary, error_type: error.constructor?.name || 'Error' });
    writeSse(stream, 'error', { error: 'The librarian could not generate an answer right now.', request_id: requestId });
  } finally {
    logEvent('info', 'request_completed', { ...summary, duration_ms: Math.round(performance.now() - start) });
    stream.end();
  }
});
