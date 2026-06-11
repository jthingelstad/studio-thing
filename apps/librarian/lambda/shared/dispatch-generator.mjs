import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { GetObjectCommand } from '@aws-sdk/client-s3';
import MarkdownIt from 'markdown-it';
import { bedrock, s3, advancedModel } from './aws-clients.mjs';
import { tinylyticsPixelHtml } from './tinylytics-email.mjs';

const MAX_SOURCE_PACKETS = 18;
const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;
const THINGY_URL = 'https://thingy.thingelstad.com/';

let corpusCache = null;

const dispatchMarkdown = new MarkdownIt({
  html: false,
  linkify: false,
  typographer: false,
  breaks: false
});

function withAttrs(tokens, idx, attrs = {}) {
  for (const [key, value] of Object.entries(attrs)) tokens[idx].attrSet(key, value);
  return dispatchMarkdown.renderer.renderToken(tokens, idx, {});
}

dispatchMarkdown.renderer.rules.paragraph_open = (tokens, idx) => withAttrs(tokens, idx, {
  style: 'font-size:17px;line-height:1.6;margin:0 0 18px;color:#14181f;'
});

dispatchMarkdown.renderer.rules.bullet_list_open = (tokens, idx) => withAttrs(tokens, idx, {
  style: 'padding-left:24px;margin:0 0 18px;color:#14181f;font-size:17px;line-height:1.6;'
});

dispatchMarkdown.renderer.rules.ordered_list_open = (tokens, idx) => withAttrs(tokens, idx, {
  style: 'padding-left:24px;margin:0 0 18px;color:#14181f;font-size:17px;line-height:1.6;'
});

dispatchMarkdown.renderer.rules.list_item_open = (tokens, idx) => withAttrs(tokens, idx, {
  style: 'margin:0 0 8px;'
});

dispatchMarkdown.renderer.rules.blockquote_open = (tokens, idx) => withAttrs(tokens, idx, {
  style: 'border-left:4px solid #d8e1dd;margin:0 0 18px;padding:0 0 0 16px;color:#4a5565;'
});

dispatchMarkdown.renderer.rules.heading_open = (tokens, idx) => {
  const level = tokens[idx].tag === 'h2' ? '20px' : '18px';
  return withAttrs(tokens, idx, {
    style: `font-size:${level};line-height:1.35;margin:4px 0 12px;color:#14181f;font-weight:700;`
  });
};

dispatchMarkdown.renderer.rules.link_open = (tokens, idx) => {
  tokens[idx].attrSet('style', linkStyle());
  return dispatchMarkdown.renderer.renderToken(tokens, idx, {});
};

dispatchMarkdown.renderer.rules.code_inline = (tokens, idx) => (
  `<code style="font-family:Menlo,Consolas,monospace;font-size:.92em;background:#f1f5f3;border-radius:4px;padding:1px 4px;">${escapeHtml(tokens[idx].content)}</code>`
);

function cleanText(value, max = 1000) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function cleanBlockText(value, max = 5000) {
  const text = Array.isArray(value) ? value.join('\n\n') : String(value || '');
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => line.replace(/[ \t]+/g, ' ').trim())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .slice(0, max);
}

