import crypto from 'node:crypto';
import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { agentModel, bedrock } from './aws-clients.mjs';
import { ARCHIVE_TOOLS } from './archive-tools.mjs';
import { sanitizeAnswerProse } from './answer-sanitizer.mjs';
import { shouldEmitExperienceForTurn } from './experience.mjs';
import { logEvent as sharedLogEvent } from './logging.mjs';
import { agentSystemPrompt } from './prompts.mjs';
import { compactSource, retrieve, tokenize } from './retrieval.mjs';
import { normalizeScope } from './scope.mjs';
import { conversationModeDefinition, conversationModePrompt, normalizeConversationMode } from './conversation-modes.mjs';

const AGENT_SYSTEM_PROMPT = agentSystemPrompt();
const SERVICE_NAME = 'weekly-thing-librarian-stream';

function logEvent(level, message, fields = {}) {
  sharedLogEvent(level, message, fields, SERVICE_NAME);
}

function bedrockMessageText(message) {
  const parts = [];
  for (const content of message?.content || []) {
    if (content.text) parts.push(content.text);
  }
  return parts.join('\n').trim();
}

function issueKey(value) {
  return String(value || '').replace(/^#/, '').trim();
}

function normalizeSourceKind(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (!raw) return '';
  if (['weekly_thing', 'weeklything', 'newsletter', 'issue', 'issues', 'archive', 'wt', 'chunk'].includes(raw)) return 'weekly_thing';
  if (['blog', 'thingelstad', 'thingelstad_com', 'post', 'posts', 'micropost'].includes(raw)) return 'blog';
  if (['podcast', 'podcasts', 'another', 'another_thing', 'episode', 'episodes'].includes(raw)) return 'podcast';
  return '';
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

function recordYear(record) {
  return Number(record?.issue_year || record?.post_year || String(record?.publish_date || '').match(/\b(?:19|20)\d{2}\b/)?.[0] || 0);
}

function sourceRecordKey(record) {
  const kind = normalizeSourceKind(record?.source_kind || '') || (record?.episode_number ? 'podcast' : record?.microblog_id ? 'blog' : record?.issue_number ? 'weekly_thing' : '');
  if (kind === 'weekly_thing') return `weekly_thing\0${issueKey(record.issue_number || record.number)}`;
  if (kind === 'blog') return `blog\0${record.microblog_id || urlKey(record.url)}`;
  if (kind === 'podcast') return `podcast\0${record.episode_number || record.number || urlKey(record.url)}`;
  return `${kind || 'unknown'}\0${urlKey(record?.url)}`;
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

function recentSparkThemes(conversations = []) {
  return (conversations || [])
    .slice(0, 6)
    .map((item) => cleanThemeCandidate(item?.title || item))
    .filter(Boolean);
}

function isRecentThemeRut(theme, recentThemes = []) {
  if (!theme) return false;
  return recentThemes.filter((recent) => themesSimilar(theme, recent)).length >= 2;
}

function sparkThemeFromConversations(conversations = []) {
  const recentThemes = recentSparkThemes(conversations);
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

export async function buildWelcomeSpark({ conversations, scope }) {
  const theme = sparkThemeFromConversations(conversations);
  const result = await ARCHIVE_TOOLS.archive_gems({
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

function curiosityThemeCandidates(conversations = []) {
  const candidates = new Map();
  const add = (value, weight, reason, kind = 'recent') => {
    const theme = cleanThemeCandidate(value);
    if (theme) addCuriosityCandidate(candidates, theme, { weight, reason, kind });
  };
  for (const entry of (conversations || []).slice(0, 10)) add(entry?.title || '', 2.5, 'conversation history', 'recent');
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

export async function buildCuriosityMap({ conversations, scope, center }) {
  const requestedCenter = cleanCuriosityLabel(center);
  const userCandidates = curiosityThemeCandidates(conversations);
  const fallbackTheme = cleanCuriosityLabel(sparkThemeFromConversations(conversations));
  const centerTheme = cleanCuriosityLabel(requestedCenter || userCandidates[0]?.label || fallbackTheme) || 'Archive';
  const scopeValue = normalizeScope(scope);
  const archiveResult = centerTheme && centerTheme !== 'Archive'
    ? await ARCHIVE_TOOLS.archive_gems({ theme: centerTheme, limit: 7 }, { scope: scopeValue })
    : await ARCHIVE_TOOLS.archive_gems({ mood: 'serendipity', limit: 7 }, { scope: scopeValue });
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
    const broad = await ARCHIVE_TOOLS.archive_gems({ mood: 'serendipity', limit: 5 }, { scope: scopeValue });
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
      why: 'Current center of gravity from your recent conversations.'
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

export function experienceFromToolResults(toolResults = [], answer = '', question = '') {
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

function welcomePrompt({ readerContext, conversations, scope, mode, spark }) {
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
    '- If this looks like their first time, give a little more orientation. If returning, welcome them back and lightly reference recent conversations when they exist.',
    '- If an archive spark is supplied, mention it as a small invitation, not a citation-heavy answer. The UI may show it as a card.',
    '- In Thought Partner mode, welcome Jamie as the author and invite a reflective thread rather than explaining Thingy to a general reader.',
    '- If they are a Weekly Thing Supporting Member, acknowledge that gracefully without making the whole message about it.',
    '- Do not frame Thingy as just search. Prefer agentic verbs like connect, trace, compare, explore, and pick up threads.',
    '- Do not recite the active source list or say all sources are open; the UI already shows source selection.',
    '- Keep it under 115 words, no heading, no table, no citations.'
  ].join('\n');
}

export async function generateWelcome({ readerContext, conversations, scope, mode, spark }) {
  const start = performance.now();
  const response = await bedrock.send(new ConverseCommand({
    modelId: agentModel(),
    system: [{ text: AGENT_SYSTEM_PROMPT }, { cachePoint: { type: 'default' } }],
    messages: [{
      role: 'user',
      content: [{ text: welcomePrompt({ readerContext, conversations, scope, mode, spark }) }]
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
