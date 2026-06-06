import { countsByPublishYear, yearCountSummary, yearFromPublishDate } from './corpus-stats.mjs';

const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;
const DEFAULT_LIMIT = 18;

function tokenize(value) {
  return Array.from(String(value || '').matchAll(TOKEN_RE), (match) => match[0].toLowerCase());
}

function compactWhitespace(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

export function normalizeLensOperation(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (['first', 'last', 'first_last', 'first_and_last', 'earliest_latest'].includes(raw)) return 'first_last';
  if (['year', 'years', 'by_year', 'yearly', 'themes_by_year'].includes(raw)) return 'by_year';
  if (['sources', 'source', 'source_compare', 'compare_sources', 'by_source'].includes(raw)) return 'source_compare';
  if (['reading_path', 'path', 'tour', 'route'].includes(raw)) return 'reading_path';
  return 'timeline';
}

export function parseLensYearRange(value) {
  if (!value) return [null, null];
  if (Array.isArray(value) && value.length >= 2) return [Number(value[0]) || null, Number(value[1]) || null];
  if (typeof value === 'object') return [Number(value.start || value.from) || null, Number(value.end || value.to) || null];
  const years = String(value).match(/\b(?:19|20)\d{2}\b/g)?.map(Number) || [];
  if (years.length > 1) return [Math.min(...years), Math.max(...years)];
  if (years.length === 1) return [years[0], years[0]];
  return [null, null];
}

function inYearRange(item, yearRange) {
  const [start, end] = parseLensYearRange(yearRange);
  const year = yearFromPublishDate(item.publish_date);
  if (start && (!year || year < start)) return false;
  if (end && (!year || year > end)) return false;
  return true;
}

function topicTokens(topic) {
  return tokenize(topic).filter((token) => token.length > 2);
}

export function matchesLensTopic(item, topic) {
  const rawTopic = compactWhitespace(topic).toLowerCase();
  if (!rawTopic) return true;
  const haystack = compactWhitespace([
    item.subject,
    item.title,
    item.section,
    item.summary,
    item.text,
    (item.topics || []).join(' '),
    (item.domains || []).join(' ')
  ].join(' ')).toLowerCase();
  if (haystack.includes(rawTopic)) return true;
  const tokens = topicTokens(topic);
  if (!tokens.length) return false;
  const matchCount = tokens.filter((token) => (
    haystack.includes(token) ||
    (token.length >= 6 && haystack.includes(token.slice(0, 5)))
  )).length;
  return tokens.length <= 2 ? matchCount === tokens.length : matchCount >= Math.ceil(tokens.length * 0.7);
}

function sourceKey(item) {
  return [
    item.source_kind || '',
    item.issue_number || item.episode_number || item.microblog_id || '',
    item.url || ''
  ].join('\0');
}

function sourceFromChunk(chunk) {
  return {
    source_kind: chunk.source_kind || 'weekly_thing',
    issue_number: chunk.issue_number ?? null,
    microblog_id: chunk.microblog_id,
    episode_number: chunk.episode_number,
    show: chunk.show,
    subject: chunk.subject || '',
    publish_date: chunk.publish_date || '',
    section: chunk.section || '',
    url: chunk.url || (chunk.issue_number ? `/archive/${chunk.issue_number}/` : ''),
    transcript_url: chunk.transcript_url,
    audio_url: chunk.audio_url,
    also_in_issues: chunk.also_in_issues,
    topics: chunk.topics || [],
    domains: chunk.domains || []
  };
}

function snippetFor(text, topic) {
  const clean = compactWhitespace(text);
  if (!clean) return '';
  const lower = clean.toLowerCase();
  const rawTopic = compactWhitespace(topic).toLowerCase();
  let index = rawTopic ? lower.indexOf(rawTopic) : -1;
  if (index < 0) {
    for (const token of topicTokens(topic)) {
      index = lower.indexOf(token);
      if (index >= 0) break;
    }
  }
  if (index < 0) return clean.slice(0, 360);
  return clean.slice(Math.max(0, index - 140), Math.min(clean.length, index + 260));
}

function mergeSource(existing, chunk, topic) {
  existing.match_count += 1;
  existing.sections.add(chunk.section || '');
  for (const domain of chunk.domains || []) existing.domains.add(domain);
  for (const sourceTopic of chunk.topics || []) existing.topics.add(sourceTopic);
  const snippet = snippetFor(chunk.text || '', topic);
  if (snippet && existing.evidence.length < 3) {
    existing.evidence.push({
      section: chunk.section || '',
      text: snippet
    });
  }
}

function compactLensSource(item) {
  return {
    source_kind: item.source_kind,
    issue_number: item.issue_number ?? null,
    microblog_id: item.microblog_id,
    episode_number: item.episode_number,
    show: item.show,
    subject: item.subject,
    publish_date: item.publish_date,
    year: yearFromPublishDate(item.publish_date) || null,
    section: item.section || '',
    sections: Array.from(item.sections || []).filter(Boolean).slice(0, 8),
    url: item.url,
    transcript_url: item.transcript_url,
    audio_url: item.audio_url,
    also_in_issues: item.also_in_issues,
    match_count: item.match_count || 0,
    topics: Array.from(item.topics || []).filter(Boolean).slice(0, 12),
    domains: Array.from(item.domains || []).filter(Boolean).slice(0, 12),
    evidence: item.evidence || []
  };
}

function sortByDateAsc(items) {
  return [...items].sort((a, b) => String(a.publish_date || '').localeCompare(String(b.publish_date || '')));
}

function topCounts(map, key, limit = 10) {
  return Array.from(map.entries())
    .filter(([name]) => name)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([name, count]) => ({ [key]: name, count }));
}