export function dispatchSubject(value, fallbackTitle = '') {
  const raw = cleanText(value || fallbackTitle || 'From the archive', 110);
  const withoutPrefix = raw.replace(/^(?:thingy\s+)?dispatch\s*[-:\u2014\u2013]\s*/i, '').trim();
  const title = cleanText(withoutPrefix || fallbackTitle || 'From the archive', 88);
  return `Thingy Dispatch — ${title}`;
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function escapeRegExp(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function sourceHref(source = {}) {
  const url = String(source.url || '').trim();
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith('/archive/')) return `https://weekly.thingelstad.com${url}`;
  if (url.startsWith('/')) return `${THINGY_URL.replace(/\/$/, '')}${url}`;
  return url;
}

function thingyPromptUrl(prompt) {
  const url = new URL('/chat/', THINGY_URL);
  url.searchParams.set('prompt', cleanText(prompt, 400));
  return url.toString();
}

function requestedAtText(value) {
  const date = value ? new Date(value) : new Date();
  if (!Number.isFinite(date.getTime())) return String(value || '');
  return `${date.toISOString().slice(0, 16).replace('T', ' ')}Z`;
}

function tokenize(value) {
  const words = String(value || '').toLowerCase().match(TOKEN_RE) || [];
  const allowedShortTerms = new Set(['ai', 'ar', 'vr', 'xr']);
  return words.filter((word) => word.length > 2 || allowedShortTerms.has(word));
}

function sourceKindLabel(kind) {
  if (kind === 'weekly_thing') return 'Weekly Thing';
  if (kind === 'blog') return 'Blog';
  if (kind === 'podcast') return 'Another Thing';
  return 'Archive';
}

function chunkTitle(chunk = {}) {
  return cleanText(chunk.subject || chunk.title || chunk.episode_title || chunk.section || 'Archive source', 140);
}

function chunkUrl(chunk = {}) {
  if (chunk.url) return String(chunk.url);
  if (chunk.issue_number) return `https://weekly.thingelstad.com/archive/${chunk.issue_number}/`;
  return '';
}

function chunkLabel(chunk = {}) {
  if (chunk.issue_number) return `WT${chunk.issue_number}`;
  if (chunk.source_kind === 'podcast' && chunk.episode_number) return `Another Thing ${chunk.episode_number}`;
  if (chunk.source_kind === 'blog') return 'Blog';
  return sourceKindLabel(chunk.source_kind);
}

function normalizeChunk(chunk = {}) {
  return {
    source_kind: String(chunk.source_kind || (chunk.episode_number ? 'podcast' : chunk.issue_number ? 'weekly_thing' : 'blog')),
    issue_number: chunk.issue_number || '',
    episode_number: chunk.episode_number || '',
    title: chunkTitle(chunk),
    label: chunkLabel(chunk),
    publish_date: String(chunk.publish_date || chunk.date || ''),
    url: chunkUrl(chunk),
    section: cleanText(chunk.section || chunk.content_kind || '', 80),
    topics: Array.isArray(chunk.topics) ? chunk.topics.map((item) => cleanText(item, 40)).filter(Boolean).slice(0, 8) : [],
    text: cleanText(chunk.text || chunk.summary || chunk.description || '', 1600)
  };
}

async function loadJsonFromS3(bucket, key) {
  if (!bucket || !key) return null;
  const response = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
  return JSON.parse(await response.Body.transformToString());
}

export async function loadDispatchCorpus() {
  if (corpusCache) return corpusCache;
  const bucket = process.env.CORPUS_BUCKET;
  const keys = [
    process.env.CORPUS_KEY || 'librarian/corpus.json',
    process.env.BLOG_CORPUS_KEY,
    process.env.PODCAST_CORPUS_KEY
  ].filter(Boolean);
  const all = [];
  for (const key of keys) {
    const corpus = await loadJsonFromS3(bucket, key);
    for (const chunk of corpus?.chunks || []) {
      const normalized = normalizeChunk(chunk);
      if (normalized.text) all.push(normalized);
    }
  }
  corpusCache = all;
  return corpusCache;
}

function scoreChunk(chunk, queryTokens) {
  const haystack = [
    chunk.title,
    chunk.section,
    Array.isArray(chunk.topics) ? chunk.topics.join(' ') : '',
    chunk.text
  ].join(' ').toLowerCase();
  let score = 0;
  for (const token of queryTokens) {
    const count = haystack.split(token).length - 1;
    if (count) score += Math.min(count, 4);
  }
  if (!score) return 0;
  if (chunk.source_kind === 'weekly_thing') score += 0.25;
  if (chunk.url) score += 0.1;
  return score;
}

export function selectDispatchSources(chunks = [], query = '', limit = MAX_SOURCE_PACKETS) {
  const queryTokens = Array.from(new Set(tokenize(query)));
  const scored = chunks
    .map((chunk) => normalizeChunk(chunk))
    .map((chunk) => ({ ...chunk, score: scoreChunk(chunk, queryTokens) }))
    .filter((chunk) => chunk.score > 0)
    .sort((a, b) => b.score - a.score || String(b.publish_date).localeCompare(String(a.publish_date)));

  const selected = [];
  const seenUrls = new Set();
  const perKind = new Map();
  for (const chunk of scored) {
    const key = chunk.url || `${chunk.source_kind}:${chunk.title}:${chunk.section}`;
    if (seenUrls.has(key)) continue;
    const kindCount = perKind.get(chunk.source_kind) || 0;
    if (kindCount >= Math.ceil(limit / 2) && selected.length < Math.floor(limit * 0.7)) continue;
    seenUrls.add(key);
    perKind.set(chunk.source_kind, kindCount + 1);
    selected.push({
      id: `S${selected.length + 1}`,
      label: chunk.label,
      title: chunk.title,
      url: chunk.url,
      source_kind: chunk.source_kind,
      publish_date: chunk.publish_date,
      excerpt: cleanText(chunk.text, 900)
    });
    if (selected.length >= limit) break;
  }
  return selected;
}

export function analyzeDispatchSourceFit(chunks = [], query = '', limit = MAX_SOURCE_PACKETS) {
  const queryTokens = Array.from(new Set(tokenize(query)));
  const scored = chunks
    .map((chunk) => normalizeChunk(chunk))
    .map((chunk) => ({ ...chunk, score: scoreChunk(chunk, queryTokens) }))
    .filter((chunk) => chunk.score > 0)
    .sort((a, b) => b.score - a.score || String(b.publish_date).localeCompare(String(a.publish_date)));
  const selected = selectDispatchSources(scored, query, limit);
  const words = cleanText(query, 1200).split(/\s+/).filter(Boolean);
  let coverageStatus = 'focused';
  if (selected.length < 4) {
    coverageStatus = 'thin';
  } else if (words.length <= 3 || scored.length >= 34 || (selected.length >= 16 && words.length <= 8)) {
    coverageStatus = 'broad';
  }
  const perKind = selected.reduce((counts, source) => {
    counts[source.source_kind] = (counts[source.source_kind] || 0) + 1;
    return counts;
  }, {});
  return {
    coverage_status: coverageStatus,
    query_tokens: queryTokens,
    candidate_count: scored.length,
    selected_sources: selected,
    source_kinds: perKind
  };
}

function fallbackDispatchSources(chunks = [], limit = 8) {
  const selected = [];
  const seenUrls = new Set();
  for (const chunk of chunks.map((item) => normalizeChunk(item))) {
    const key = chunk.url || `${chunk.source_kind}:${chunk.title}:${chunk.section}`;
    if (!chunk.text || seenUrls.has(key)) continue;
    seenUrls.add(key);
    selected.push({
      id: `S${selected.length + 1}`,
      label: chunk.label,
      title: chunk.title,
      url: chunk.url,
      source_kind: chunk.source_kind,
      publish_date: chunk.publish_date,
      excerpt: cleanText(chunk.text, 900)
    });
    if (selected.length >= limit) break;
  }
  return selected;
}

function sourcePacketText(sources = []) {
  return sources.map((source) => [
    `[${source.id}] ${source.label} · ${source.title}`,
    source.publish_date ? `Date: ${source.publish_date}` : '',
    source.url ? `URL: ${source.url}` : '',
    `Excerpt: ${source.excerpt}`
  ].filter(Boolean).join('\n')).join('\n\n');
}

function dispatchSystemPrompt() {
  return `You are Thingy, Jamie Thingelstad's archive sidekick.

You write Dispatches: one-off, requested archive briefs for Weekly Thing supporting members.

Rules:
- Write as Thingy, not as Jamie. Never use Jamie's first-person voice.
- Do not imply Jamie personally curated, approved, or wrote this Dispatch.
- Ground the Dispatch in the supplied source packets from Jamie's published archive.
- The shape may be inspired by The Weekly Thing: warm opening, titled sections, source links, closing follow-up prompts.
- Do not make it materially fancier or more promotional than The Weekly Thing.
- Target about 1,200 words.
- Include source references like [S1] where claims depend on a source, but attach them directly after the source title, issue name, or linked phrase rather than at the end of a sentence. Example: Weekly Thing 336 [S1] says... not ...says something. [S1]
- Write follow-up prompts as questions a reader can click to continue in Thingy.
- Use simple Markdown only inside text fields: paragraphs, ordered lists, unordered lists, **bold**, *italic*, and Markdown links. Do not return raw HTML.
- Return only JSON.`;
}

function dispatchUserPrompt({ dispatch, sources }) {
  const brief = dispatchBriefForPrompt(dispatch.brief);
  return [
    `Reader request: ${dispatch.prompt || dispatch.topic}`,
    dispatch.clarification_question ? `Thingy's clarification question: ${dispatch.clarification_question}` : '',
    dispatch.clarification_answer ? `Reader clarification: ${dispatch.clarification_answer}` : '',
    dispatch.direction ? `Confirmed direction: ${dispatch.direction}` : '',
    brief ? `Dispatch planning brief:\n${brief}` : '',
    '',
    'Source packets:',
    sourcePacketText(sources),
    '',
    'Return JSON with this shape:',
    '{',
    '  "subject": "email subject line, starts with Thingy Dispatch —",',
    '  "preview": "one sentence preview",',
    '  "title": "Dispatch title",',
    '  "intro": "2-3 paragraph Thingy-authored opening",',
    '  "sections": [{"heading":"section heading","body":"2-4 paragraphs with optional simple Markdown lists and [S#] references"}],',
    '  "closing": "short closing from Thingy",',
    '  "followups": ["question to continue in Thingy"]',
    '}'
  ].filter(Boolean).join('\n');
}

function dispatchBriefForPrompt(brief) {
  if (!brief || typeof brief !== 'object' || Array.isArray(brief)) return '';
  const compact = {
    user_goal: cleanText(brief.user_goal, 400),
    working_angle: cleanText(brief.working_angle, 500),
    coverage_status: cleanText(brief.coverage_status, 40),
    generation_instructions: cleanBlockText(brief.generation_instructions, 900),
    preheader_basis: cleanText(brief.preheader_basis, 240),
    excluded_scope: Array.isArray(brief.excluded_scope)
      ? brief.excluded_scope.map((item) => cleanText(item, 160)).filter(Boolean).slice(0, 6)
      : [],
    selected_sources: Array.isArray(brief.selected_sources)
      ? brief.selected_sources.slice(0, 10).map((source) => ({
        label: cleanText(source?.label, 60),
        title: cleanText(source?.title, 180),
        url: cleanText(source?.url, 500),
        source_kind: cleanText(source?.source_kind, 40),
        why: cleanText(source?.why, 220)
      }))
      : []
  };
  return JSON.stringify(compact);
}

function prioritizeBriefSources(sources = [], brief = {}) {
  const planned = Array.isArray(brief?.selected_sources) ? brief.selected_sources : [];
  if (!planned.length) return sources;
  const keys = new Set();
  for (const source of planned) {
    const url = cleanText(source?.url, 500).toLowerCase();
    const title = cleanText(source?.title, 180).toLowerCase();
    if (url) keys.add(`url:${url}`);
    if (title) keys.add(`title:${title}`);
  }
  if (!keys.size) return sources;
  return [...sources].sort((a, b) => {
    const aHit = keys.has(`url:${cleanText(a.url, 500).toLowerCase()}`) || keys.has(`title:${cleanText(a.title, 180).toLowerCase()}`);
    const bHit = keys.has(`url:${cleanText(b.url, 500).toLowerCase()}`) || keys.has(`title:${cleanText(b.title, 180).toLowerCase()}`);
    return Number(bHit) - Number(aHit);
  }).map((source, index) => ({ ...source, id: `S${index + 1}` }));
}

export function dispatchTemplateTestPayload(dispatch, sources = []) {
  const topic = cleanText(dispatch.direction || dispatch.prompt || dispatch.topic || 'Dispatch template test', 180);
  const refs = sources.slice(0, 6).map((source) => `[${source.id}]`).join(', ');
  const primaryRefs = refs || '[S1]';
  return normalizeDispatchPayload({
    subject: `Thingy Dispatch — ${topic}`,
    preview: 'A low-cost Thingy Dispatch template test using placeholder copy and real archive source metadata.',
    title: topic,
    intro: [
      'This is a Thingy Dispatch template test. It intentionally does not contain generated long-form Dispatch writing.',
      `The goal is to exercise the real queue, delivery, storage, and email rendering path while using placeholder copy. Source references such as ${primaryRefs} are included so link rendering and source styling can be reviewed.`
    ].join('\n\n'),
    sections: [
      {
        heading: 'Opening Shape',
        body: `This section stands in for the first substantive Dispatch thread. It should feel like ordinary email body copy, include enough length to exercise paragraph spacing, and carry source references like ${primaryRefs}.`
      },
      {
        heading: 'Archive Thread',
        body: `This section exists to test the visual rhythm of headings, body text, links, and citations. It is deliberately template copy, not generated analysis. Review margins, type size, source link color, and how repeated paragraphs feel in real email clients. ${primaryRefs}`
      },
      {
        heading: 'Reader Takeaway',
        body: 'This final section tests the closing cadence before the follow-up block. It should make it easy to spot whether the Dispatch template feels close enough to The Weekly Thing without pretending Jamie wrote or approved the content.'
      }
    ],
    closing: 'Template test complete. This closing exists so the footer boundary and source block can be reviewed without invoking the advanced writing model.',
    followups: [
      'What should Thingy make easier to inspect in Dispatch test emails?',
      'Does the Dispatch template feel too close to, or too far from, The Weekly Thing?'
    ]
  }, topic);
}

export function parseDispatchJson(text) {
  const raw = String(text || '').trim();
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1] : (raw.match(/\{[\s\S]*\}/) || [raw])[0];
  try {
    const parsed = JSON.parse(candidate);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function sourceLinkMap(sources = []) {
  return Object.fromEntries(sources.map((source) => [source.id, source]));
}

function linkStyle() {
  return 'color:#1f6fd6;text-decoration:underline;';
}

function linkHtml(href, label) {
  return `<a href="${escapeHtml(href)}" style="${linkStyle()}">${label}</a>`;
}

function sourceFootnoteNumber(id = '') {
  const match = String(id || '').match(/^S(\d+)$/i);
  return match ? match[1] : String(id || '');
}

function sourceFootnoteHtml(source = {}, id = '') {
  const label = escapeHtml(sourceFootnoteNumber(source.id || id));
  if (!source?.id) return `<strong>${escapeHtml(id)}</strong>`;
  return `<sup style="font-size:11px;line-height:0;vertical-align:super;"><a href="#source-${escapeHtml(source.id)}" style="${linkStyle()}">${label}</a></sup>`;
}

function sourceMentionPatterns(source = {}) {
  const patterns = [];
  const title = cleanText(source.title || '', 180);
  if (title) patterns.push(escapeRegExp(escapeHtml(title)));
  const label = cleanText(source.label || '', 60);
  if (label) patterns.push(escapeRegExp(escapeHtml(label)));
  const wtMatch = label.match(/^WT(\d+)$/i);
  if (wtMatch) {
    patterns.push(`Weekly Thing\\s+#?${wtMatch[1]}`);
    patterns.push(`WT${wtMatch[1]}`);
  }
  const podcastMatch = label.match(/^Another Thing\s+(\d+)$/i);
  if (podcastMatch) patterns.push(`Another Thing\\s+${podcastMatch[1]}`);
  return Array.from(new Set(patterns.filter(Boolean)));
}

function linkFirstSourceMention(html, source = {}) {
  const href = sourceHref(source);
  if (!href) return { html, linked: false };
  for (const pattern of sourceMentionPatterns(source)) {
    const regex = new RegExp(`(?<![\\w/])(${pattern})(?![^<]*>)`, 'i');
    if (regex.test(html)) {
      return {
        html: html.replace(regex, (_, label) => linkHtml(href, label)),
        linked: true
      };
    }
  }
  return { html, linked: false };
}

function replaceRemainingSourceRefs(html, sources = []) {
  const map = sourceLinkMap(sources);
  return html.replace(/\s*\[(S\d+)\]/g, (match, id) => {
    const source = map[id];
    if (!source) return ` <strong>${id}</strong>`;
    return sourceFootnoteHtml(source, id);
  });
}

function inlineDispatchMarkup(text, sources = []) {
  let html = escapeHtml(text);
  const referencedIds = Array.from(new Set((String(text || '').match(/\[(S\d+)\]/g) || []).map((id) => id.slice(1, -1))));
  for (const id of referencedIds) {
    const source = sourceLinkMap(sources)[id];
    const linked = linkFirstSourceMention(html, source);
    html = linked.html;
    if (linked.linked) html = html.replace(new RegExp(`\\s*\\[${escapeRegExp(id)}\\]`, 'g'), '');
  }
  html = html.replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, label, href) => linkHtml(href, label));
  return replaceRemainingSourceRefs(html, sources)
    .replace(/\*\*([^*\n][\s\S]*?[^*\n])\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n][^*\n]*?[^*\n])\*(?!\*)/g, '$1<em>$2</em>');
}

