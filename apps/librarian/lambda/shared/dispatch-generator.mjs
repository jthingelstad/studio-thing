import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { GetObjectCommand } from '@aws-sdk/client-s3';
import { bedrock, s3, advancedModel } from './aws-clients.mjs';
import { sendJmapEmail } from './jmap-mail.mjs';

const MAX_SOURCE_PACKETS = 18;
const TOKEN_RE = /[a-z0-9][a-z0-9'-]{1,}/gi;

let corpusCache = null;

function cleanText(value, max = 1000) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function tokenize(value) {
  const words = String(value || '').toLowerCase().match(TOKEN_RE) || [];
  return words.filter((word) => word.length > 2);
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
- Include source references like [S1] in section bodies where claims depend on a source.
- Return only JSON.`;
}

function dispatchUserPrompt({ dispatch, sources }) {
  return [
    `Reader request: ${dispatch.prompt || dispatch.topic}`,
    dispatch.clarification_question ? `Thingy's clarification question: ${dispatch.clarification_question}` : '',
    dispatch.clarification_answer ? `Reader clarification: ${dispatch.clarification_answer}` : '',
    dispatch.direction ? `Confirmed direction: ${dispatch.direction}` : '',
    '',
    'Source packets:',
    sourcePacketText(sources),
    '',
    'Return JSON with this shape:',
    '{',
    '  "subject": "email subject line, starts with Dispatch:",',
    '  "preview": "one sentence preview",',
    '  "title": "Dispatch title",',
    '  "intro": "2-3 paragraph Thingy-authored opening",',
    '  "sections": [{"heading":"section heading","body":"2-4 paragraphs with [S#] references"}],',
    '  "closing": "short closing from Thingy",',
    '  "followups": ["question to continue in Thingy"]',
    '}'
  ].filter(Boolean).join('\n');
}