function yearBuckets(items) {
  const buckets = new Map();
  for (const item of items) {
    const year = yearFromPublishDate(item.publish_date);
    if (!year) continue;
    if (!buckets.has(year)) {
      buckets.set(year, {
        year,
        source_count: 0,
        evidence_count: 0,
        sources: [],
        sections: new Map(),
        domains: new Map()
      });
    }
    const bucket = buckets.get(year);
    bucket.source_count += 1;
    bucket.evidence_count += item.match_count || 0;
    for (const section of item.sections || []) bucket.sections.set(section, (bucket.sections.get(section) || 0) + 1);
    for (const domain of item.domains || []) bucket.domains.set(domain, (bucket.domains.get(domain) || 0) + 1);
    if (bucket.sources.length < 5) bucket.sources.push(compactLensSource(item));
  }
  return Array.from(buckets.values())
    .sort((a, b) => b.year - a.year)
    .map((bucket) => ({
      year: bucket.year,
      source_count: bucket.source_count,
      evidence_count: bucket.evidence_count,
      top_sections: topCounts(bucket.sections, 'section', 6),
      top_domains: topCounts(bucket.domains, 'domain', 6),
      sample_sources: bucket.sources
    }));
}

function sourceBuckets(items) {
  const buckets = new Map();
  for (const item of items) {
    const key = item.source_kind || 'unknown';
    if (!buckets.has(key)) {
      buckets.set(key, {
        source_kind: key,
        source_count: 0,
        evidence_count: 0,
        dates: [],
        sources: []
      });
    }
    const bucket = buckets.get(key);
    bucket.source_count += 1;
    bucket.evidence_count += item.match_count || 0;
    if (item.publish_date) bucket.dates.push(item.publish_date);
    if (bucket.sources.length < 6) bucket.sources.push(compactLensSource(item));
  }
  return Array.from(buckets.values())
    .sort((a, b) => b.source_count - a.source_count || a.source_kind.localeCompare(b.source_kind))
    .map((bucket) => ({
      source_kind: bucket.source_kind,
      source_count: bucket.source_count,
      evidence_count: bucket.evidence_count,
      first_publish_date: bucket.dates.sort()[0] || '',
      latest_publish_date: bucket.dates.sort().at(-1) || '',
      sample_sources: bucket.sources
    }));
}