function applyDispatchSourceRefs(html, text, sources = []) {
  let next = html;
  const referencedIds = Array.from(new Set((String(text || '').match(/\[(S\d+)\]/g) || []).map((id) => id.slice(1, -1))));
  for (const id of referencedIds) {
    const source = sourceLinkMap(sources)[id];
    const linked = linkFirstSourceMention(next, source);
    next = linked.html;
    if (linked.linked) next = next.replace(new RegExp(`\\s*\\[${escapeRegExp(id)}\\]`, 'g'), '');
  }
  return replaceRemainingSourceRefs(next, sources);
}

function renderDispatchBlocks(text, sources = []) {
  const markdown = cleanBlockText(text, 5000);
  if (!markdown) return '';
  return applyDispatchSourceRefs(dispatchMarkdown.render(markdown), markdown, sources);
}

function normalizeDispatchPayload(payload = {}, fallbackTopic = '') {
  const sections = Array.isArray(payload.sections) ? payload.sections : [];
  const title = cleanText(payload.title || fallbackTopic || 'Dispatch from Thingy', 140);
  return {
    subject: dispatchSubject(title || payload.subject, fallbackTopic),
    preview: cleanText(payload.preview || '', 220),
    title,
    intro: cleanBlockText(payload.intro || '', 4000),
    sections: sections.slice(0, 7).map((section, index) => ({
      heading: cleanText(section?.heading || `Thread ${index + 1}`, 120),
      body: cleanBlockText(section?.body || '', 5000)
    })).filter((section) => section.body),
    closing: cleanBlockText(payload.closing || '', 2000),
    followups: Array.isArray(payload.followups)
      ? payload.followups.map((item) => cleanText(item, 160)).filter(Boolean).slice(0, 5)
      : []
  };
}

