import { InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
import { RerankCommand } from '@aws-sdk/client-bedrock-agent-runtime';
import { GetObjectCommand } from '@aws-sdk/client-s3';
import {
  bedrock,
  bedrockAgentRuntime,
  embeddingModel,
  rerankModel,
  s3
} from './aws-clients.mjs';
import { errorFields, logEvent as sharedLogEvent, truthyEnv } from './logging.mjs';
import { normalizeScope, scopeKinds } from './scope.mjs';

const DEFAULT_EMBEDDING_DIMENSIONS = 1024;
const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;
const EMPTY_CORPUS = { version: 0, chunks: [], issues: [], topics: [], links: [] };
const SERVICE_NAME = 'weekly-thing-librarian-stream';

let corpusCache;
let blogCorpusCache;
let podcastCorpusCache;
let graphCache;
let indexedCache;
let blogIndexedCache;
let podcastIndexedCache;

function logEvent(level, message, fields = {}) {
  sharedLogEvent(level, message, fields, SERVICE_NAME);
}

function rerankModelArn() {
  const model = rerankModel();
  if (model.startsWith('arn:')) return model;
  const region = process.env.BEDROCK_RERANK_REGION || 'us-west-2';
  return `arn:aws:bedrock:${region}::foundation-model/${model}`;
}

export async function loadCorpus(kind = 'weekly_thing') {
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

export async function loadGraph() {
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

export function tokenize(text) {
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

export function compactSource(source, textLimit = 900) {
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
    // Present only on blog chunks that a WT issue Journal linked back to -
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

export function parseYearRange(value) {
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

// Scope is enforced HERE - by which corpus/corpora we scan, not by a
// post-filter. weekly_thing scans the WT corpus (identical to today);
// blog/podcast scan their own corpora; mixed scopes gather candidates from
// each and rerank the union once. matchesFilters only applies year/section.
export async function retrieve(query, limit = 8, filters = {}) {
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
