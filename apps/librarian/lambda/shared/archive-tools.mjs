import { buildArchiveLens } from './archive-lens.mjs';
import { countsByPublishYear, yearCountSummary, yearlyContentSignals } from './corpus-stats.mjs';
import { searchFaq } from './faq.mjs';
import { loadToolSpecs } from './prompts.mjs';
import { compactSource, loadCorpus, loadGraph, parseYearRange, retrieve, tokenize } from './retrieval.mjs';
import { normalizeScope, scopeKinds } from './scope.mjs';

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

export function collectToolCitations(toolResults = []) {
  const sources = [];
  for (const result of toolResults || []) {
    if (!result || result.error) continue;
    if (Array.isArray(result.results)) sources.push(...result.results);
    if (result.source) sources.push(result.source);
    if (result.issue) sources.push(result.issue);
  }
  return citationsFor(sources);
}

function issueKey(value) {
  return String(value || '').replace(/^#/, '').trim();
}

async function issueByNumber(number) {
  const wanted = issueKey(number);
  const corpus = await loadCorpus();
  return (corpus.issues || []).find((issue) => issueKey(issue.number) === wanted);
}

export async function weeklyIssueCatalog() {
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

export const ARCHIVE_TOOLS = {
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
  claim_check: toolClaimCheck
};

export function toolSpecs() {
  return loadToolSpecs();
}