function dispatchRequestLine(context = {}) {
  const email = cleanText(context.toEmail || context.to_email || '', 180);
  const requestedAt = requestedAtText(context.requestedAt || context.requested_at || context.createdAt || context.created_at || '');
  if (email && requestedAt) return `This Thingy Dispatch was requested by ${email} on ${requestedAt}.`;
  if (email) return `This Thingy Dispatch was requested by ${email}.`;
  if (requestedAt) return `This Thingy Dispatch was requested on ${requestedAt}.`;
  return 'This Thingy Dispatch was requested by a Weekly Thing reader.';
}

function dispatchRequestSummary(context = {}) {
  return cleanBlockText(
    context.requestSummary || context.request_summary || context.direction || context.prompt || context.topic || '',
    520
  );
}

function dispatchAttributionText() {
  return `Prepared by Thingy (${THINGY_URL}) from Jamie Thingelstad's published archive. Written by Thingy, not Jamie.`;
}

function dispatchProvenanceLines(context = {}) {
  const lines = [dispatchRequestLine(context)];
  const summary = dispatchRequestSummary(context);
  if (summary) lines.push(`Request: ${summary}`);
  lines.push(dispatchAttributionText());
  return lines;
}

function dispatchProvenanceHtml(context = {}) {
  const request = dispatchRequestLine(context);
  const summary = dispatchRequestSummary(context);
  const attribution = `${request} Prepared by Thingy from Jamie Thingelstad's published archive. Written by Thingy, not Jamie.`;
  return [
    `<p style="font-size:14px;line-height:1.45;color:#4a5565;margin:0 0 10px;"><strong style="display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#1f6fd6;margin:0 0 3px;">Request</strong>${summary ? inlineDispatchMarkup(summary) : 'Thingy Dispatch'}</p>`,
    `<p style="font-size:13px;line-height:1.45;color:#5d6675;margin:0;font-style:italic;">${escapeHtml(attribution).replace('Prepared by Thingy', `Prepared by <a href="${THINGY_URL}" style="${linkStyle()}">Thingy</a>`)}</p>`
  ].join('');
}

