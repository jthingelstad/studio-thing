export function yearFromPublishDate(value) {
  const match = String(value || '').match(/\b(?:19|20)\d{2}\b/);
  return match ? Number(match[0]) : 0;
}

export function countsByPublishYear(records = []) {
  const counts = new Map();
  for (const record of records || []) {
    const year = yearFromPublishDate(record?.publish_date);
    if (!year) continue;
    counts.set(year, (counts.get(year) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[0] - a[0])
    .map(([year, count]) => ({ year, count }));
}

export function yearCountSummary(countsByYear = []) {
  const rows = (countsByYear || [])
    .filter((row) => Number.isFinite(Number(row?.year)) && Number.isFinite(Number(row?.count)))
    .map((row) => ({ year: Number(row.year), count: Number(row.count) }));
  if (!rows.length) return { highest_years: [], lowest_years: [] };
  const highestCount = Math.max(...rows.map((row) => row.count));
  const lowestCount = Math.min(...rows.map((row) => row.count));
  return {
    highest_years: rows
      .filter((row) => row.count === highestCount)
      .sort((a, b) => b.year - a.year),
    lowest_years: rows
      .filter((row) => row.count === lowestCount)
      .sort((a, b) => b.year - a.year)
  };
}

const STOPWORDS = new Set([
  'about', 'after', 'again', 'also', 'and', 'another', 'because', 'before', 'being',
  'been', 'blog', 'but', 'can', 'could', 'did', 'does', 'doing', 'don', 'from',
  'had', 'has', 'have', 'into', 'its', 'jamie', 'just', 'like', 'more', 'not',
  'one', 'our', 'out', 'over', 'post', 'she', 'some', 'than', 'that', 'the',
  'their', 'there', 'these', 'they', 'thing', 'this', 'was', 'were', 'with',
  'weekly', 'what', 'when', 'where', 'which', 'while', 'who', 'will', 'would',
  'you', 'your'
]);

function increment(map, key, amount = 1) {
  const normalized = String(key || '').trim();
  if (!normalized) return;
  map.set(normalized, (map.get(normalized) || 0) + amount);
}

function topCounts(map, key, limit = 8) {
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([name, count]) => ({ [key]: name, count }));
}

function terms(value, { maxChars = 0 } = {}) {
  const text = String(value || '');
  const input = maxChars ? text.slice(0, maxChars) : text;
  return input
    .toLowerCase()
    .match(/[a-z][a-z0-9'-]{2,}/g)
    ?.filter((term) => !STOPWORDS.has(term) && !/^\d+$/.test(term)) || [];
}

function subjectTerms(value) {
  return terms(value);
}

function textTerms(value) {
  return Array.from(new Set(terms(value, { maxChars: 1800 })));
}

function bucketFor(buckets, year) {
  if (!buckets.has(year)) {
    buckets.set(year, {
      year,
      count: 0,
      chunk_count: 0,
      subjectTerms: new Map(),
      textTerms: new Map(),
      domains: new Map(),
      sections: new Map(),
      samples: []
    });
  }
  return buckets.get(year);
}

export function yearlyContentSignals(records = [], options = {}) {
  const topYearLimit = Math.max(Number(options.topYearLimit || 40), 1);
  const sampleLimit = Math.max(Number(options.sampleLimit || 4), 0);
  const chunks = Array.isArray(options.chunks) ? options.chunks : [];
  const buckets = new Map();
  for (const record of records || []) {
    const year = yearFromPublishDate(record?.publish_date);
    if (!year) continue;
    const bucket = bucketFor(buckets, year);
    bucket.count += 1;
    for (const term of subjectTerms([record.subject, record.title].join(' '))) {
      increment(bucket.subjectTerms, term);
    }
    for (const domain of record.domains || []) increment(bucket.domains, domain);
    increment(bucket.sections, record.section || record.post_kind || record.source_kind || 'item');
    if (bucket.samples.length < sampleLimit) {
      bucket.samples.push({
        subject: record.subject || '',
        publish_date: record.publish_date || '',
        url: record.url || '',
        section: record.section || ''
      });
    }
  }
  for (const chunk of chunks) {
    const year = yearFromPublishDate(chunk?.publish_date);
    if (!year) continue;
    const bucket = bucketFor(buckets, year);
    bucket.chunk_count += 1;
    for (const term of textTerms([chunk.subject, chunk.section, chunk.summary, chunk.text].join(' '))) {
      increment(bucket.textTerms, term);
    }
  }
  return Array.from(buckets.values())
    .sort((a, b) => b.year - a.year)
    .slice(0, topYearLimit)
    .map((bucket) => ({
      year: bucket.year,
      count: bucket.count,
      chunk_count: bucket.chunk_count,
      top_subject_terms: topCounts(bucket.subjectTerms, 'term', 10),
      top_text_terms: topCounts(bucket.textTerms, 'term', 12),
      top_domains: topCounts(bucket.domains, 'domain', 8),
      counts_by_section: topCounts(bucket.sections, 'section', 8),
      sample_items: bucket.samples
    }));
}