export function dispatchTemplateTestPayload(dispatch, sources = []) {
  const topic = cleanText(dispatch.direction || dispatch.prompt || dispatch.topic || 'Dispatch template test', 180);
  const refs = sources.slice(0, 6).map((source) => `[${source.id}]`).join(', ');
  const primaryRefs = refs || '[S1]';
  return normalizeDispatchPayload({
    subject: `Dispatch Template Test: ${topic}`,
    preview: 'A low-cost Thingy Dispatch template test using placeholder copy and real archive source metadata.',
    title: `Template Test: ${topic}`,
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

function paragraphs(text) {
  return String(text || '')
    .split(/\n{2,}/)
    .map((part) => cleanText(part, 3000))
    .filter(Boolean);
}

function sourceLinkMap(sources = []) {
  return Object.fromEntries(sources.map((source) => [source.id, source]));
}

function inlineSourceRefs(text, sources = []) {
  const map = sourceLinkMap(sources);
  return escapeHtml(text).replace(/\[(S\d+)\]/g, (match, id) => {
    const source = map[id];
    if (!source?.url) return `<strong>${id}</strong>`;
    return `<a href="${escapeHtml(source.url)}" style="color:#315f54;text-decoration:underline;">${escapeHtml(source.label || id)}</a>`;
  });
}

function normalizeDispatchPayload(payload = {}, fallbackTopic = '') {
  const sections = Array.isArray(payload.sections) ? payload.sections : [];
  return {
    subject: cleanText(payload.subject || `Dispatch: ${fallbackTopic || 'From the archive'}`, 110),
    preview: cleanText(payload.preview || '', 220),
    title: cleanText(payload.title || fallbackTopic || 'Dispatch from Thingy', 140),
    intro: cleanText(payload.intro || '', 4000),
    sections: sections.slice(0, 7).map((section, index) => ({
      heading: cleanText(section?.heading || `Thread ${index + 1}`, 120),
      body: cleanText(section?.body || '', 5000)
    })).filter((section) => section.body),
    closing: cleanText(payload.closing || '', 2000),
    followups: Array.isArray(payload.followups)
      ? payload.followups.map((item) => cleanText(item, 160)).filter(Boolean).slice(0, 5)
      : []
  };
}

export function dispatchTextEmail(dispatchPayload, sources = []) {
  const lines = [
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
    dispatchPayload.followups.forEach((item) => lines.push(`- ${item}`));
    lines.push('');
  }
  lines.push('Sources:');
  sources.forEach((source) => lines.push(`- [${source.id}] ${source.label} · ${source.title}${source.url ? ` — ${source.url}` : ''}`));
  lines.push('', "Prepared by Thingy from Jamie Thingelstad's published archive. Written by Thingy, not Jamie.");
  return lines.filter((line, index, all) => line || all[index - 1]).join('\n');
}

export function dispatchHtmlEmail(dispatchPayload, sources = []) {
  const sectionHtml = dispatchPayload.sections.map((section) => `
    <tr><td style="padding:22px 30px 4px;">
      <h2 style="font-family:Georgia,'Times New Roman',serif;font-size:24px;line-height:1.2;margin:0 0 10px;color:#17231f;">${escapeHtml(section.heading)}</h2>
      ${paragraphs(section.body).map((p) => `<p style="font-size:16px;line-height:1.62;margin:0 0 14px;color:#24322e;">${inlineSourceRefs(p, sources)}</p>`).join('')}
    </td></tr>`).join('');

  const followupHtml = dispatchPayload.followups.length ? `
    <tr><td style="padding:18px 30px;background:#f3f6f0;border-top:1px solid #dfe8df;">
      <h2 style="font-family:Georgia,'Times New Roman',serif;font-size:21px;line-height:1.2;margin:0 0 10px;color:#17231f;">Keep Pulling This Thread</h2>
      <ul style="padding-left:20px;margin:0;color:#24322e;font-size:15px;line-height:1.55;">
        ${dispatchPayload.followups.map((item) => `<li style="margin:0 0 8px;">${escapeHtml(item)}</li>`).join('')}
      </ul>
    </td></tr>` : '';

  const sourcesHtml = sources.map((source) => `
    <li style="margin:0 0 8px;">
      <strong>${escapeHtml(source.id)}</strong> ${escapeHtml(source.label)} ·
      ${source.url ? `<a href="${escapeHtml(source.url)}" style="color:#315f54;">${escapeHtml(source.title)}</a>` : escapeHtml(source.title)}
      ${source.publish_date ? `<span style="color:#7c8a84;">(${escapeHtml(source.publish_date)})</span>` : ''}
    </li>`).join('');

  return `<!doctype html>
<html>
  <body style="margin:0;background:#f5f3ee;color:#17231f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f3ee;margin:0;padding:28px 12px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#fffdf8;border:1px solid #ded8ca;">
          <tr><td style="padding:28px 30px 20px;border-bottom:4px solid #203c35;">
            <div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:700;color:#587268;">Thingy Dispatch</div>
            <h1 style="font-family:Georgia,'Times New Roman',serif;font-size:36px;line-height:1.08;margin:10px 0 8px;color:#14211d;font-weight:700;">${escapeHtml(dispatchPayload.title)}</h1>
            ${dispatchPayload.preview ? `<p style="font-size:17px;line-height:1.45;margin:0;color:#4a5b54;">${escapeHtml(dispatchPayload.preview)}</p>` : ''}
          </td></tr>
          <tr><td style="padding:24px 30px 4px;">
            ${paragraphs(dispatchPayload.intro).map((p) => `<p style="font-size:17px;line-height:1.65;margin:0 0 15px;color:#24322e;">${inlineSourceRefs(p, sources)}</p>`).join('')}
          </td></tr>
          ${sectionHtml}
          ${dispatchPayload.closing ? `<tr><td style="padding:18px 30px 26px;">${paragraphs(dispatchPayload.closing).map((p) => `<p style="font-size:16px;line-height:1.62;margin:0 0 14px;color:#24322e;">${inlineSourceRefs(p, sources)}</p>`).join('')}</td></tr>` : ''}
          ${followupHtml}
          <tr><td style="padding:22px 30px;border-top:1px solid #d8d4c9;">
            <h2 style="font-family:Georgia,'Times New Roman',serif;font-size:20px;line-height:1.2;margin:0 0 10px;color:#17231f;">Sources</h2>
            <ol style="padding-left:20px;margin:0;color:#24322e;font-size:14px;line-height:1.45;">${sourcesHtml}</ol>
          </td></tr>
          <tr><td style="padding:18px 30px;background:#203c35;color:#edf5f1;">
            <p style="font-size:13px;line-height:1.5;margin:0;">Prepared by Thingy from Jamie Thingelstad's published archive. Written by Thingy, not Jamie.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>`;
}

export async function generateDispatch(dispatch) {
  const chunks = await loadDispatchCorpus();
  const query = [dispatch.prompt, dispatch.direction, dispatch.clarification_answer].filter(Boolean).join(' ');
  let sources = selectDispatchSources(chunks, query, MAX_SOURCE_PACKETS);
  if (dispatch.template_test && sources.length < 4) {
    sources = fallbackDispatchSources(chunks, 8);
  }
  if (sources.length < 4) throw new Error('Not enough archive sources matched this Dispatch topic.');

  if (dispatch.template_test) {
    const payload = dispatchTemplateTestPayload(dispatch, sources);
    const html = dispatchHtmlEmail(payload, sources);
    const fallbackText = dispatchTextEmail(payload, sources);
    const sent = await sendJmapEmail({
      to: dispatch.to_email,
      subject: payload.subject.startsWith('Dispatch') ? payload.subject : `Dispatch Template Test: ${payload.subject}`,
      text: fallbackText,
      html
    });
    return {
      ...payload,
      text: fallbackText,
      html,
      model: 'template-test',
      usage: { inputTokens: 0, outputTokens: 0 },
      sources: sources.map(({ excerpt, ...source }) => source),
      submission_id: sent.submission_id
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
  const html = dispatchHtmlEmail(payload, sources);
  const fallbackText = dispatchTextEmail(payload, sources);
  const sent = await sendJmapEmail({
    to: dispatch.to_email,
    subject: payload.subject.startsWith('Dispatch:') ? payload.subject : `Dispatch: ${payload.subject}`,
    text: fallbackText,
    html
  });
  return {
    ...payload,
    text: fallbackText,
    html,
    model,
    usage: response.usage || {},
    sources: sources.map(({ excerpt, ...source }) => source),
    submission_id: sent.submission_id
  };
}