export function dispatchTextEmail(dispatchPayload, sources = [], context = {}) {
  const lines = [
    ...dispatchProvenanceLines(context),
    '',
    '---',
    '',
    dispatchPayload.title,
    '',
    dispatchPayload.preview,
    '',
    dispatchPayload.intro,
    ''
  ];
  for (const section of dispatchPayload.sections) {
    lines.push(section.heading, '', section.body, '');
  }
  if (dispatchPayload.closing) lines.push(dispatchPayload.closing, '');
  if (dispatchPayload.followups.length) {
    lines.push('Continue in Thingy:');
    dispatchPayload.followups.forEach((item) => lines.push(`- ${item} — ${thingyPromptUrl(item)}`));
    lines.push('');
  }
  lines.push('Sources:');
  sources.forEach((source) => lines.push(`- ${source.label} · ${source.title}${sourceHref(source) ? ` — ${sourceHref(source)}` : ''}`));
  lines.push('', dispatchAttributionText());
  return lines.filter((line, index, all) => line || all[index - 1]).join('\n');
}

export function dispatchHtmlEmail(dispatchPayload, sources = [], context = {}) {
  const sectionHtml = dispatchPayload.sections.map((section) => `
    <tr><td style="padding:24px 28px 4px;">
      <h2 style="font-family:Charter,'Iowan Old Style','Source Serif 4',Georgia,serif;font-size:24px;line-height:1.25;margin:0 0 12px;color:#14181f;font-weight:500;border-top:1px solid #f0f3f8;padding-top:24px;">${escapeHtml(section.heading)}</h2>
      ${renderDispatchBlocks(section.body, sources)}
    </td></tr>`).join('');

  const followupHtml = dispatchPayload.followups.length ? `
    <tr><td style="padding:22px 28px;background:#f7f9fc;border-top:1px solid #e6ebf2;">
      <h2 style="font-family:Charter,'Iowan Old Style','Source Serif 4',Georgia,serif;font-size:21px;line-height:1.2;margin:0 0 10px;color:#14181f;font-weight:500;">Keep Pulling This Thread</h2>
      <ul style="padding-left:22px;margin:0;color:#14181f;font-size:16px;line-height:1.55;">
        ${dispatchPayload.followups.map((item) => `<li style="margin:0 0 8px;"><a href="${escapeHtml(thingyPromptUrl(item))}" style="${linkStyle()}">${inlineDispatchMarkup(item, sources)}</a></li>`).join('')}
      </ul>
    </td></tr>` : '';

  const sourcesHtml = sources.map((source) => `
    <li id="source-${escapeHtml(source.id)}" style="margin:0 0 8px;">
      ${escapeHtml(source.label)} ·
      ${sourceHref(source) ? `<a href="${escapeHtml(sourceHref(source))}" style="${linkStyle()}">${escapeHtml(source.title)}</a>` : escapeHtml(source.title)}
    </li>`).join('');
  const dispatchId = cleanText(context.dispatchId || context.dispatch_id || '', 120).replace(/[^a-zA-Z0-9._-]+/g, '-');
  const trackingPixelPath = dispatchId ? `/email/thingy/dispatch/${dispatchId}` : '/email/thingy/dispatch';
  const trackingPixel = tinylyticsPixelHtml(trackingPixelPath);

  return `<!doctype html>
<html>
  <body style="margin:0;background:#fcfcfa;color:#14181f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
    <div style="display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;color:transparent;line-height:1px;font-size:1px;">${escapeHtml(dispatchPayload.preview || dispatchPayload.title || 'Thingy Dispatch')}</div>
    <div style="display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;color:transparent;line-height:1px;font-size:1px;">&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fcfcfa;margin:0;padding:24px 12px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#fcfcfa;">
          <tr><td style="padding:0 28px 18px;">
            <div style="padding:14px 16px;border:1px solid #e6ebf2;background:#f7f9fc;">${dispatchProvenanceHtml(context)}</div>
          </td></tr>
          <tr><td style="padding:4px 28px 20px;border-bottom:1px solid #e6ebf2;">
            <div style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:#1f6fd6;margin:0 0 10px;">Thingy Dispatch</div>
            <h1 style="font-family:Charter,'Iowan Old Style','Source Serif 4',Georgia,serif;font-size:34px;line-height:1.1;margin:0 0 8px;color:#14181f;font-weight:500;">${escapeHtml(dispatchPayload.title)}</h1>
            ${dispatchPayload.preview ? `<p style="font-size:17px;line-height:1.45;margin:0;color:#3d4654;">${escapeHtml(dispatchPayload.preview)}</p>` : ''}
          </td></tr>
          <tr><td style="padding:26px 28px 4px;">
            ${renderDispatchBlocks(dispatchPayload.intro, sources)}
          </td></tr>
          ${sectionHtml}
          ${dispatchPayload.closing ? `<tr><td style="padding:18px 28px 28px;">${renderDispatchBlocks(dispatchPayload.closing, sources)}</td></tr>` : ''}
          ${followupHtml}
          <tr><td style="padding:24px 28px;border-top:1px solid #e6ebf2;">
            <h2 style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;line-height:1.2;letter-spacing:.12em;text-transform:uppercase;margin:0 0 12px;color:#1f6fd6;font-weight:600;">Sources</h2>
            <ol style="padding-left:22px;margin:0;color:#14181f;font-size:14px;line-height:1.45;">${sourcesHtml}</ol>
          </td></tr>
          <tr><td style="padding:22px 28px;border-top:1px solid #e6ebf2;">
            <p style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;line-height:1.5;letter-spacing:.04em;color:#7d8694;margin:0;">Prepared by <a href="${THINGY_URL}" style="color:#1f6fd6;text-decoration:underline;">Thingy</a> from Jamie Thingelstad's published archive. Written by Thingy, not Jamie.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    ${trackingPixel}
  </body>
</html>`;
}