function readingPath(items, limit) {
  const chronological = sortByDateAsc(items);
  if (!chronological.length) return [];
  const chosen = new Map();
  const add = (item, reason) => {
    if (!item) return;
    chosen.set(sourceKey(item), { ...compactLensSource(item), reason });
  };
  add(chronological[0], 'earliest matched source');
  const buckets = yearBuckets(items).sort((a, b) => b.evidence_count - a.evidence_count);
  add(buckets[0]?.sample_sources?.[0], 'densest year for this topic');
  add(chronological[Math.floor(chronological.length / 2)], 'middle-era bridge');
  add(chronological.at(-1), 'latest matched source');
  for (const item of chronological) {
    if (chosen.size >= limit) break;
    add(item, 'additional representative source');
  }
  return Array.from(chosen.values()).slice(0, limit);
}

export function buildArchiveLens({ topic = '', operation = 'timeline', records = [], chunks = [], yearRange = null, limit = DEFAULT_LIMIT } = {}) {
  const normalizedOperation = normalizeLensOperation(operation);
  const maxResults = Math.min(Math.max(Number(limit || DEFAULT_LIMIT), 1), 40);
  const sources = new Map();

  for (const record of records || []) {
    if (!inYearRange(record, yearRange) || !matchesLensTopic(record, topic)) continue;
    const source = {
      ...record,
      match_count: 1,
      sections: new Set([record.section || '']),
      topics: new Set(record.topics || []),
      domains: new Set(record.domains || []),
      evidence: []
    };
    sources.set(sourceKey(source), source);
  }

  for (const chunk of chunks || []) {
    if (!inYearRange(chunk, yearRange) || !matchesLensTopic(chunk, topic)) continue;
    const key = sourceKey(chunk);
    if (!sources.has(key)) {
      const source = sourceFromChunk(chunk);
      sources.set(key, {
        ...source,
        match_count: 0,
        sections: new Set([source.section || '']),
        topics: new Set(source.topics || []),
        domains: new Set(source.domains || []),
        evidence: []
      });
    }
    mergeSource(sources.get(key), chunk, topic);
  }

  const matched = sortByDateAsc(Array.from(sources.values()).filter((item) => item.publish_date));
  const countsByYear = countsByPublishYear(matched);
  const timeline = matched.slice(0, maxResults).map(compactLensSource);
  const latest = [...matched].reverse().slice(0, maxResults).map(compactLensSource);
  const years = yearBuckets(matched);
  const bySource = sourceBuckets(matched);

  return {
    operation: normalizedOperation,
    topic: compactWhitespace(topic),
    total_sources: matched.length,
    total_evidence_matches: matched.reduce((sum, item) => sum + (item.match_count || 0), 0),
    counts_by_year: countsByYear,
    year_count_summary: yearCountSummary(countsByYear),
    first: matched[0] ? compactLensSource(matched[0]) : null,
    latest: matched.at(-1) ? compactLensSource(matched.at(-1)) : null,
    results: normalizedOperation === 'first_last'
      ? [matched[0], matched.at(-1)].filter(Boolean).map(compactLensSource)
      : normalizedOperation === 'reading_path'
        ? readingPath(matched, Math.min(maxResults, 8))
        : normalizedOperation === 'source_compare'
          ? bySource.flatMap((bucket) => bucket.sample_sources).slice(0, maxResults)
          : normalizedOperation === 'by_year'
            ? years.flatMap((bucket) => bucket.sample_sources.slice(0, 2)).slice(0, maxResults)
            : timeline,
    timeline,
    latest_sources: latest,
    years,
    sources: bySource,
    reading_path: readingPath(matched, Math.min(maxResults, 8))
  };
}