export async function renderDispatch(dispatch) {
  const chunks = await loadDispatchCorpus();
  const brief = dispatch.brief && typeof dispatch.brief === 'object' ? dispatch.brief : {};
  const plannedSourceText = Array.isArray(brief.selected_sources)
    ? brief.selected_sources.map((source) => [source?.title, source?.label, source?.why].filter(Boolean).join(' ')).join(' ')
    : '';
  const query = [
    dispatch.prompt,
    dispatch.direction,
    dispatch.clarification_answer,
    brief.user_goal,
    brief.working_angle,
    brief.generation_instructions,
    plannedSourceText
  ].filter(Boolean).join(' ');
  let sources = prioritizeBriefSources(selectDispatchSources(chunks, query, MAX_SOURCE_PACKETS), brief);
  if (dispatch.template_test && sources.length < 4) {
    sources = fallbackDispatchSources(chunks, 8);
  }
  if (sources.length < 4) throw new Error('Not enough archive sources matched this Dispatch topic.');

  if (dispatch.template_test) {
    const payload = dispatchTemplateTestPayload(dispatch, sources);
    const deliveryContext = {
      dispatchId: dispatch.id,
      toEmail: dispatch.to_email,
      requestedAt: dispatch.queued_at || dispatch.created_at,
      requestSummary: brief.preheader_basis || brief.working_angle || dispatch.direction || dispatch.prompt || dispatch.topic
    };
    const html = dispatchHtmlEmail(payload, sources, deliveryContext);
    const fallbackText = dispatchTextEmail(payload, sources, deliveryContext);
    return {
      ...payload,
      text: fallbackText,
      html,
      model: 'template-test',
      usage: { inputTokens: 0, outputTokens: 0 },
      sources: sources.map(({ excerpt, ...source }) => source)
    };
  }

  const model = advancedModel();
  const response = await bedrock.send(new ConverseCommand({
    modelId: model,
    system: [{ text: dispatchSystemPrompt() }, { cachePoint: { type: 'default' } }],
    messages: [{ role: 'user', content: [{ text: dispatchUserPrompt({ dispatch, sources }) }] }],
    inferenceConfig: {
      maxTokens: Number(process.env.BEDROCK_DISPATCH_MAX_TOKENS || '4200'),
      temperature: Number(process.env.BEDROCK_DISPATCH_TEMPERATURE || '0.55')
    }
  }));
  const text = (response.output?.message?.content || []).map((part) => part.text || '').join('\n').trim();
  const parsed = parseDispatchJson(text);
  if (!parsed) throw new Error('Dispatch generation returned invalid JSON.');
  const payload = normalizeDispatchPayload(parsed, dispatch.topic || dispatch.prompt);
  const deliveryContext = {
    dispatchId: dispatch.id,
    toEmail: dispatch.to_email,
    requestedAt: dispatch.queued_at || dispatch.created_at,
    requestSummary: brief.preheader_basis || brief.working_angle || dispatch.direction || dispatch.prompt || dispatch.topic
  };
  const html = dispatchHtmlEmail(payload, sources, deliveryContext);
  const fallbackText = dispatchTextEmail(payload, sources, deliveryContext);
  return {
    ...payload,
    text: fallbackText,
    html,
    model,
    usage: response.usage || {},
    sources: sources.map(({ excerpt, ...source }) => source)
  };
}

export const generateDispatch = renderDispatch;
